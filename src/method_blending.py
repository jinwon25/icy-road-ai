"""같은 모집단에서 온도·점수 결합과 세 단계 공간 제외를 검증한다."""
import numpy as np
import pandas as pd
from scipy.optimize import minimize

ALLOWED = frozenset('12103 12209 12210 12211 12409 23202 23203 23204 23403 33103 33206 33409 33410 33412 12207 12408 23205 23404 33205 33408 33207 33413 33414'.split())
COMPONENTS = ('direct_weather14', 'weather12_no_distance', 'residual_weather14', 'direct_thermal24',
              'residual_thermal24', 'weather_mae100', 'weather_mse300', 'weather_mae300', 'augmented_ridge')
BLENDS = ('equal_nine', 'equal_weather_trio', 'simplex_mse', 'simplex_shrink')


def domain(frame):
    if frame.empty or frame.duplicated(['station', 'time']).any() or not set(frame.station) <= ALLOWED:
        raise ValueError('Only unique allowed development rows permitted')
    times = pd.to_datetime(frame.time)
    if times.dt.tz is not None or times.isna().any() or not (times.ge('2024-11-01') & times.lt('2025-03-01')).all():
        raise ValueError('Only naive KST first-winter development permitted')
    if ((times.dt.minute % 10 != 0) | (times.dt.second != 0) | (times.dt.microsecond != 0) | (times.dt.nanosecond != 0)).any():
        raise ValueError('Exact ten-minute grid required')
    return frame


def validate_meta_origin(target_groups, excluded_groups, outer, inner=None):
    targets, excluded = set(target_groups), set(excluded_groups)
    required = targets | {outer} | ({inner} if inner is not None else set())
    if outer in targets or (inner is not None and inner in targets) or not required <= excluded:
        raise ValueError('Validation group entered base fitting for meta training')


def matrix(frame, columns=COMPONENTS):
    p = frame[list(columns)].to_numpy(dtype=float)
    if np.isinf(p).any() or not np.all(np.isfinite(p) == np.isfinite(p[:, :1])):
        raise ValueError('All component finite-row denominators must match')
    return p


def convex_predict(predictions, weights):
    p, w = np.asarray(predictions, float), np.asarray(weights, float)
    if p.ndim != 2 or w.shape != (p.shape[1],) or not np.isfinite(w).all():
        raise ValueError('Aligned components and weights required')
    if np.any(w < 0) or abs(w.sum()-1) > 1e-10:
        raise ValueError('Nonnegative weights summing to one required')
    if np.isinf(p).any() or not np.all(np.isfinite(p) == np.isfinite(p[:, :1])):
        raise ValueError('Shared finite-row denominator required')
    return p @ w


def objective_matrix(frame, penalty=0.):
    if not np.isfinite(penalty) or penalty < 0:
        raise ValueError('Nonnegative fixed penalty required')
    domain(frame); p = matrix(frame); y = frame.road_temp.to_numpy(float)
    valid = np.isfinite(y) & np.isfinite(p[:, 0])
    if not valid.any():
        raise ValueError('No valid meta training rows')
    counts = frame.loc[valid, 'station'].value_counts()
    a = frame.loc[valid, 'station'].map(1./counts).to_numpy()/len(counts)
    e = p[valid]-y[valid, None]
    gram = e.T @ (a[:, None]*e)
    return gram + penalty*np.eye(p.shape[1]), np.repeat(penalty/p.shape[1], p.shape[1]), int(valid.sum())


def fit_weights(frame, penalty=0.):
    q, b, n = objective_matrix(frame, penalty)
    size = q.shape[0]; uniform = np.ones(size)/size
    result = minimize(lambda w: float(w @ q @ w - 2*b @ w), uniform,
                      jac=lambda w: 2*(q @ w-b), method='SLSQP', bounds=[(0., 1.)]*size,
                      constraints={'type': 'eq', 'fun': lambda w: w.sum()-1., 'jac': lambda w: np.ones(size)},
                      options={'ftol': 1e-12, 'maxiter': 1000})
    if not result.success or np.min(result.x) < -1e-10 or abs(result.x.sum()-1) > 1e-8:
        raise ValueError('Convex meta optimization failed')
    w = np.maximum(result.x, 0); w /= w.sum()
    return w, {'valid_rows': n, 'penalty': penalty, 'weights': w.tolist(),
               'objective_without_constant': float(w @ q @ w-2*b @ w), 'iterations': int(result.nit)}


