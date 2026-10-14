"""입력 배치 길이에 무관한 고정소수점 기상 이력. 이전 연구 원본을 보존한다."""
import numpy as np
import pandas as pd

from src.method_blending import domain
from src.weather_memory_temperature import (
    HISTORY_COLUMNS, WINDOWS, CHANGES, HISTORY_FEATURES, FEATURES, BASELINE,
    MODELS, CANDIDATES, REGIMES, model_features, condition_bins,
    calibrate_ranges, apply_ranges, range_gate,
)

SCALE = 1_000_000


def weather_history(frame):
    """기상값 소수6자리→정수 누적합→평균6자리. [t-w,t)·80%·정확한 lag 유지."""
    domain(frame)
    if frame.index.has_duplicates: raise ValueError('Unique input row index required')
    x = frame[list(HISTORY_COLUMNS)].to_numpy(float)
    if np.isinf(x).any() or np.any(np.abs(x[np.isfinite(x)]) > 100_000):
        raise ValueError('Finite weather values within fixed point bounds required')
    output = pd.DataFrame(np.nan, index=frame.index, columns=HISTORY_FEATURES)
    for _, f in frame.groupby('station', sort=False):
        f = f.sort_values('time')
        if len(f) > 1_000_000: raise ValueError('Fixed point cumulative sum safety bound')
        t = f.time.to_numpy(dtype='datetime64[ns]'); right = np.arange(len(f))
        for c in HISTORY_COLUMNS:
            raw = f[c].to_numpy(float); valid = np.isfinite(raw)
            integers = np.rint(np.where(valid, raw, 0.)*SCALE).astype(np.int64)
            total = np.r_[np.int64(0), np.cumsum(integers, dtype=np.int64)]
            counts = np.r_[np.int64(0), np.cumsum(valid, dtype=np.int64)]
            for minutes in WINDOWS:
                left = np.searchsorted(t, t-np.timedelta64(minutes, 'm'), side='left')
                n, sums = counts[right]-counts[left], total[right]-total[left]
                means = np.divide(sums, n*SCALE, out=np.full(len(raw), np.nan), where=n >= np.ceil(.8*minutes/10))
                output.loc[f.index, f'{c}_past_mean_{minutes}m'] = np.round(means, 6)
            for minutes in CHANGES:
                wanted = t-np.timedelta64(minutes, 'm'); ids = np.searchsorted(t, wanted)
                exact = (ids < len(t)) & (t[np.minimum(ids, len(t)-1)] == wanted)
                delta = np.full(len(raw), np.nan)
                usable = exact & valid & valid[np.minimum(ids, len(t)-1)]
                delta[usable] = (integers[usable]-integers[ids[usable]])/SCALE
                output.loc[f.index, f'{c}_change_{minutes}m'] = delta
    return output
