"""고정 개발 예측의 날짜 구성 민감도. 새 지점 일반화의 신뢰구간이 아니다."""
import numpy as np


def circular_day_indices(days, block_days, repetitions, seed):
    if any(isinstance(x, bool) or int(x) != x for x in (days, block_days, repetitions)):
        raise ValueError('Integer dimensions required')
    if not 1 <= block_days <= days or repetitions < 1:
        raise ValueError('Positive valid block dimensions required')
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, days, size=(repetitions, int(np.ceil(days / block_days))))
    return ((starts[..., None] + np.arange(block_days)) % days).reshape(repetitions, -1)[:, :days]


def paired_macro_resamples(numerators, denominators, indices):
    """[모델, 지점, 날짜] 집계에 같은 날짜 인덱스를 적용하고 지점 균등 평균."""
    a, b = np.asarray(numerators, float), np.asarray(denominators, float)
    ids = np.asarray(indices)
    if a.ndim != 3 or a.shape != b.shape or ids.ndim != 2 or not np.issubdtype(ids.dtype, np.integer):
        raise ValueError('Aligned model/station/day arrays and integer day indices required')
    if not np.isfinite(a).all() or not np.isfinite(b).all() or (b < 0).any() or (ids < 0).any() or (ids >= a.shape[2]).any():
        raise ValueError('Finite aggregates, nonnegative counts and valid day indices required')
    top = a[:, :, ids].sum(axis=-1)
    bot = b[:, :, ids].sum(axis=-1)
    means = np.divide(top, bot, out=np.full_like(top, np.nan), where=bot > 0)
    valid = np.isfinite(means)
    n = valid.sum(axis=1)
    values = np.divide(np.nansum(means, axis=1), n, out=np.full((a.shape[0], len(ids)), np.nan), where=n > 0)
    return values, n
