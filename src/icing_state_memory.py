"""순간 결빙 조건에 과거의 확인·짧은 지속을 적용하는 고정 개발 대조.

얼음 양·마찰·제설을 추정하는 물리 모델이 아니다. 결측이나 10분 격자 단절은 상태를 초기화한다.
"""
import numpy as np
import pandas as pd


def causal_ice_state(frame, prediction, temperature, confirmation=1, hold_minutes=0, release_c=0.):
    if confirmation not in (1, 2, 3) or hold_minutes not in (0, 30, 90) or release_c not in (0., 1.):
        raise ValueError('Only predeclared confirmation/hold/release settings allowed')
    if frame.empty or not frame.index.is_unique or frame.duplicated(['station', 'time']).any():
        raise ValueError('Unique nonempty station/time rows required')
    times = pd.to_datetime(frame.time)
    if times.isna().any() or times.dt.tz is not None or not times.eq(times.dt.floor('10min')).all():
        raise ValueError('Exact naive KST ten-minute grid required')
    p, t = np.asarray(prediction, float), np.asarray(temperature, float)
    if p.shape != (len(frame),) or t.shape != (len(frame),):
        raise ValueError('Aligned prediction and temperature required')
    if np.isinf(p).any() or np.isinf(t).any() or not np.isin(p[np.isfinite(p)], [0., 1.]).all():
        raise ValueError('Binary-or-missing prediction and finite-or-missing temperature required')
    f = frame[['station', 'time']].copy()
    f['_position'] = np.arange(len(f))
    output = np.full(len(f), np.nan)
    for _, part in f.groupby('station', sort=False):
        part = part.sort_values('time')
        stamp = part.time.to_numpy(dtype='datetime64[m]').astype(np.int64)
        indexes = part._position.to_numpy()
        last_time, last_trigger, run = None, None, 0
        for i, now in zip(indexes, stamp):
            if last_time is None or now - last_time != 10:
                run, last_trigger = 0, None
            last_time = now
            if not np.isfinite(p[i]) or not np.isfinite(t[i]):
                run, last_trigger = 0, None
                continue
            run = run + 1 if p[i] == 1 else 0
            trigger = run >= confirmation
            if trigger:
                last_trigger = now
            held = (last_trigger is not None and now - last_trigger <= hold_minutes
                    and t[i] <= release_c)
            output[i] = float(trigger or held)
            if not trigger and not held:
                last_trigger = None
    return output
