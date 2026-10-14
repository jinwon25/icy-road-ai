"""목표 노면 관측 없이 만드는 기상 이력과 고정 조건별 경험적 오차 범위."""
import numpy as np
import pandas as pd

from src.method_blending import domain
from src.temperature_uncertainty import residual_radius
from src.weather_distance_ablation import DISTANCE_FREE_FEATURES

HISTORY_COLUMNS = ('asos_air_temp', 'aws_air_temp', 'aws_humidity', 'aws_dewpoint', 'aws_rain_15m', 'aws_wind_speed')
WINDOWS = (60, 180, 720)
CHANGES = (60, 180)
HISTORY_FEATURES = [f'{c}_past_mean_{m}m' for c in HISTORY_COLUMNS for m in WINDOWS] + [f'{c}_change_{m}m' for c in HISTORY_COLUMNS for m in CHANGES]
FEATURES = list(DISTANCE_FREE_FEATURES) + HISTORY_FEATURES
BASELINE = 'equal_distance_mse_mae300'
MODELS = ('memory12_mse300', 'memory12_mae300')
CANDIDATES = (*MODELS, 'equal_memory_pair', 'equal_trio_memory')
REGIMES = tuple(f'{t}_{light}' for t in ('cold', 'transition', 'warm') for light in ('day', 'night'))


def weather_history(frame):
    """[t-w,t) 평균, 예정 슬롯80% 관측, 정확한60/180분 전 값으로 변화량 계산."""
    domain(frame)
    if frame.index.has_duplicates:
        raise ValueError('Unique input row index required')
    x = frame[list(HISTORY_COLUMNS)].astype(float)
    if np.isinf(x.to_numpy()).any():
        raise ValueError('Infinite weather history')
    result = pd.DataFrame(np.nan, index=frame.index, columns=HISTORY_FEATURES)
    for _, part in frame.groupby('station', sort=False):
        part = part.sort_values('time')
        values = x.loc[part.index].copy(); values.index = pd.DatetimeIndex(part.time)
        for c in HISTORY_COLUMNS:
            for minutes in WINDOWS:
                rolling = values[c].rolling(f'{minutes}min', closed='left', min_periods=1)
                means = rolling.mean().where(rolling.count() >= np.ceil(.8*minutes/10))
                result.loc[part.index, f'{c}_past_mean_{minutes}m'] = means.to_numpy()
            for minutes in CHANGES:
                previous = values[c].reindex(values.index-pd.Timedelta(minutes=minutes))
                result.loc[part.index, f'{c}_change_{minutes}m'] = values[c].to_numpy()-previous.to_numpy()
    return result


def model_features(frame):
    domain(frame)
    x = frame[FEATURES].astype(float)
    if np.isinf(x.to_numpy()).any():
        raise ValueError('Infinite temperature predictor')
    return x


def condition_bins(frame, prediction):
    """예측온도와 KST 시각만 사용한 사전 고정6구간. day는 시각 대용값이다."""
    domain(frame); p = np.asarray(prediction, float)
    if p.shape != (len(frame),) or np.isinf(p).any():
        raise ValueError('Aligned finite-or-missing predictions required')
    level = np.where(p < -2, 'cold', np.where(p <= 2, 'transition', 'warm'))
    hour = pd.to_datetime(frame.time).dt.hour.to_numpy()
    light = np.where((hour >= 6) & (hour < 18), 'day', 'night')
    bins = np.char.add(np.char.add(level, '_'), light).astype(object)
    bins[~np.isfinite(p)] = None
    return pd.Series(bins, index=frame.index, name='regime')


def calibrate_ranges(frame, prediction, conditional=False):
    """지점 균등90% 절대 OOF 오차. 부족한 조건은 전역 오차로 되돌린다."""
    global_radius, global_receipt = residual_radius(frame, prediction)
    result = {'global': dict(radius=global_radius, **global_receipt), 'conditions': {}, 'conditional': conditional,
              'minimum_rows': 500, 'minimum_stations': 2, 'guaranteed_coverage': False}
    if conditional:
        bins = condition_bins(frame, prediction); p = np.asarray(prediction, float)
        for key in REGIMES:
            mask = bins.eq(key).to_numpy() & np.isfinite(frame.road_temp.to_numpy(float))
            sub = frame.loc[mask]
            eligible = len(sub) >= 500 and sub.station.nunique() >= 2
            r, detail = residual_radius(sub, p[mask]) if eligible else (global_radius, global_receipt)
            result['conditions'][key] = dict(radius=r, calibration_n=len(sub), calibration_stations=sorted(sub.station.unique()),
                                             fallback_to_global=not eligible, radius_receipt=detail)
    return result


def apply_ranges(frame, prediction, calibration):
    bins = condition_bins(frame, prediction); p = np.asarray(prediction, float)
    radii = np.full(len(frame), calibration['global']['radius'])
    if calibration['conditional']:
        for key in REGIMES:
            radii[bins.eq(key).to_numpy()] = calibration['conditions'][key]['radius']
    return p-radii, p+radii


def range_gate(candidate, baseline):
    """평균 점수와 포함률, 지점 하한을 함께 확인하는 개발 적격 기준."""
    if candidate['n'] != baseline['n'] or set(candidate['stations']) != set(baseline['stations']):
        raise ValueError('Shared interval evaluation population required')
    return (candidate['station_macro_coverage'] >= .89 and min(s['coverage'] for s in candidate['stations'].values()) >= .80
            and candidate['near_freezing']['coverage'] >= .90
            and candidate['mean_interval_score'] < baseline['mean_interval_score']-1e-12
            and candidate['mean_width'] <= baseline['mean_width']*1.10+1e-12)
