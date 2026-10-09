"""외부·내부·보정 생성 그룹을 모두 제외한 점수 보정을 첫 겨울에서 검증한다."""
from pathlib import Path
from datetime import datetime, timezone
from itertools import combinations
import argparse, hashlib, json, shutil, sys, time

import joblib
import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.joint_surface import (WEATHER, FEATURES, excluded_stations, unit_blocks, thermal_features,
                              ice_probability, threshold_table, select_threshold, threshold_prediction, eligibility)
from src.thermal_ice import validate_development, diagnostic_report
from src.score_calibration import adjusted_logit, fit_sigmoid, apply_sigmoid, validate_calibration_origins
from src.external_reserved import verify_reserved_freeze
from src.frozen_assessment import verify_freeze

PARAMS = dict(learning_rate=.05, max_iter=100, max_leaf_nodes=15, min_samples_leaf=100,
              l2_regularization=10., early_stopping=False, random_state=20260923)
CANDIDATES = ['prior_score', 'calibrated_raw', 'calibrated_prior']
PLAN = dict(experiment_id='20261009_three_level_score_calibration_v1', candidates=CANDIDATES,
            classifier='Frozen binary thermal/weather architecture, features20 and parameters unchanged.',
            parameters=PARAMS, positive_weight=20., clipping=1e-9,
            prior_score='expit(logit(weighted_score)-log(20)-logit(unweighted training Ice fraction)). Standardized score, not validated posterior.',
            calibrated_raw='Nonnegative-slope sigmoid on raw logit; summed logistic loss + slope squared / 2; no class weights.',
            calibrated_prior='Same sigmoid on prior-adjusted logit; no target prior estimation from evaluation labels.',
            inner_calibration='For outer G and validation H, fit calibrator on the two remaining K groups with classifier predictions excluding G+H+K. Temperature training and auxiliary folds exclude the same groups.',
            outer_calibration='For outer G, fit calibrator on the other three H groups with existing classifier predictions excluding G+H.',
            auxiliary_folds='Reuse outcome-independent 18 spatial units modulo3. Every classifier training row receives temperature excluding its block and all held-out groups.',
            threshold='403 fixed points; inner FP <= fixed thermal/moisture baseline, maximize fixed actual-ice-day F1, then micro F1, then higher threshold.',
            eligibility='Same micro/ice-day/fixed-station F1, FP, single-slot and >=5-positive station TP guards as previous experiment.',
            missing_temperature='For every threshold use competition-only old baseline prediction on missing temperature; retain valid labels.',
            labels='04 only; undefined excluded, 13 and 15 remain negative.',
            period_kst=['2024-11-01', '2025-02-28'], max_threads=2,
            protected_or_reserved_outcomes_used=False, bbse_or_em_applied=False,
            scope='Repeated first-winter development; no fresh blind/official score or deployment promotion.')


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(2**20), b''): h.update(b)
    return h.hexdigest()


def identity(frame):
    return hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).values.tobytes()).hexdigest()


