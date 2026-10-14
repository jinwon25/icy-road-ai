"""두 온도 추정의 합의·불일치를 비교한다. 임계값은 개발 가설이다."""
import numpy as np


def predict_consensus(first, second, moisture, fallback, aggregation='mean',
                      cold_threshold=0., dewpoint_margin=0.):
    a, b, old = (np.asarray(v, dtype=float) for v in (first, second, fallback))
    water = np.asarray(moisture, dtype=float)
    if a.ndim != 1 or b.shape != a.shape or old.shape != a.shape or water.shape != (len(a), 3):
        raise ValueError('Aligned predictions and three weather moisture columns required')
    if any(np.isinf(v).any() for v in [a, b, water]) or not np.isin(old, [0, 1]).all():
        raise ValueError('Clean finite-or-missing inputs and binary fallback required')
    if aggregation not in ['mean', 'coldest', 'warmest'] or not np.isfinite([cold_threshold, dewpoint_margin]).all():
        raise ValueError('Explicit finite decision policy required')
    t = (a+b)/2 if aggregation == 'mean' else np.minimum(a, b) if aggregation == 'coldest' else np.maximum(a, b)
    missing = ~np.isfinite(t) | np.isnan(water).all(axis=1)
    wet = (water[:, 0] >= t+dewpoint_margin) | (water[:, 1] > 0) | (water[:, 2] > 0)
    result = ((t <= cold_threshold) & wet).astype(np.int8)
    result[missing] = old[missing].astype(np.int8)
    return result, missing
