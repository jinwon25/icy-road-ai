"""v3 이후의 긴 기상 이력·결빙점 가중 대조. 도로 정답은 가중 학습에만 쓴다."""
import numpy as np
import pandas as pd

from src.solar_memory_search import feature_table as solar_features

LONG_MEMORY_COLUMNS = (
    'asos_air_temp', 'asos_ground_temp', 'asos_cloud_tenths', 'asos_solar_mj_m2',
)


def long_memory(frame, windows=(1440, 2880)):
    """[t-window, t) 관측만 집계하며 기대 10분 슬롯의 80%를 요구한다."""
    if frame.empty or not frame.index.is_unique or frame.duplicated(['station', 'time']).any():
        raise ValueError('Unique nonempty station/time rows required')
    times = pd.to_datetime(frame.time)
    if times.isna().any() or times.dt.tz is not None or not times.eq(times.dt.floor('10min')).all():
        raise ValueError('Exact naive KST ten-minute grid required')
    if not windows or any(w not in (1440, 2880) for w in windows) or len(set(windows)) != len(windows):
        raise ValueError('Only distinct fixed 24/48-hour windows allowed')
    columns = [f'{c}_prior_mean_{w}m' for c in LONG_MEMORY_COLUMNS for w in windows]
    output = pd.DataFrame(np.nan, index=frame.index, columns=columns)
    for _, part in frame.groupby('station', sort=False):
        part = part.sort_values('time')
        if len(part) > 1_000_000:
            raise ValueError('Fixed-point safety bound exceeded')
        t = part.time.to_numpy(dtype='datetime64[ns]')
        right = np.arange(len(part))
        for column in LONG_MEMORY_COLUMNS:
            values = part[column].to_numpy(float)
            good = np.isfinite(values)
            if np.isinf(values).any() or (np.abs(values[good]) > 100_000).any():
                raise ValueError('Invalid weather values')
            integers = np.rint(np.where(good, values, 0) * 1_000_000).astype(np.int64)
            sums = np.r_[np.int64(0), np.cumsum(integers, dtype=np.int64)]
            counts = np.r_[np.int64(0), np.cumsum(good, dtype=np.int64)]
            for window in windows:
                left = np.searchsorted(t, t - np.timedelta64(window, 'm'), side='left')
                n = counts[right] - counts[left]
                total = sums[right] - sums[left]
                result = np.divide(total, n * 1_000_000, out=np.full(len(part), np.nan),
                                   where=n >= np.ceil(.8 * window / 10))
                output.loc[part.index, f'{column}_prior_mean_{window}m'] = np.round(result, 6)
    return output


def feature_table(frame, kind='combined_asos_solar'):
    if kind not in ('combined_asos_solar', 'solar_long24', 'solar_long48'):
        raise ValueError('Unknown follow-up feature set')
    base = solar_features(frame, 'combined_asos_solar')
    if kind == 'combined_asos_solar':
        return base
    extra = long_memory(frame, (1440,) if kind == 'solar_long24' else (1440, 2880))
    return pd.concat([base, extra], axis=1)


def training_weights(frame, spec):
    if not spec.get('cold_weight'):
        return None
    if spec['cold_weight'] != 'exp_sigma3_floor01':
        raise ValueError('Unknown fixed temperature weight')
    target = frame.road_temp.to_numpy(float)
    if not np.isfinite(target).all():
        raise ValueError('Finite training targets required for weights')
    # 같은 시각 추정이므로 예측 선행시간 항은 없다. 추론에서 정답을 요구하지 않는다.
    return np.clip(np.exp(-np.square(target / 3.0)), .1, 1.)
