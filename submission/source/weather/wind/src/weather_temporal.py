"""지역·겨울 동시 제외 검증과 목표 관측을 사용하지 않는 과거 기상 이력."""
import numpy as np
import pandas as pd

from src.road_weather_transfer import features


HISTORY_FIELDS = ['asos_air_temp', 'asos_ground_temp', 'asos_humidity',
                  'asos_wind_speed', 'asos_solar_mj_m2', 'aws_air_temp',
                  'aws_humidity', 'aws_wind_speed']
WINDOWS = {3: 6, 24: 48}


def temporal_features(frame):
    """각 도로·겨울의 (t-window, t]만 사용한다. 현재 입력도 이미 과거 연결값이다.

    coverage는 유효 10분 입력 행 비율이며 독립 기상 관측 개수가 아니다.
    긴 관측 공백을 메우거나 다른 겨울·도로에서 이력을 빌리지 않는다.
    """
    if not frame.index.equals(pd.RangeIndex(len(frame))):
        raise ValueError('Reset source index required')
    if frame[['station', 'winter', 'time']].isna().any().any():
        raise ValueError('Complete history keys required')
    if frame.duplicated(['station', 'time']).any():
        raise ValueError('Unique station timestamps required')
    base = features(frame)
    result = base.copy()
    for hours in WINDOWS:
        for field in HISTORY_FIELDS:
            for kind in ['mean', 'departure', 'coverage']:
                result[f'{field}_{kind}_{hours}h'] = np.nan
    for _, part in frame.groupby(['station', 'winter'], sort=True):
        order = part.sort_values('time').index
        times = pd.DatetimeIndex(part.loc[order, 'time'])
        if len(times) > 1 and np.any(np.diff(times.asi8) < pd.Timedelta(minutes=10).value):
            raise ValueError('History inputs must be at least ten minutes apart')
        current = base.loc[order, HISTORY_FIELDS].set_axis(times)
        for hours, minimum in WINDOWS.items():
            rolling = current.rolling(f'{hours}h', closed='right', min_periods=minimum)
            means = rolling.mean()
            counts = current.rolling(f'{hours}h', closed='right', min_periods=0).count()
            for field in HISTORY_FIELDS:
                result.loc[order, f'{field}_mean_{hours}h'] = means[field].to_numpy()
                result.loc[order, f'{field}_departure_{hours}h'] = (current[field]-means[field]).to_numpy()
                result.loc[order, f'{field}_coverage_{hours}h'] = counts[field].to_numpy()/(hours*6)
    if np.isinf(result.to_numpy()).any():
        raise ValueError('Infinite history input')
    return base, result


def split_masks(frame, valid, held, query_winter):
    """평가 지역의 두 겨울 정답과 평가 겨울의 모든 정답을 학습에서 제외한다."""
    valid = np.asarray(valid, bool)
    if valid.shape != (len(frame),) or query_winter not in [2024, 2025]:
        raise ValueError('Aligned validity and known winter required')
    train = valid & frame.group.ne(held).to_numpy() & frame.winter.ne(query_winter).to_numpy()
    query = valid & frame.group.eq(held).to_numpy() & frame.winter.eq(query_winter).to_numpy()
    if not train.any() or not query.any():
        raise ValueError('Empty space-time split')
    if set(frame.loc[train, 'station']) & set(frame.loc[query, 'station']):
        raise ValueError('Station leakage across regions')
    if set(frame.loc[train, 'winter']) & set(frame.loc[query, 'winter']):
        raise ValueError('Winter leakage')
    return train, query