def read(p): return json.loads(Path(p).read_text('utf-8'))
def write(p, v): Path(p).write_text(json.dumps(v, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); out = args.output.resolve(); private = ROOT / 'outputs/private'
    if not out.is_relative_to(private.resolve()): parser.error('Private output required')
    if out.exists(): raise FileExistsError('Preserve previous experiment')
    release = private / 'releases/20261007'
    frozen_external = verify_reserved_freeze(release, release / 'outputs/private/external_reserved_predictions_v1')
    frozen_original = verify_freeze(release)
    previous = private / 'joint_surface_20261009_v1'; temperature_run = private / 'weather_fallback_20261009_v1'
    assert read(previous / 'independent_verification_labels_v2.json')['status'] == 'passed'
    for entry in read(previous / 'input_signature.json').values(): assert sha(entry['path']) == entry['sha256']
    for entry in read(temperature_run / 'input_signature.json').values(): assert sha(entry['path']) == entry['sha256']
    out.mkdir(parents=True); write(out / 'experiment_plan.json', PLAN)
    shutil.copy2(__file__, out / 'analysis_source.py'); shutil.copy2(ROOT / 'src/score_calibration.py', out / 'calibration_source.py')
    paths = dict(index=private / 'ice_group_balanced_20261009_v1/development_index.parquet',
                 features=private / 'ice_group_balanced_20261009_v1/feature_matrix.parquet',
                 temperature_index=temperature_run / 'training_index.parquet',
                 previous_receipts=previous / 'fit_receipts.json', previous_predictions=previous / 'outer_predictions.parquet',
                 previous_plan=previous / 'experiment_plan.json', previous_audit=previous / 'independent_verification_labels_v2.json')
    signatures = {k: dict(path=str(p), sha256=sha(p)) for k, p in paths.items()}
    index = validate_development(pd.read_parquet(paths['index'])); temp = pd.read_parquet(paths['temperature_index'])
    pd.testing.assert_frame_equal(index[['station', 'time', 'group']], temp[['station', 'time', 'group']])
    raw = pd.read_parquet(paths['features']); assert len(raw) == len(index)
    groups = sorted(set(index.group) - {'competition'}); assert len(groups) == 4
    blocks = unit_blocks(index); assert blocks == read(previous / 'unit_blocks.json')
    receipts = []; contexts = {}; temperature_cache = {}; calibrations = {}
    old_receipts = read(paths['previous_receipts'])
    for r in old_receipts: assert sha(r['model_path']) == r['model_sha256']
    for folder in (previous / 'contexts').iterdir():
        qpath = folder / 'query_predictions.parquet'; q = pd.read_parquet(qpath)
        key = tuple(sorted(q.group.unique())); contexts[key] = q
        signatures['context_' + '__'.join(key)] = dict(path=str(qpath), sha256=sha(qpath))
    write(out / 'input_signature.json', signatures)
    domain = np.isfinite(temp.road_temp) & raw.asos_air_temp.notna()
    started = time.perf_counter()

    def temperature_model(forbidden):
        key = tuple(sorted(forbidden))
        if key in temperature_cache: return temperature_cache[key]
        mask = domain & ~index.station.isin(forbidden)
        matches = [r for r in old_receipts if r['kind'] == 'temperature' and set(r['forbidden_stations']) == forbidden]
        training_id = identity(temp.loc[mask, ['station', 'time', 'road_temp']])
        if matches:
            r = matches[0]; assert r['training_identity'] == training_id and r['training_rows'] == int(mask.sum())
            model = joblib.load(r['model_path']); record = dict(r, reused=True)
        else:
            model = HistGradientBoostingRegressor(**PARAMS)
            with threadpool_limits(limits=2): model.fit(raw.loc[mask, WEATHER], temp.loc[mask, 'road_temp'])
            folder = out / 'temperature_models'; folder.mkdir(exist_ok=True)
            path = folder / (hashlib.sha256('|'.join(key).encode()).hexdigest()[:20] + '.joblib'); joblib.dump(model, path, compress=3)
            record = dict(kind='temperature', reused=False, model_path=str(path), model_sha256=sha(path),
                          forbidden_stations=list(key), training_rows=int(mask.sum()), training_identity=training_id,
                          training_stations=sorted(set(index.loc[mask, 'station'])), features=WEATHER)
        assert all(model.get_params()[k] == v for k, v in PARAMS.items())
        assert not set(record['training_stations']) & forbidden
        receipts.append(record); write(out / 'fit_receipts.json', receipts)
        temperature_cache[key] = (model, record); return model, record

    def estimate(model, rows):
        with threadpool_limits(limits=2): values = model.predict(raw.loc[rows, WEATHER])
        return np.where(raw.loc[rows].asos_air_temp.notna(), values, np.nan)

    for held in combinations(groups, 3):
        forbidden = excluded_stations(index, held); train = ~index.station.isin(forbidden) & index.ice.notna()
        query = index.station.isin(forbidden); folder = out / 'contexts' / '__'.join(held); folder.mkdir(parents=True)
        temperature = pd.Series(np.nan, index=index.index); assignment = pd.Series(-1, index=index.index); auxiliary = []
        for block in range(3):
            rows = train & index.station.map(blocks).eq(block)
            if not rows.any(): continue
            model, record = temperature_model(excluded_stations(index, held, blocks, block))
            assert not set(index.loc[rows, 'station']) & set(record['training_stations'])
            temperature.loc[rows] = estimate(model, rows); assignment.loc[rows] = block
            auxiliary.append(dict(block=block, receipt=record))
        assert assignment[train].ge(0).all()
        full, record = temperature_model(forbidden); query_temperature = estimate(full, query)
        train_x = thermal_features(raw.loc[train], temperature[train]); query_x = thermal_features(raw.loc[query], query_temperature)
        saved = pd.concat([index.loc[train], train_x], axis=1); saved['original_index'] = saved.index; saved['auxiliary_block'] = assignment[train]
        saved.to_parquet(folder / 'training_features.parquet', index=False, compression='zstd')
        write(folder / 'auxiliary_receipts.json', dict(held_groups=list(held), auxiliary=auxiliary, full=record))
        classifier = HistGradientBoostingClassifier(**PARAMS)
        with threadpool_limits(limits=2):
            classifier.fit(train_x, index.loc[train, 'ice'].astype(int), sample_weight=np.where(index.loc[train].ice.eq(1), 20., 1.))
            score = ice_probability(classifier, query_x)
        path = folder / 'binary_thermal_weather.joblib'; joblib.dump(classifier, path, compress=3)
        r = dict(kind='classifier', candidate='binary_thermal_weather', context_groups=list(held), forbidden_stations=sorted(forbidden),
                 training_rows=int(train.sum()), positives=int(index.loc[train, 'ice'].sum()),
                 training_stations=sorted(set(index.loc[train, 'station'])), training_identity=identity(saved),
                 matrix_sha256=sha(folder / 'training_features.parquet'), features=FEATURES, model_path=str(path), model_sha256=sha(path))
        receipts.append(r); write(out / 'fit_receipts.json', receipts)
        q = index.loc[query].copy(); q['original_index'] = q.index; q['estimated_weather_temp'] = query_temperature
        q['fallback'] = ~np.isfinite(query_temperature)
        # 고정 대회 14지점 모델의 비교 예측. 외부 목표 정답은 입력에 넣지 않는다.
        baseline = pd.concat([contexts[(g,)][['original_index', 'baseline_prediction', 'baseline_score']] for g in held]).set_index('original_index')
        q['baseline_prediction'] = baseline.loc[q.index, 'baseline_prediction'].to_numpy()
        q['baseline_score'] = baseline.loc[q.index, 'baseline_score'].to_numpy()
        q['binary_thermal_weather_score'] = np.where(q.fallback, q.baseline_score, score)
        q.to_parquet(folder / 'query_predictions.parquet', index=False, compression='zstd'); contexts[held] = q
        print('Triple-excluded classifier completed:', held, flush=True)

    combined_receipts = old_receipts + receipts
    def metadata(held):
        r = next(r for r in combined_receipts if r['kind'] == 'classifier' and r['candidate'] == 'binary_thermal_weather' and r['context_groups'] == list(held))
        positives = r.get('positives', int(r.get('label_counts', {}).get('1.0', 0)))
        return positives / r['training_rows'], r['model_sha256']

    def score_rows(held, target_groups):
        q = contexts[held]; q = q[q.group.isin(target_groups)].copy(); prevalence, model_sha = metadata(held)
        q['training_prevalence'] = prevalence; q['source_model_sha256'] = model_sha
        q['source_forbidden_groups'] = [list(held)] * len(q)
        q['raw_logit'] = adjusted_logit(q.binary_thermal_weather_score, prevalence)
        q['prior_logit'] = adjusted_logit(q.binary_thermal_weather_score, prevalence, prior_adjusted=True)
        return q

    def calibrator(held):
        held = tuple(sorted(held))
        if held in calibrations: return calibrations[held]
        pool = pd.concat([score_rows(tuple(sorted([*held, k])), [k]) for k in groups if k not in held])
        pool = pool[pool.ice.notna() & ~pool.fallback].copy()
        validate_calibration_origins(pool, set(held))
        folder = out / 'calibrations' / '__'.join(held); folder.mkdir(parents=True)
        pool.to_parquet(folder / 'training_predictions.parquet', index=False, compression='zstd')
        result = dict(held_groups=list(held), training_groups=sorted(set(pool.group)), training_rows=len(pool),
                      positives=int(pool.ice.sum()), training_predictions_sha256=sha(folder / 'training_predictions.parquet'),
                      raw=fit_sigmoid(pool.raw_logit, pool.ice), prior=fit_sigmoid(pool.prior_logit, pool.ice))
        write(folder / 'receipt.json', result); calibrations[held] = result; return result

    def predictions(held, target_groups):
        q = score_rows(held, target_groups); calibration = calibrator(held)
        q['prior_score_score'] = expit(q.prior_logit)
        q['calibrated_raw_score'] = apply_sigmoid(calibration['raw'], q.raw_logit)
        q['calibrated_prior_score'] = apply_sigmoid(calibration['prior'], q.prior_logit)
        for c in CANDIDATES: q[c + '_score'] = np.where(q.fallback, q.baseline_score, q[c + '_score'])
        return q

    decisions = {}; outputs = []; inner_paths = {}
    for outer in groups:
        inner = pd.concat([predictions(tuple(sorted([outer, h])), [h]) for h in groups if h != outer])
        # 비교 물리 기준은 같은 G+H 제외 온도에서 계산한 직전 기준을 재사용한다.
        baseline, bs, _, _ = diagnostic_report(inner, inner.thermal_moisture)
        reports = {}; thresholds = {}; guards = {}; accepted = []
        folder = out / 'decisions'; folder.mkdir(exist_ok=True)
        for c in CANDIDATES:
            table = threshold_table(inner, inner[c + '_score'], inner.fallback, inner.baseline_prediction)
            table.to_csv(folder / (outer + '__' + c + '__thresholds.csv'), index=False)
            threshold = select_threshold(table, baseline['fp']); thresholds[c] = threshold
            inner[c] = threshold_prediction(inner[c + '_score'], threshold, inner.fallback, inner.baseline_prediction)
            result, stations, _, _ = diagnostic_report(inner, inner[c]); reports[c] = result
            accept, checks = eligibility(result, baseline, stations, bs); guards[c] = checks
            if accept: accepted.append(c)
        selected = min(accepted, key=lambda c: (-reports[c]['fixed_ice_day_f1'], -reports[c]['f1'], c)) if accepted else 'thermal_moisture'
        path = folder / (outer + '__inner_predictions.parquet'); inner.to_parquet(path, index=False, compression='zstd'); inner_paths[outer] = str(path)
        decisions[outer] = dict(inner_groups=[g for g in groups if g != outer], baseline=baseline, candidates=reports,
                                thresholds=thresholds, guards=guards, eligible=accepted, selected=selected,
                                decided_at_utc=datetime.now(timezone.utc).isoformat(), outer_labels_used=False)
        write(out / 'decisions.json', decisions)
        q = predictions((outer,), [outer])
        for c in CANDIDATES:
            q[c] = threshold_prediction(q[c + '_score'], thresholds[c], q.fallback, q.baseline_prediction)
            q[c + '_threshold'] = thresholds[c]
        q['selected_candidate'] = selected; q['selected_prediction'] = q[selected]; outputs.append(q)
        print('Decision before outer scoring:', outer, selected, flush=True)
    outer = pd.concat(outputs).sort_values('original_index').reset_index(drop=True)
    outer.to_parquet(out / 'outer_predictions.parquet', index=False, compression='zstd')
    write(out / 'prediction_seal.json', dict(sha256=sha(out / 'outer_predictions.parquet'), decisions_sha256=sha(out / 'decisions.json'),
                                           timestamp_utc=datetime.now(timezone.utc).isoformat(), scored=False))
    metrics = {}; station_rows = []; day_rows = []; event_rows = []; group_rows = []
    for policy in ['thermal_moisture', *CANDIDATES, 'selected_prediction']:
        result, stations, days, events = diagnostic_report(outer, outer[policy]); metrics[policy] = result
        for data, rows in [(stations, station_rows), (days, day_rows), (events, event_rows)]: data['policy'] = policy; rows.append(data)
        if policy in CANDIDATES:
            valid = outer.ice.notna(); score = outer.loc[valid, policy + '_score']; yy = outer.loc[valid, 'ice']
            result['average_precision'] = float(average_precision_score(yy, score))
            if policy.startswith('calibrated'):
                result['brier'] = float(brier_score_loss(yy, score)); result['log_loss'] = float(log_loss(yy, score))
            for g, part in outer[valid].groupby('group'):
                group_rows.append(dict(group=g, candidate=policy, n=len(part), positives=int(part.ice.sum()),
                                       average_precision=float(average_precision_score(part.ice, part[policy + '_score']))))
    pd.concat(station_rows).to_csv(out / 'station_metrics.csv', index=False); pd.concat(day_rows).to_csv(out / 'daily_metrics.csv', index=False)
    pd.concat(event_rows).to_csv(out / 'event_metrics.csv', index=False); pd.DataFrame(group_rows).to_csv(out / 'group_ranking.csv', index=False)
    verify_reserved_freeze(release, release / 'outputs/private/external_reserved_predictions_v1'); verify_freeze(release)
    write(out / 'summary.json', dict(status='completed', metrics=metrics, selected_groups={g: d['selected'] for g,d in decisions.items()},
                                    new_classifier_models=4, temperature_models=len(temperature_cache),
                                    new_temperature_models=sum(r['kind']=='temperature' and not r['reused'] for r in receipts),
                                    calibrators=len(calibrations)*2, classifier_receipts=len(receipts),
                                    fallback_rows=int(outer.fallback.sum()), external_rows=len(outer),
                                    seconds=time.perf_counter()-started, plan_sha256=sha(out / 'experiment_plan.json'),
                                    protected_or_reserved_outcomes_used=False, final_model_promoted=False,
                                    frozen_external_files=len(frozen_external['files']), frozen_original_files=len(frozen_original['files']), scope=PLAN['scope']))
    print(json.dumps(metrics,ensure_ascii=False),flush=True)


if __name__ == '__main__': main()
