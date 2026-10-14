"""공간 제외 OOF 오차의 경험적 범위. 교환가능성이나 보장된 신뢰구간을 주장하지 않는다."""
import numpy as np
from src.method_blending import domain


def residual_radius(frame, prediction, nominal=.9):
    domain(frame)
    if not 0 < nominal < 1:
        raise ValueError('Interior nominal fraction required')
    p, y = np.asarray(prediction, float), frame.road_temp.to_numpy(float)
    if p.shape != y.shape or np.isinf(p).any():
        raise ValueError('Aligned finite-or-missing predictions required')
    valid = np.isfinite(p) & np.isfinite(y)
    if not valid.any():
        raise ValueError('No calibration residuals')
    stations = frame.loc[valid, 'station']; counts = stations.value_counts()
    weights = stations.map(1./counts).to_numpy()/len(counts)
    errors = np.abs(p[valid]-y[valid]); order = np.argsort(errors, kind='stable')
    cumulative = np.cumsum(weights[order]); cumulative /= cumulative[-1]
    radius = errors[order][np.searchsorted(cumulative, nominal, side='left')]
    return float(radius), dict(n=int(valid.sum()), stations=sorted(counts.index), nominal_fraction=nominal,
                              station_balanced=True, guaranteed_coverage=False)


def empirical_interval(prediction, radius):
    p = np.asarray(prediction, float)
    if p.ndim != 1 or np.isinf(p).any() or not np.isfinite(radius) or radius < 0:
        raise ValueError('Finite nonnegative radius and aligned vector required')
    return p-radius, p+radius


def interval_report(frame, prediction, lower, upper, nominal=.9):
    domain(frame)
    y, p, lo, hi = frame.road_temp.to_numpy(float), np.asarray(prediction, float), np.asarray(lower, float), np.asarray(upper, float)
    if any(v.shape != y.shape for v in [p, lo, hi]) or not np.array_equal(np.isfinite(p), np.isfinite(lo)) or not np.array_equal(np.isfinite(p), np.isfinite(hi)):
        raise ValueError('Shared interval population required')
    valid = np.isfinite(y) & np.isfinite(p)
    if np.any(lo[valid] > hi[valid]):
        raise ValueError('Reversed interval')
    d = frame.loc[valid, ['station']].copy()
    yy, ll, hh = y[valid], lo[valid], hi[valid]
    d['coverage'] = ((ll <= yy) & (yy <= hh)).astype(float)
    d['width'] = hh-ll
    d['interval_score'] = hh-ll+2/(1-nominal)*(np.maximum(ll-yy, 0)+np.maximum(yy-hh, 0))
    stations = {s: dict(n=len(part), **{c: float(part[c].mean()) for c in ['coverage', 'width', 'interval_score']}) for s, part in d.groupby('station')}
    near = np.abs(yy) <= 2
    cold, warm = hh <= 0, ll > 0
    return dict(n=len(d), nominal_fraction=nominal, pooled_coverage=float(d.coverage.mean()),
                station_macro_coverage=float(np.mean([r['coverage'] for r in stations.values()])),
                mean_width=float(d.width.mean()), mean_interval_score=float(d.interval_score.mean()), stations=stations,
                near_freezing=dict(n=int(near.sum()), coverage=float(d.coverage.to_numpy()[near].mean()) if near.any() else None),
                temperature_boundary=dict(cold_decisive_rows=int(cold.sum()), warm_decisive_rows=int(warm.sum()),
                                          ambiguous_rows=int((~cold & ~warm).sum()), false_cold_rows=int((cold & (yy > 0)).sum()), false_warm_rows=int((warm & (yy <= 0)).sum())),
                guaranteed_coverage=False, official_ice_probability=False)
