"""노면 관측 없이 기온·습도·풍속을 추정하기 위한 고정 입력과 수치 검증."""
import numpy as np
import pandas as pd

from src.observation_io import numeric_observations


TARGETS = ['air_temperature', 'relative_humidity', 'wind_speed']
SOURCE_FIELDS = dict(zip(TARGETS, ['air_temp', 'humidity', 'wind_speed']))
ASOS_FIELDS = ['air_temp', 'ground_temp', 'humidity', 'rain_mm', 'snow_cm',
               'cloud_tenths', 'solar_mj_m2', 'wind_speed', 'dewpoint_obs',
               'pressure', 'visibility', 'new_snow3h', 'soil5cm']
AWS_FIELDS = ['air_temp', 'humidity', 'wind_speed', 'rain_15m', 'dewpoint']


def clean_target(values, bounds):
    value = numeric_observations(values)
    return value.where(value.between(*bounds))


def allowed_csv(archive, member, allowed, columns):
    """식별자만 먼저 읽고 제외 행은 목표 열을 읽기 전에 건너뛴다.

    대회 일별 CSV는 한 관측당 한 물리 행이다. 합성 테스트에서도 차단 행의
    목표 값이 결과에 들어오지 않는지 확인한다. 전체 목표 열을 읽은 뒤 거르는
    방식은 보호 자료가 메모리에 들어오므로 사용하지 않는다.
    """
    station_column = '관측 지점번호'
    with archive.open(member) as stream:
        identifiers = pd.read_csv(stream, usecols=[station_column], dtype=str,
                                  encoding='utf-8-sig', keep_default_na=False)
    permitted = identifiers[station_column].str.strip().isin(set(allowed))
    skip = (np.flatnonzero(~permitted.to_numpy()) + 1).tolist()
    with archive.open(member) as stream:
        result = pd.read_csv(stream, usecols=columns, dtype=str, skiprows=skip,
                             encoding='utf-8-sig', keep_default_na=False)
    if len(result) != int(permitted.sum()):
        raise ValueError('CSV physical-row selection mismatch')
    if not set(result[station_column].str.strip()) <= set(allowed):
        raise ValueError('Blocked station entered target reader')
    return result.loc[:, columns], len(identifiers) - len(result)


def features(frame):
    """열 이름을 고정해 정답·지점 ID·겨울·사후 재분석의 혼입을 막는다."""
    x = pd.DataFrame(index=frame.index)
    asos_valid = frame.asos_age_minutes.between(0, 60, inclusive='right')
    aws_valid = frame.aws_age_minutes.between(0, 15, inclusive='right')
    for field in ASOS_FIELDS:
        x['asos_' + field] = frame['asos_' + field].where(asos_valid)
    for field in AWS_FIELDS:
        x['aws_' + field] = frame['aws_' + field].where(aws_valid)
    for column in ['asos_age_minutes', 'aws_age_minutes', 'hour_sin', 'hour_cos',
                   'season_sin', 'season_cos', 'asos_distance_km', 'aws_distance_km',
                   'solar_altitude_deg', 'solar_sine_positive']:
        x[column] = frame[column]
    for name, field in SOURCE_FIELDS.items():
        x['aws_asos_' + name + '_contrast'] = x['aws_' + field] - x['asos_' + field]
    x['asos_ground_air_contrast'] = x.asos_ground_temp - x.asos_air_temp
    x['asos_dewpoint_gap'] = x.asos_air_temp - x.asos_dewpoint_obs
    x['aws_dewpoint_gap'] = x.aws_air_temp - x.aws_dewpoint
    if np.isinf(x.to_numpy(float)).any():
        raise ValueError('Infinite predictor')
    return x.astype(float)


def baselines(frame, target):
    field = SOURCE_FIELDS[target]
    asos = frame['asos_' + field].where(frame.asos_age_minutes.between(0, 60, inclusive='right'))
    aws = frame['aws_' + field].where(frame.aws_age_minutes.between(0, 15, inclusive='right'))
    return asos.to_numpy(float), aws.fillna(asos).to_numpy(float)


def constrain(values, target):
    if target == 'relative_humidity':
        return np.clip(values, 0, 100)
    if target == 'wind_speed':
        return np.maximum(values, 0)
    return np.asarray(values, float)


def balanced_weights(frame):
    count = frame.groupby(['station', 'winter']).station.transform('size').to_numpy(float)
    value = 1 / count
    return value / value.mean()


def regression_numbers(observed, predicted):
    y = np.asarray(observed, float); p = np.asarray(predicted, float)
    good = np.isfinite(y) & np.isfinite(p); y = y[good]; p = p[good]
    if not len(y):
        return dict(n=0, mae=None, rmse=None, bias=None, correlation=None, r2=None)
    error = p-y
    variance = ((y-y.mean())**2).sum()
    corr = float(np.corrcoef(y, p)[0, 1]) if np.std(y)>0 and np.std(p)>0 else None
    return dict(n=len(y), mae=float(np.abs(error).mean()), rmse=float(np.sqrt((error**2).mean())),
                bias=float(error.mean()), correlation=corr,
                r2=float(1-(error**2).sum()/variance) if variance>0 else None)
