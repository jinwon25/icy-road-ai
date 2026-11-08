"""공개 IFS 수식의 수증기압·서리점 입력과 문맥에 불변인 과거 창.

원 식: ECMWF earthkit-meteo saturation_vapour_pressure(method='ifs').
물/얼음의 포화 수증기압은 구별한다. 이 모듈은 관측 목표를 읽지 않는다.
"""
import numpy as np
import pandas as pd
from scipy.special import expit, logit

from src.road_weather_transfer import features
from src.weather_history_stable import stable_temporal_features

PHYSICAL_HISTORY = ['asos_vapor_pressure_pa', 'asos_saturation_deficit_pa',
                    'aws_vapor_pressure_pa', 'aws_saturation_deficit_pa']


def saturation_pressure(temperature_c, phase='water'):
    """IFS CY47R3의 단일 상 수식. 입력 °C, 출력 Pa, 범위 밖은 결측."""
    if phase not in ['water', 'ice']:
        raise ValueError('Water or ice phase required')
    t = np.asarray(temperature_c, float)
    good = np.isfinite(t) & (t >= -80) & (t <= 60)
    a, b = (17.502, 32.19) if phase == 'water' else (22.587, -0.7)
    kelvin = np.where(good, t + 273.15, np.nan)
    return 611.21 * np.exp(a * (kelvin - 273.16) / (kelvin - b))


def frost_point(vapor_pressure_pa):
    """동일 얼음 포화 수식의 해석적 역함수. e<=0은 결측."""
    e = np.asarray(vapor_pressure_pa, float)
    with np.errstate(divide='ignore', invalid='ignore'):
        ratio = np.log(np.where(e > 0, e / 611.21, np.nan))
        t = (22.587 * 273.16 + 0.7 * ratio) / (22.587 - ratio) - 273.15
    return np.where(np.isfinite(t) & (t >= -80) & (t <= 60), t, np.nan)


def vapor_pressure(temperature_c, relative_humidity):
    rh = np.asarray(relative_humidity, float)
    return saturation_pressure(temperature_c) * np.where((rh >= 0) & (rh <= 100), rh / 100, np.nan)


def instantaneous_thermodynamics(frame):
    base = features(frame)
    result = pd.DataFrame(index=frame.index)
    for prefix, dew in [('asos', 'dewpoint_obs'), ('aws', 'dewpoint')]:
        t = base[prefix + '_air_temp'].to_numpy()
        rh = base[prefix + '_humidity'].to_numpy()
        es = saturation_pressure(t)
        e = vapor_pressure(t, rh)
        fp = frost_point(e)
        values = dict(liquid_saturation_pa=es, vapor_pressure_pa=e,
            saturation_deficit_pa=es-e, frost_point_c=fp, air_frost_gap_c=t-fp,
            dewpoint_rh_disagreement_pct=100*saturation_pressure(base[prefix+'_'+dew])/es-rh,
            ice_saturation_deficit_pa=np.where(t<=0, saturation_pressure(t, 'ice')-e, np.nan))
        for name, value in values.items():
            result[prefix + '_' + name] = value
    ground = base.asos_ground_temp.to_numpy()
    e = result.asos_vapor_pressure_pa.to_numpy()
    result['asos_ground_condensation_pa'] = e-saturation_pressure(ground)
    result['asos_ground_frost_excess_pa'] = np.where(ground<=0, e-saturation_pressure(ground, 'ice'), np.nan)
    result['aws_asos_vapor_contrast_pa'] = result.aws_vapor_pressure_pa-result.asos_vapor_pressure_pa
    result['aws_asos_frost_contrast_c'] = result.aws_frost_point_c-result.asos_frost_point_c
    if np.isinf(result.to_numpy()).any():
        raise ValueError('Infinite thermodynamic input')
    assert len(result.columns) == 18
    return result


def thermodynamic_features(frame, history=None):
    if not frame.index.equals(pd.RangeIndex(len(frame))):
        raise ValueError('Reset source index required')
    if frame[['station', 'winter', 'time']].isna().any().any() or frame.duplicated(['station', 'time']).any():
        raise ValueError('Complete unique history keys required')
    if history is None:
        _, history = stable_temporal_features(frame)
    if not history.index.equals(frame.index) or len(history.columns) != 82:
        raise ValueError('Aligned 82-column stable history required')
    physical = instantaneous_thermodynamics(frame)
    extra = {c: physical[c].to_numpy().copy() for c in physical}
    for hours in [3, 24]:
        for field in PHYSICAL_HISTORY:
            for kind in ['mean', 'departure', 'coverage']:
                extra[f'{field}_{kind}_{hours}h'] = np.full(len(frame), np.nan)
    step = pd.Timedelta(minutes=10).value
    for _, part in frame.groupby(['station', 'winter'], sort=True):
        order = part.sort_values('time').index.to_numpy()
        times = pd.DatetimeIndex(frame.loc[order, 'time']).asi8
        if np.any(times % step) or np.any(np.diff(times) <= 0):
            raise ValueError('Unique ten-minute history clock required')
        position = ((times-times[0])//step).astype(np.int64)
        current = physical.loc[order, PHYSICAL_HISTORY].to_numpy()
        dense = np.full((int(position[-1])+1, len(PHYSICAL_HISTORY)), np.nan)
        dense[position] = current
        valid = np.isfinite(dense)
        clean = np.where(valid, dense, 0.)
        for hours, minimum in [(3, 6), (24, 48)]:
            width = hours*6
            padded = np.vstack([np.zeros((width-1, len(PHYSICAL_HISTORY))), clean])
            padded_valid = np.vstack([np.zeros((width-1, len(PHYSICAL_HISTORY)), bool), valid])
            total = np.lib.stride_tricks.sliding_window_view(padded, width, axis=0).sum(axis=2)[position]
            count = np.lib.stride_tricks.sliding_window_view(padded_valid, width, axis=0).sum(axis=2)[position]
            mean = np.divide(total, count, out=np.full_like(total, np.nan), where=count>=minimum)
            for j, field in enumerate(PHYSICAL_HISTORY):
                extra[f'{field}_mean_{hours}h'][order] = mean[:, j]
                extra[f'{field}_departure_{hours}h'][order] = current[:, j]-mean[:, j]
                extra[f'{field}_coverage_{hours}h'][order] = count[:, j]/width
    result = pd.concat([history, pd.DataFrame(extra, index=frame.index)], axis=1)
    assert len(result.columns) == 124 and not result.columns.duplicated().any()
    if np.isinf(result.to_numpy()).any():
        raise ValueError('Infinite physical history input')
    return result


def transformed_target(observed, baseline, kind):
    if kind == 'thermo_residual':
        return np.asarray(observed, float)-np.asarray(baseline, float), np.ones(len(observed))
    if kind != 'thermo_logit':
        raise ValueError(kind)
    p = np.clip(np.asarray(observed, float)/100, .005, .995)
    b = np.clip(np.asarray(baseline, float)/100, .005, .995)
    # 물리 단위 L1을 국소 근사하는 야코비안 가중치. 정확한 동치 손실은 아니다.
    return logit(p)-logit(b), p*(1-p)


def inverse_target(score, baseline, kind):
    if kind == 'thermo_residual':
        return np.clip(np.asarray(score)+baseline, 0, 100)
    if kind != 'thermo_logit':
        raise ValueError(kind)
    return 100*expit(np.asarray(score)+logit(np.clip(np.asarray(baseline)/100, .005, .995)))
