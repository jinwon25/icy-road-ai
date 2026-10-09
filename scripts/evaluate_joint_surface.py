"""그룹을 제외해 추정한 온도로 이진 결빙과 다중 노면상태 분류를 비교한다."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import average_precision_score
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.joint_surface import (FEATURES, WEATHER, eligibility, excluded_stations, ice_probability,
                              select_threshold, state_classes, thermal_features,
                              threshold_prediction, threshold_table, unit_blocks)
from src.thermal_ice import diagnostic_report, fixed_thermal_rule, validate_development
from src.validation import normalize_state
from src.external_reserved import verify_reserved_freeze
from src.frozen_assessment import verify_freeze

PARAMS = dict(learning_rate=.05, max_iter=100, max_leaf_nodes=15, min_samples_leaf=100,
              l2_regularization=10., early_stopping=False, random_state=20260923)
CANDIDATES = ['binary_thermal_weather', 'joint_surface_state']
PLAN = dict(experiment_id='20261009_nested_crossfit_joint_surface_v1',
            period_kst=['2024-11-01', '2025-02-28'], candidates=CANDIDATES,
            features=FEATURES, regression_features=WEATHER, parameters=PARAMS, ice_weight=20.,
            state_classes={'dry': ['01'], 'wet_damp': ['02', '11', '14'], 'snow': ['03'],
                           'chemical_wet': ['12'], 'critical_wet': ['13'], 'snow_ice': ['15'],
                           'ice': ['04'], 'other': ['10']},
            official_positive='04 only; unknown states excluded, not relabelled',
            auxiliary_folds='18 outcome-independent spatial units sorted by name, modulo 3. Competition station is a unit; each external spatial group is one unit.',
            auxiliary_training='Every training temperature excludes its entire unit block AND outer/inner held-out groups. Query temperature excludes outer/inner groups. Finite temperature + ASOS domain only.',
            reuse='Previously audited HGB temperature models may be reused only with identical rows, features, parameters, station exclusions and SHA256.',
            threshold='403 fixed points: 0, geomspace(1e-6,1,401), nextafter(1,2). Max inner actual-ice-day station macro F1 subject to FP <= inner thermal/moisture baseline; tie micro F1 then higher threshold.',
            eligibility='Inner micro F1, actual-ice-day F1 and fixed station F1 must not decrease; micro or ice-day must strictly improve; FP and detected single-slot events must not worsen; each station with >=5 Ice rows must not lose TP.',
            selection='Eligible candidate with highest inner ice-day F1, micro F1, then lexicographic name; otherwise thermal_moisture. No choices from outer labels.',
            fallback='Nonfinite estimated query temperature uses old competition-only baseline score and prediction for every candidate and threshold.',
            banned_predictors=['actual target temperature', 'actual target state', 'station ID', 'sensor kind', 'neighbor road temperature', 'neighbor state'],
            scope='Repeated first-winter development only; not independent, official or deployment validation.',
            protected_or_reserved_outcomes_used=False, max_compute_threads=2,
            versions=dict(sklearn=sklearn.__version__, numpy=np.__version__, pandas=pd.__version__))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(2 ** 20), b''):
            h.update(block)
    return h.hexdigest()


def identity(frame):
    return hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).values.tobytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='새 outputs/private 실험 폴더')
    args = parser.parse_args()
    out = args.output.resolve(); private = ROOT / 'outputs/private'
    if not out.is_relative_to(private.resolve()):
        parser.error('Results must stay inside outputs/private')
    if out.exists():
        raise FileExistsError('Preserve all previous experiments; choose a new output directory')
    release = private / 'releases/20261007'
    frozen_external = verify_reserved_freeze(release, release / 'outputs/private/external_reserved_predictions_v1')
    frozen_original = verify_freeze(release)
    out.mkdir(parents=True)
    write(out / 'experiment_plan.json', PLAN)
    shutil.copy2(__file__, out / 'analysis_source.py')
    shutil.copy2(ROOT / 'src/joint_surface.py', out / 'joint_surface_source.py')
    source = private / 'ice_group_balanced_20261009_v1'
    temperature_run = private / 'weather_fallback_20261009_v1'
    paths = dict(development_index=source / 'development_index.parquet', features=source / 'feature_matrix.parquet',
                 old_predictions=source / 'outer_predictions.parquet', temperature_index=temperature_run / 'training_index.parquet',
                 temperature_features=temperature_run / 'weather_features.parquet',
                 temperature_receipts=temperature_run / 'fit_receipts.json',
                 temperature_audit=temperature_run / 'independent_verification.json',
                 thermal_predictions=private / 'thermal_ice_diagnostics_20261009_v1/predictions.parquet')
    write(out / 'input_signature.json', {k: dict(path=str(p), sha256=sha(p)) for k, p in paths.items()})
    if read(paths['temperature_audit'])['status'] != 'passed':
        raise ValueError('Reuse requires a completed independent temperature audit')
    index = validate_development(pd.read_parquet(paths['development_index']))
    temp = pd.read_parquet(paths['temperature_index'])
    pd.testing.assert_frame_equal(index[['station', 'time', 'group']], temp[['station', 'time', 'group']])
    weather = pd.read_parquet(paths['features'])[WEATHER + ['rain15_max_3h', 'asos_snow_cm']]
    pd.testing.assert_frame_equal(weather[WEATHER], pd.read_parquet(paths['temperature_features']))
    if not np.array_equal(index.ice.to_numpy(dtype=float), index.state_raw.map(normalize_state).to_numpy(dtype=float), equal_nan=True):
        raise ValueError('Official code 04-only labels changed')
    classes = state_classes(index.state_raw)
    assert np.array_equal(np.isfinite(classes), index.ice.notna())
    assert np.array_equal(classes[np.isfinite(classes)] == 6, index.ice.dropna().eq(1))
    groups = sorted(set(index.group) - {'competition'})
    blocks = unit_blocks(index)
    assert len(groups) == 4 and len(set(index.station)) == 23
    write(out / 'unit_blocks.json', blocks)
    old = pd.read_parquet(paths['old_predictions'])
    old = old.set_index(['station', 'time'])
    external = index.group.ne('competition')
    old = old.reindex(pd.MultiIndex.from_frame(index.loc[external, ['station', 'time']]))
    assert old.baseline_score.notna().all() and old.baseline_prediction.notna().all()
    base_pred = pd.Series(np.nan, index=index.index); base_score = base_pred.copy()
    base_pred.loc[external] = old.baseline_prediction.to_numpy(); base_score.loc[external] = old.baseline_score.to_numpy()
    receipts = []; contexts = {}; temperature_cache = {}
    previous_receipts = [r for r in read(paths['temperature_receipts']) if r['candidate'] == 'augmented_hgb']
    domain = np.isfinite(temp.road_temp) & weather.asos_air_temp.notna()
    started = time.perf_counter()

    def temperature_model(forbidden, allow_reuse=True):
        key = tuple(sorted(forbidden))
        if key in temperature_cache:
            return temperature_cache[key]
        mask = domain & ~index.station.isin(forbidden)
        training_id = identity(temp.loc[mask, ['station', 'time', 'road_temp']])
        matches = [r for r in previous_receipts if set(r['forbidden_stations']) == forbidden]
        if allow_reuse and matches:
            r = matches[0]; path = temperature_run / r['model_path']
            assert r['training_identity'] == training_id and r['training_rows'] == int(mask.sum())
            assert set(r['training_stations']) == set(index.loc[mask, 'station']) and r['features'] == WEATHER
            assert sha(path) == r['model_sha256']
            model = joblib.load(path)
            assert all(model.get_params()[k] == v for k, v in PARAMS.items())
            record = dict(kind='temperature', reused=True, model_path=str(path), model_sha256=sha(path),
                          forbidden_stations=list(key), training_identity=training_id, training_rows=int(mask.sum()),
                          training_stations=sorted(set(index.loc[mask, 'station'])), features=WEATHER)
        else:
            model = HistGradientBoostingRegressor(**PARAMS)
            tick = time.perf_counter()
            with threadpool_limits(limits=2):
                model.fit(weather.loc[mask, WEATHER], temp.loc[mask, 'road_temp'])
            folder = out / 'temperature_models'; folder.mkdir(exist_ok=True)
            path = folder / (hashlib.sha256('|'.join(key).encode()).hexdigest()[:20] + '.joblib')
            joblib.dump(model, path, compress=3)
            record = dict(kind='temperature', reused=False, model_path=str(path), model_sha256=sha(path),
                          forbidden_stations=list(key), training_identity=training_id, training_rows=int(mask.sum()),
                          training_stations=sorted(set(index.loc[mask, 'station'])), features=WEATHER,
                          fit_seconds=time.perf_counter() - tick)
            print(f'Temperature fit: excluded {len(key)} stations, rows={mask.sum()}, seconds={record["fit_seconds"]:.1f}', flush=True)
        receipts.append(record); write(out / 'fit_receipts.json', receipts)
        temperature_cache[key] = (model, record)
        return model, record

    def estimate(model, rows):
        with threadpool_limits(limits=2):
            values = model.predict(weather.loc[rows, WEATHER])
        return np.where(weather.loc[rows].asos_air_temp.notna(), values, np.nan)

    def context(forbidden_groups):
        key = tuple(sorted(forbidden_groups))
        if key in contexts:
            return contexts[key]
        folder = out / 'contexts' / '__'.join(key); folder.mkdir(parents=True)
        forbidden = excluded_stations(index, key)
        train = ~index.station.isin(forbidden) & index.ice.notna()
        query = index.station.isin(forbidden)
        oof = pd.Series(np.nan, index=index.index); assignment = pd.Series(-1, index=index.index)
        auxiliary_receipts = []
        for block in range(3):
            excluded = excluded_stations(index, key, blocks, block)
            rows = train & index.station.map(blocks).eq(block)
            if not rows.any():
                continue
            model, receipt = temperature_model(excluded, allow_reuse=False)
            assert not set(index.loc[rows, 'station']) & set(receipt['training_stations'])
            oof.loc[rows] = estimate(model, rows); assignment.loc[rows] = block
            auxiliary_receipts.append(dict(block=block, receipt=receipt))
        assert assignment[train].ge(0).all()
        full, full_receipt = temperature_model(forbidden)
        query_temperature = estimate(full, query)
        train_x = thermal_features(weather.loc[train], oof.loc[train])
        query_x = thermal_features(weather.loc[query], query_temperature)
        saved_train = index.loc[train].copy(); saved_train['original_index'] = saved_train.index
        saved_train['auxiliary_block'] = assignment.loc[train].to_numpy()
        saved_train = pd.concat([saved_train, train_x], axis=1)
        saved_train.to_parquet(folder / 'training_features.parquet', index=False, compression='zstd')
        write(folder / 'auxiliary_receipts.json', dict(forbidden_groups=list(key), auxiliary=auxiliary_receipts, full=full_receipt))
        q = index.loc[query].copy(); q['original_index'] = q.index
        q['estimated_weather_temp'] = query_temperature
        q['fallback'] = ~np.isfinite(query_temperature)
        q['baseline_prediction'] = base_pred.loc[query].astype(int).to_numpy()
        q['baseline_score'] = base_score.loc[query].to_numpy()
        q['thermal_moisture'], _, _ = fixed_thermal_rule(query_temperature, weather.loc[query], q.baseline_prediction, True)
        for candidate in CANDIDATES:
            joint = candidate == 'joint_surface_state'
            labels = classes[train] if joint else index.loc[train, 'ice'].to_numpy()
            weights = np.where(index.loc[train, 'ice'].eq(1), PLAN['ice_weight'], 1.)
            model = HistGradientBoostingClassifier(**PARAMS)
            tick = time.perf_counter()
            with threadpool_limits(limits=2):
                model.fit(train_x, labels.astype(int), sample_weight=weights)
                score = ice_probability(model, query_x, joint)
            q[candidate + '_score'] = np.where(q.fallback, q.baseline_score, score)
            path = folder / (candidate + '.joblib'); joblib.dump(model, path, compress=3)
            receipt = dict(kind='classifier', candidate=candidate, context_groups=list(key),
                           forbidden_stations=sorted(forbidden), training_stations=sorted(set(index.loc[train, 'station'])),
                           training_rows=int(train.sum()), training_identity=identity(saved_train),
                           matrix_sha256=sha(folder / 'training_features.parquet'), features=FEATURES,
                           model_path=str(path), model_sha256=sha(path),
                           classes=[int(c) for c in model.classes_], label_counts={str(k): int(v) for k, v in pd.Series(labels).value_counts().items()},
                           fit_seconds=time.perf_counter() - tick)
            receipts.append(receipt); write(out / 'fit_receipts.json', receipts)
            print(f'Classifier {candidate}, context={key}, rows={train.sum()}, seconds={receipt["fit_seconds"]:.1f}', flush=True)
        q.to_parquet(folder / 'query_predictions.parquet', index=False, compression='zstd')
        contexts[key] = q
        return q

    decisions = {}; outer_parts = []
    for outer in groups:
        inner = pd.concat([context([outer, held]).loc[lambda d: d.group.eq(held)] for held in groups if held != outer])
        baseline, bs, _, _ = diagnostic_report(inner, inner.thermal_moisture)
        reports = {}; thresholds = {}; guards = {}; eligible = []
        for candidate in CANDIDATES:
            table = threshold_table(inner, inner[candidate + '_score'], inner.fallback, inner.baseline_prediction)
            directory = out / 'decisions'; directory.mkdir(exist_ok=True)
            table.to_csv(directory / (outer + '__' + candidate + '__thresholds.csv'), index=False)
            threshold = select_threshold(table, baseline['fp']); thresholds[candidate] = threshold
            p = threshold_prediction(inner[candidate + '_score'], threshold, inner.fallback, inner.baseline_prediction)
            report, stations, _, _ = diagnostic_report(inner, p)
            accepted, checks = eligibility(report, baseline, stations, bs)
            reports[candidate] = report; guards[candidate] = checks
            if accepted:
                eligible.append(candidate)
        selected = min(eligible, key=lambda c: (-reports[c]['fixed_ice_day_f1'], -reports[c]['f1'], c)) if eligible else 'thermal_moisture'
        decisions[outer] = dict(outer_group=outer, inner_groups=[g for g in groups if g != outer],
                                baseline=baseline, candidates=reports, thresholds=thresholds,
                                guards=guards, eligible=eligible, selected=selected,
                                decided_at_utc=datetime.now(timezone.utc).isoformat(), outer_labels_used=False)
        write(out / 'decisions.json', decisions)
        print(f'Decision before outer scoring: {outer}: {selected}', flush=True)
        query = context([outer]).copy()
        for candidate in CANDIDATES:
            query[candidate] = threshold_prediction(query[candidate + '_score'], thresholds[candidate], query.fallback, query.baseline_prediction)
            query[candidate + '_threshold'] = thresholds[candidate]
        query['selected_candidate'] = selected; query['selected_prediction'] = query[selected]
        outer_parts.append(query)
    predictions = pd.concat(outer_parts).sort_values('original_index').reset_index(drop=True)
    predictions.to_parquet(out / 'outer_predictions.parquet', index=False, compression='zstd')
    write(out / 'prediction_seal.json', dict(sha256=sha(out / 'outer_predictions.parquet'),
                                           decisions_sha256=sha(out / 'decisions.json'),
                                           timestamp_utc=datetime.now(timezone.utc).isoformat(), scored=False))
    previous_thermal = pd.read_parquet(paths['thermal_predictions']).set_index(['station', 'time'])
    paired = previous_thermal.loc[pd.MultiIndex.from_frame(predictions[['station', 'time']])]
    assert np.array_equal(paired.hgb_cold_moisture, predictions.thermal_moisture)
    assert np.allclose(paired.selected_weather, predictions.estimated_weather_temp, atol=0, rtol=0, equal_nan=True)
    metrics = {}; stations_all = []; days_all = []; events_all = []; state_rows = []
    for policy in ['baseline_prediction', 'thermal_moisture', *CANDIDATES, 'selected_prediction']:
        report, stations, days, events = diagnostic_report(predictions, predictions[policy])
        if policy in CANDIDATES:
            valid = predictions.ice.notna()
            report['average_precision'] = float(average_precision_score(predictions.loc[valid, 'ice'], predictions.loc[valid, policy + '_score']))
        metrics[policy] = report
        for result, collection in [(stations, stations_all), (days, days_all), (events, events_all)]:
            result['policy'] = policy; collection.append(result)
        for state, rows in predictions[predictions.ice.eq(0)].groupby('state_raw'):
            state_rows.append(dict(policy=policy, state_raw=str(state), negative_rows=len(rows), fp=int(rows[policy].sum())))
    pd.concat(stations_all).to_csv(out / 'station_metrics.csv', index=False)
    pd.concat(days_all).to_csv(out / 'daily_metrics.csv', index=False)
    pd.concat(events_all).to_csv(out / 'event_metrics.csv', index=False)
    pd.DataFrame(state_rows).to_csv(out / 'raw_state_metrics.csv', index=False)
    verify_reserved_freeze(release, release / 'outputs/private/external_reserved_predictions_v1')
    verify_freeze(release)
    write(out / 'summary.json', dict(status='completed', metrics=metrics,
                                    selected_groups={g: d['selected'] for g, d in decisions.items()},
                                    development_rows=len(index), valid_training_labels=int(index.ice.notna().sum()),
                                    external_prediction_rows=len(predictions), missing_temperature_fallback_rows=int(predictions.fallback.sum()),
                                    unique_temperature_models=sum(r['kind'] == 'temperature' for r in receipts),
                                    new_temperature_models=sum(r['kind'] == 'temperature' and not r['reused'] for r in receipts),
                                    unique_classifier_models=sum(r['kind'] == 'classifier' for r in receipts),
                                    seconds=time.perf_counter() - started, plan_sha256=sha(out / 'experiment_plan.json'),
                                    frozen_external_files=len(frozen_external['files']), frozen_original_files=len(frozen_original['files']),
                                    protected_or_reserved_outcomes_used=False, final_model_promoted=False,
                                    scope=PLAN['scope']))
    print(json.dumps(metrics, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
