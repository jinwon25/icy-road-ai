"""외부 첫 겨울 온도 보강의 고정 혼합·동일 분모·그룹 선택."""
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.validation import assert_training_stations, regression_metrics


def join_training_temperatures(features, thermal, allowed_stations):
    if 'road_temp' in features:
        raise ValueError('Temperature outcomes must be joined separately from classification inputs')
    allowed = set(map(str, allowed_stations))
    assert_training_stations(allowed)
    if not set(features.station) <= allowed or not set(thermal.station) <= allowed:
        raise ValueError('Only development donor temperature outcomes accepted')
    if thermal.duplicated(['station', 'time']).any():
        raise ValueError('Duplicate donor temperature outcome')
    result = features.merge(thermal[['station', 'time', 'road_temp']], on=['station', 'time'], how='left', validate='one_to_one')
    if len(result) != len(features):
        raise ValueError('Temperature outcome join changed feature rows')
    return result


def fit_weather_temperature(frame, features, alpha=100.):
    if set(features) & {'ice', 'state_raw', 'road_temp'}:
        raise ValueError('Target measurements cannot be predictor columns')
    train = frame.loc[frame.road_temp.notna() & frame.asos_air_temp.notna()]
    if train.empty:
        raise ValueError('No valid training temperatures')
    model = make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                          StandardScaler(), Ridge(alpha=alpha))
    model.fit(train[list(features)], train.road_temp)
    return model, train


def predict_temperature(model, frame, features):
    weather = model.predict(frame[list(features)])
    neighbor = frame.neighbor_road_temp.to_numpy()
    blend = np.where(np.isfinite(neighbor), .5 * (weather + neighbor), weather)
    return np.where(frame.asos_air_temp.notna(), blend, np.nan)


def paired_temperature_metrics(frame, baseline, candidate):
    base, selected = np.asarray(baseline), np.asarray(candidate)
    valid = frame.road_temp.notna().to_numpy() & np.isfinite(base) & np.isfinite(selected)
    return {'shared_valid_rows': int(valid.sum()),
            'baseline': regression_metrics(frame.road_temp.to_numpy()[valid], base[valid]),
            'candidate': regression_metrics(frame.road_temp.to_numpy()[valid], selected[valid])}


def select_temperature_candidate(rows, held_group):
    comparisons = [row for row in rows if row['outer_held_group'] == held_group and row['validation_group'] != held_group]
    if len(comparisons) != 3 or len({row['validation_group'] for row in comparisons}) != 3:
        raise ValueError('Exactly three other-group comparisons required')
    totals = {name: {'n': 0, 'absolute': 0., 'squared': 0., 'signed': 0.} for name in ('baseline', 'candidate')}
    for row in comparisons:
        if not {held_group, row['validation_group']} <= set(row['training_excluded_groups']):
            raise ValueError('Held groups influenced temperature fitting')
        for name in totals:
            result = row[name]; n = result['n']
            if n != row['shared_valid_rows'] or n != row['baseline']['n']:
                raise ValueError('Different temperature validation rows')
            if n:
                totals[name]['n'] += n
                totals[name]['absolute'] += result['mae'] * n
                totals[name]['squared'] += result['rmse'] ** 2 * n
                totals[name]['signed'] += result['bias'] * n
    metrics = {}
    for name, total in totals.items():
        n = total['n']
        metrics[name] = {'n': n, 'mae': total['absolute']/n if n else None,
                         'rmse': (total['squared']/n)**.5 if n else None, 'bias': total['signed']/n if n else None}
    base, candidate = metrics['baseline'], metrics['candidate']
    improved = bool(base['n'] and candidate['mae'] < base['mae'] and candidate['rmse'] < base['rmse'])
    return {'held_group': held_group, 'selected_candidate': 'augmented_weather_ridge' if improved else 'baseline',
            'selection_groups': sorted(row['validation_group'] for row in comparisons),
            'selection_excludes_held_group': True, 'require_both_mae_rmse_improvement': True,
            'selection_metrics': metrics, 'reserved_validation_opened': False}
