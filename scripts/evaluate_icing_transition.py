"""결빙 전이 모델 30개를 지역 이중 제외로 학습하고 일별 F1 선택을 검증한다."""
import argparse
from datetime import datetime, timezone
from itertools import combinations
import json
from pathlib import Path
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.icing_transition import previous_training_state, transition_weights, forward_state_scores
from src.two_winter import validate, curve
from src.thermal_extended import feature_table as thermal_features
from src.solar_memory_search import feature_table as solar_features
from src.submission_runtime import FEATURES
from src.thermal_runtime import EXTRA
from src.runtime_metrics import runtime_daily
from src.extended_comparison import event_retention
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from scripts.evaluate_method_blending import preservation
from scripts.evaluate_thermal_classification import available, choose

CONFIG = ROOT / 'config/icing_transition_20261025.json'
KEYS = ['station', 'time', 'winter', 'group', 'ice', 'asos_air_temp']


def read(path):
    return json.loads(path.read_text('utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', 'utf-8')


def score_name(strength):
    return f'score_m{round(strength * 100)}'


def features(data, kind):
    return thermal_features(data, kind) if kind == 'thermal' else solar_features(data, kind)


def load_inputs(plan):
    columns = list(dict.fromkeys([*KEYS, *FEATURES, *EXTRA, 'asos_solar_altitude_deg', 'asos_solar_sine_positive']))
    data = validate(pd.read_parquet(ROOT / plan['data'], columns=columns)).sort_values(['station', 'time']).reset_index(drop=True)
    assert data.groupby('station').group.nunique().eq(1).all()
    baseline_path = ROOT / plan['baseline']
    baseline = validate(pd.read_parquet(baseline_path)).sort_values(['station', 'time']).reset_index(drop=True)
    assert sha(baseline_path) == read(baseline_path.parent / 'audit_runtime.json')['runtime_prediction_sha256']
    return data, baseline


def evaluate(out, plan, data, baseline):
    groups = sorted(set(data.group) - {'competition'})
    candidates, stores = [], {}
    for spec in plan['candidates']:
        for strength in plan['memory_strengths']:
            name = spec['name'] + '_m' + str(round(strength * 100))
            candidates.append(name)
            stores[name] = (spec['name'], score_name(strength))
    frames = {}
    def load(name, key):
        model, column = stores[name]
        cache_key = model, key
        if cache_key not in frames:
            frames[cache_key] = pd.read_parquet(out / model / ('__'.join(key) + '.parquet'))
        return frames[cache_key], column

    parts, decisions = [], {}
    for outer in groups:
        tables = []
        for name in [*candidates, 'asos_zero']:
            candidate = candidates[0] if name == 'asos_zero' else name
            chunks = []
            for held in groups:
                if held == outer:
                    continue
                f, column = load(candidate, tuple(sorted([outer, held])))
                q = f.loc[f.group.eq(held)].copy()
                q['selection_score'] = q.asos_air_temp.le(0).astype(float) if name == 'asos_zero' else q[column]
                chunks.append(q)
            inner = pd.concat(chunks, ignore_index=True)
            inner.loc[~inner.available, 'ice'] = np.nan
            scores = inner.selection_score.fillna(0).to_numpy()
            kwargs = {'thresholds': np.array([.5])} if name == 'asos_zero' else {}
            table = curve(inner, scores, **kwargs)
            table['mean_f1'] = table.f1_fixed_population
            yearly = [curve(inner.loc[inner.winter.eq(y)], scores[inner.winter.eq(y)], **kwargs).f1_fixed_population.to_numpy() for y in [2024, 2025]]
            table['worst_winter_f1'] = np.minimum(*yearly)
            table['candidate'] = name
            tables.append(table)
        table = pd.concat(tables, ignore_index=True)
        table.to_csv(out / (outer + '_selection.csv'), index=False)
        reference, _ = load(candidates[0], (outer,))
        result = reference[[*KEYS, 'available']].copy()
        result['asos_zero'] = np.where(result.available, result.asos_air_temp.le(0), np.nan)
        decisions[outer] = {'held_stations': sorted(result.station.unique()), 'selection_stations': sorted(inner.station.unique()), 'outer_labels_used_for_selection': False, 'choices': {}}
        for track in plan['selection_tracks']:
            for name in [*candidates, 'selected']:
                selected = choose(table if name == 'selected' else table.loc[table.candidate.eq(name)], track)
                chosen = selected['candidate']
                if chosen == 'asos_zero':
                    scores = result.asos_air_temp.le(0).to_numpy(float)
                else:
                    q, column = load(chosen, (outer,))
                    pd.testing.assert_frame_equal(q[['station', 'time']], result[['station', 'time']])
                    scores = q[column].to_numpy()
                key = name + '_' + track
                result[key] = np.where(result.available, scores >= selected['threshold'], np.nan)
                decisions[outer]['choices'][key] = selected
        parts.append(result)
        print('외부 지역 내부 선택 완료', outer, decisions[outer]['choices']['selected_mean_f1'], flush=True)

    combined = pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(combined[['station', 'time', 'ice']], baseline[['station', 'time', 'ice']])
    np.testing.assert_array_equal(combined.available, baseline.physical_both.notna())
    combined['current'] = baseline.physical_both.to_numpy()
    methods = [c for c in combined if c not in [*KEYS, 'available']]
    reports, stations_all, daily_all, regional = {}, [], [], []
    for name in methods:
        reports[name] = {}
        for year in ['all', 2024, 2025]:
            part = combined if year == 'all' else combined.loc[combined.winter.eq(year)]
            r, st, days = runtime_daily(part, part[name])
            reports[name][str(year)] = r
            if year == 'all':
                stations_all.append(st.assign(method=name))
                daily_all.append(days.assign(method=name))
        retention, events = event_retention(combined, combined[name], combined.current)
        reports[name]['events'] = retention
        events.to_csv(out / (name + '_events.csv'), index=False)
        for group, part in combined.groupby('group'):
            r, _, _ = runtime_daily(part, part[name])
            regional.append({'method': name, 'group': group, **r})
    stations = pd.concat(stations_all, ignore_index=True)
    old_station = stations.loc[stations.method.eq('current')].set_index('station').f1.fillna(0)
    old = reports['current']['all']
    for name in methods:
        new, r = reports[name]['all'], reports[name]
        st = stations.loc[stations.method.eq(name)].set_index('station').f1.fillna(0)
        gates = {
            'f1_improves': new['f1_fixed_population'] >= old['f1_fixed_population'] * 1.01,
            'precision_noninferior': new['precision_available_station_mean'] is not None and new['precision_available_station_mean'] >= old['precision_available_station_mean'],
            'recall_noninferior': new['recall_available_station_mean'] is not None and new['recall_available_station_mean'] >= old['recall_available_station_mean'],
            'each_winter': all(r[str(y)]['f1_fixed_population'] >= reports['current'][str(y)]['f1_fixed_population'] for y in [2024, 2025]),
            'each_station': bool(st.ge(old_station).all()),
            'events_preserved': r['events']['lost_events'] == 0,
            'beats_asos': new['f1_fixed_population'] > reports['asos_zero']['all']['f1_fixed_population'],
        }
        r['gates'], r['eligible'] = gates, all(gates.values())
        print('RESULT', name, round(new['f1_fixed_population'], 8), gates, flush=True)
    combined.to_parquet(out / 'predictions.parquet', index=False, compression='zstd')
    stations.to_csv(out / 'stations.csv', index=False)
    pd.concat(daily_all, ignore_index=True).to_csv(out / 'daily.csv', index=False)
    pd.DataFrame(regional).to_csv(out / 'regions.csv', index=False)
    write(out / 'decisions.json', decisions)
    return reports, len(combined)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(); out = args.output.resolve()
    if not out.is_relative_to((ROOT / 'outputs/private').resolve()):
        raise ValueError('Private experiment directory required')
    plan = read(CONFIG)
    dependencies = ['src/icing_transition.py', 'src/two_winter.py', 'src/solar_memory_search.py', 'src/thermal_extended.py', 'src/combined_thermal_history.py', 'src/runtime_metrics.py', 'src/extended_comparison.py', 'scripts/evaluate_thermal_classification.py']
    signatures = {p.relative_to(ROOT).as_posix(): sha(p) for p in [CONFIG, Path(__file__), ROOT / plan['data'], ROOT / plan['baseline'], *(ROOT / d for d in dependencies)]}
    if out.exists():
        assert read(out / 'plan.json')['signatures'] == signatures, 'Changed inputs or code: use a new experiment path'
        if (out / 'summary.json').exists():
            raise FileExistsError('Completed experiment is preserved')
    else:
        out.mkdir(parents=True)
        write(out / 'plan.json', {'settings': plan, 'signatures': signatures, 'started_at_utc': datetime.now(timezone.utc).isoformat()})
    frozen = preservation()
    data, baseline = load_inputs(plan)
    availability = available(data).to_numpy(bool)
    previous = previous_training_state(data, availability)
    groups = sorted(set(data.group) - {'competition'})
    assert len(groups) == 4
    contexts = [*((g,) for g in groups), *combinations(groups, 2)]
    receipts, cached = [], {}
    for spec in plan['candidates']:
        name, kind = spec['name'], spec['features']
        folder = out / name; folder.mkdir(exist_ok=True)
        if kind not in cached:
            cached[kind] = features(data, kind)
        x = cached[kind]
        for key in contexts:
            stem = '__'.join(key)
            modelpath, predpath, record = (folder / (stem + suffix) for suffix in ['.joblib', '.parquet', '.json'])
            query_mask = data.group.isin(key)
            training_mask = ~query_mask & np.isfinite(previous)
            train, query = data.loc[training_mask], data.loc[query_mask]
            assert not set(train.station) & set(query.station)
            if record.exists():
                receipt = read(record)
                assert sha(modelpath) == receipt['model_sha256'] and sha(predpath) == receipt['predictions_sha256']
            else:
                tx = x.loc[training_mask].copy()
                tx['previous_ice_state'] = previous[training_mask]
                weights = transition_weights(train, previous[training_mask], spec['weights'])
                prior = float(train.ice.mean())
                started = time.perf_counter()
                model = HistGradientBoostingClassifier(**plan['parameters'])
                with deny_network() as attempts, threadpool_limits(limits=plan['threads']):
                    model.fit(tx, train.ice.to_numpy(int), sample_weight=weights)
                    qx = x.loc[query_mask].copy(); qx['previous_ice_state'] = 0.
                    p0 = model.predict_proba(qx)[:, list(model.classes_).index(1)]
                    qx['previous_ice_state'] = 1.
                    p1 = model.predict_proba(qx)[:, list(model.classes_).index(1)]
                assert not attempts
                result = query[KEYS].copy().reset_index(drop=True)
                result['available'] = availability[query_mask]
                result['p0'], result['p1'] = p0, p1
                for strength in plan['memory_strengths']:
                    result[score_name(strength)] = forward_state_scores(result[['station', 'time']], p0, p1, result.available.to_numpy(), prior, strength)
                joblib.dump(model, modelpath, compress=3)
                result.to_parquet(predpath, index=False, compression='zstd')
                receipt = {'candidate': name, 'excluded_groups': list(key), 'training_rows': len(train), 'query_rows': len(query),
                           'training_stations': sorted(train.station.unique()), 'query_stations': sorted(query.station.unique()),
                           'features': list(tx), 'prior': prior, 'weights': spec['weights'], 'weight_min': float(weights.min()), 'weight_max': float(weights.max()),
                           'weight_mean': float(weights.mean()), 'model_sha256': sha(modelpath), 'predictions_sha256': sha(predpath),
                           'seconds': time.perf_counter() - started, 'protected_labels_read': False, 'observed_query_state_used': False}
                write(record, receipt)
                print('학습 완료', name, stem, round(receipt['seconds'], 1), flush=True)
            receipts.append(receipt)
            write(out / 'progress.json', {'completed_fits': len(receipts), 'planned_fits': 30, 'last_candidate': name, 'last_context': list(key)})
    write(out / 'fit_receipts.json', receipts)
    reports, rows = evaluate(out, plan, data, baseline)
    assert preservation() == frozen
    write(out / 'summary.json', {'status': 'icing_transition_development_complete', 'fits': len(receipts), 'rows': rows, 'reports': reports,
                                'protected_labels_read': False, 'new_independent_assessment': False, 'frozen_counts': frozen,
                                'completed_at_utc': datetime.now(timezone.utc).isoformat(),
                                'files': {p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*') if p.is_file()}})


if __name__ == '__main__':
    main()
