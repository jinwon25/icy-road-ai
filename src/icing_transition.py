"""학습한 기상 조건부 전이를 정답 없이 순방향으로 전달한다.

학습 때만 직전 유효 상태를 쓴다. 추론에는 두 가상 상태별 모델 점수와
지점·시각·입력 가용성만 전달하므로 보호 지점 정답을 요구하지 않는다.
"""
import numpy as np
import pandas as pd


def _keys(frame):
    if frame.empty or not {'station', 'time'} <= set(frame):
        raise ValueError('Nonempty station/time keys required')
    f = frame[['station', 'time']].reset_index(drop=True).copy()
    f['time'] = pd.to_datetime(f.time)
    if f.station.isna().any() or f.time.isna().any() or f.duplicated().any():
        raise ValueError('Unique nonmissing station/time keys required')
    if f.time.dt.tz is not None or not f.time.eq(f.time.dt.floor('10min')).all():
        raise ValueError('Naive KST 10-minute grid required')
    return f


def previous_training_state(frame, available):
    """같은 지점의 10분 연속·양쪽 유효 학습 행에서만 직전 상태를 반환한다."""
    f = _keys(frame)
    y = np.asarray(frame.ice, dtype=float)
    a = np.asarray(available)
    if a.dtype != bool or a.shape != (len(f),):
        raise ValueError('Aligned boolean availability required')
    if not np.isin(y[np.isfinite(y)], [0., 1.]).all() or np.isinf(y).any():
        raise ValueError('Binary or missing training outcomes required')
    f['y'], f['available'] = y, a
    result = np.full(len(f), np.nan)
    for _, part in f.groupby('station', sort=False):
        p = part.sort_values('time')
        continuous = p.time.diff().eq(pd.Timedelta(minutes=10))
        valid = continuous & p.available & p.available.shift(fill_value=False) & p.y.notna() & p.y.shift().notna()
        result[p.index[valid]] = p.y.shift().loc[valid]
    return result


def transition_weights(frame, previous, kind):
    """지점·겨울·전이형별 균등 가중치를 최대 20에서 절단한다."""
    p = np.asarray(previous, float)
    if p.shape != (len(frame),) or not np.isin(p, [0., 1.]).all() or not frame.ice.isin([0., 1.]).all():
        raise ValueError('Valid aligned transitions required')
    if kind == 'row':
        return np.ones(len(frame))
    if kind != 'station_transition':
        raise ValueError('Unplanned weighting')
    f = frame[['station', 'winter', 'ice']].reset_index(drop=True).copy()
    f['previous'] = p
    f['transition'] = 2 * p + f.ice.to_numpy()
    counts = f.groupby(['station', 'winter', 'transition']).ice.transform('size').to_numpy(float)
    strata = f.groupby(['station', 'winter']).transition.transform('nunique').to_numpy(float)
    w = 1. / (counts * strata)
    w /= w.mean()
    w = np.minimum(w, 20.)
    return w / w.mean()


def forward_state_scores(frame, p0, p1, available, prior, memory_strength=1.):
    """현재 기상 전이 점수로 과거 상태를 주변화한다. 미래 평활은 하지 않는다."""
    if set(frame) - {'station', 'time'}:
        raise ValueError('Inference accepts keys only, never observed outcomes')
    f = _keys(frame)
    a, b = np.asarray(p0, float), np.asarray(p1, float)
    valid = np.asarray(available)
    if valid.dtype != bool or valid.shape != (len(f),) or a.shape != valid.shape or b.shape != valid.shape:
        raise ValueError('Aligned scores and boolean availability required')
    if not np.isfinite(prior) or not 0 <= prior <= 1 or memory_strength not in [0., .5, 1.]:
        raise ValueError('Finite prior and planned memory strength required')
    if np.isinf(a).any() or np.isinf(b).any():
        raise ValueError('Infinite score')
    if not (np.isfinite(a[valid]).all() and np.isfinite(b[valid]).all() and
            ((a[valid] >= 0) & (a[valid] <= 1) & (b[valid] >= 0) & (b[valid] <= 1)).all()):
        raise ValueError('Available transition scores must be in [0, 1]')
    result = np.full(len(f), np.nan)
    for _, part in f.groupby('station', sort=False):
        state, last = float(prior), None
        p = part.sort_values('time')
        for i, time in zip(p.index, p.time.to_numpy(dtype='datetime64[ns]').view('int64')):
            if not valid[i]:
                state, last = float(prior), None
                continue
            if last is None or time - last != 600_000_000_000:
                state = float(prior)
            mixture = memory_strength * state + (1. - memory_strength) * prior
            state = (1. - mixture) * a[i] + mixture * b[i]
            result[i], last = state, time
    return result