def temperature_gate(candidate, baseline, harm=.05):
    if set(candidate['stations']) != set(baseline['stations']):
        raise ValueError('Different station population')
    for s in baseline['stations']:
        if candidate['stations'][s]['n'] != baseline['stations'][s]['n']:
            raise ValueError('Different finite station denominator')
    if candidate['near_freezing']['n'] != baseline['near_freezing']['n']:
        raise ValueError('Different near-freezing denominator')
    if not baseline['pooled']['n'] or not baseline['near_freezing']['n']:
        return False
    return (all(candidate['station_macro'][m] < baseline['station_macro'][m]-1e-12 for m in ('mae', 'rmse'))
            and all(candidate['stations'][s]['mae'] <= baseline['stations'][s]['mae']*(1+harm)+1e-12 for s in baseline['stations'])
            and candidate['near_freezing']['mae'] <= baseline['near_freezing']['mae']+1e-12)


def choose_temperature(reports, harm=.05):
    eligible = [c for c in BLENDS if temperature_gate(reports[c], reports['direct_weather14'], harm)]
    return min(eligible, key=lambda c: (reports[c]['station_macro']['mae'], reports[c]['station_macro']['rmse'], c)) if eligible else 'direct_weather14'


def combine_binary(first, second, operation):
    a, b = np.asarray(first), np.asarray(second)
    if a.ndim != 1 or a.shape != b.shape or not np.isin(a, [0, 1]).all() or not np.isin(b, [0, 1]).all():
        raise ValueError('Aligned binary predictions required')
    if operation not in ('and', 'or'):
        raise ValueError('Only fixed AND/OR operations permitted')
    return np.minimum(a, b) if operation == 'and' else np.maximum(a, b)


def ice_guard(candidate, baseline, candidate_stations, baseline_stations):
    cs, bs = candidate_stations.set_index('station'), baseline_stations.set_index('station')
    populations = ['n', 'complete_days', 'fixed_ice_days', 'fixed_ice_day_stations', 'events', 'single_slot_events']
    if set(cs.index) != set(bs.index) or any(candidate[k] != baseline[k] for k in populations):
        raise ValueError('Ice comparison population differs')
    if not cs.n.eq(bs.n).all() or not (cs.tp+cs.fn).eq(bs.tp+bs.fn).all():
        raise ValueError('Station label denominators differ')
    metrics = ['f1', 'fixed_station_f1_zero_undefined', 'fixed_ice_day_f1', 'provisional_daily_station_f1']
    supported = all(candidate[k] is not None and baseline[k] is not None for k in metrics)
    checks = {'supported_metrics': supported,
              'fp_nonincrease': candidate['fp'] <= baseline['fp'], 'fn_nonincrease': candidate['fn'] <= baseline['fn'],
              'every_positive_station_tp': bool(cs.loc[(bs.tp+bs.fn).gt(0), 'tp'].ge(bs.loc[(bs.tp+bs.fn).gt(0), 'tp']).all()),
              'events_nonincrease_misses': candidate['detected_events'] >= baseline['detected_events'],
              'singles_nonincrease_misses': candidate['detected_single_slot_events'] >= baseline['detected_single_slot_events'],
              'f1_nonworse': supported and all(candidate[k]+1e-12 >= baseline[k] for k in metrics),
              'strict_improvement': supported and (candidate['fp'] < baseline['fp'] or candidate['fn'] < baseline['fn'] or any(candidate[k] > baseline[k]+1e-12 for k in metrics))}
    return all(checks.values()), checks
