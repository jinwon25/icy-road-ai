"""누적합 이력·독립 가중치·모델 재예측·모든 임계값·사건을 별도 검산한다."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from catboost import CatBoostClassifier
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.audit_joint_surface import independent_thresholds
from scripts.audit_temperature_blind_validation import reference_ice, compare, counts
from scripts.fresh_station_validation import old_freezes, verify_seal

METHODS = ['hgb_long300', 'hgb_no_distance', 'hgb_history', 'hgb_balanced', 'catboost400', 'hurdle_non_dry']
CONTROL = 'binary100_control'
ALLOWED = set('12103 12209 12210 12211 12409 23202 23203 23204 23403 33103 33206 33409 33410 33412 12207 12408 23205 23404 33205 33408 33207 33413 33414'.split())
WEATHER = ['asos_air_temp', 'aws_air_temp', 'aws_humidity', 'aws_wind_speed', 'aws_rain_15m', 'aws_dewpoint', 'aws_age_minutes', 'asos_age_minutes', 'aws_distance_km', 'asos_distance_km', 'hour_sin', 'hour_cos', 'season_sin', 'season_cos']
FEATURES = WEATHER+['rain15_max_3h', 'asos_snow_cm', 'estimated_weather_temp', 'estimated_surface_dewpoint_gap', 'estimated_surface_air_gap', 'moisture_evidence']
HISTORY = ['estimated_weather_temp', 'aws_air_temp', 'aws_humidity', 'aws_dewpoint', 'aws_rain_15m', 'aws_wind_speed']


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


def independently_prior(frame):
    result = {}
    for c in HISTORY:
        for m in (60, 180):
            result[f'{c}_prior_mean_{m}m'] = np.full(len(frame), np.nan)
        result[c+'_change_60m'] = np.full(len(frame), np.nan)
    positions = pd.Series(np.arange(len(frame)), index=frame.index)
    for _, part in frame.groupby('station'):
        part = part.sort_values('time'); ids = positions.loc[part.index].to_numpy()
        times = part.time.to_numpy(dtype='datetime64[ns]').astype('int64')
        right = np.arange(len(part)); desired = times-60*60*10**9
        previous = np.searchsorted(times, desired, side='left'); exists = (previous < len(times)) & (times[np.minimum(previous, len(times)-1)] == desired)
        for c in HISTORY:
            x = part[c].to_numpy(float); valid = np.isfinite(x)
            sums = np.r_[0., np.cumsum(np.where(valid, x, 0.))]; number = np.r_[0, np.cumsum(valid)]
            for m in (60, 180):
                left = np.searchsorted(times, times-m*60*10**9, side='left')
                count = number[right]-number[left]; total = sums[right]-sums[left]
                mean = np.divide(total, count, out=np.full(len(part), np.nan), where=count >= np.ceil(.8*m/10))
                result[f'{c}_prior_mean_{m}m'][ids] = mean
            result[c+'_change_60m'][ids[exists]] = x[exists]-x[previous[exists]]
    return pd.DataFrame(result, index=frame.index)


def thermal(raw, temperatures):
    x = raw[WEATHER+['rain15_max_3h', 'asos_snow_cm']].copy(); x['estimated_weather_temp'] = temperatures
    x['estimated_surface_dewpoint_gap'] = temperatures-x.aws_dewpoint.to_numpy()
    x['estimated_surface_air_gap'] = temperatures-x.aws_air_temp.to_numpy()
    available = x[['aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']].notna().any(axis=1).to_numpy() & np.isfinite(temperatures)
    signal = ((x.aws_dewpoint.to_numpy() >= temperatures) | x.rain15_max_3h.gt(0).to_numpy() | x.asos_snow_cm.gt(0).to_numpy()).astype(float)
    x['moisture_evidence'] = np.where(available, signal, np.nan)
    return x[FEATURES]


def labels(frame):
    code = pd.to_numeric(frame.state_raw, errors='coerce').to_numpy()
    expected = np.where(code == 4, 1., np.where(np.isin(code, [1, 2, 3, 10, 11, 12, 13, 14, 15]), 0., np.nan))
    np.testing.assert_allclose(frame.ice, expected, atol=0, rtol=0, equal_nan=True)


def weights(y, candidate, stage):
    if candidate == 'hgb_balanced':
        return np.where(y == 1, len(y)/(2*sum(y == 1)), len(y)/(2*sum(y == 0)))
    return np.where(y == 1, 1. if stage == 'non_dry' else 20., 1.)


def predict(model, x):
    positive = list(model.classes_).index(1)
    with threadpool_limits(limits=2):
        return model.predict_proba(x)[:, positive]


def guard(frame, column, reference):
    a, b = reference_ice(frame, column), reference_ice(frame, reference)
    station_safe = all(counts(st, column)['tp'] >= counts(st, reference)['tp'] for _, st in frame.groupby('station'))
    metrics = ['f1', 'fixed_station_f1_zero_undefined', 'fixed_ice_day_f1', 'provisional_daily_station_f1']
    supported = all(a[k] is not None and b[k] is not None for k in metrics)
    result = dict(supported_metrics=supported, fp_nonincrease=a['fp'] <= b['fp'], fn_nonincrease=a['fn'] <= b['fn'],
                  every_positive_station_tp=station_safe, events_nonincrease_misses=a['detected_events'] >= b['detected_events'],
                  singles_nonincrease_misses=a['detected_single_slot_events'] >= b['detected_single_slot_events'],
                  f1_nonworse=supported and all(a[k]+1e-12 >= b[k] for k in metrics),
                  strict_improvement=supported and (a['fp'] < b['fp'] or a['fn'] < b['fn'] or any(a[k] > b[k]+1e-12 for k in metrics)))
    return a, result


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--experiment', type=Path, default=ROOT / 'outputs/private/ice_methodology_20261010_v1')
    out = parser.parse_args().experiment.resolve(); target = out / 'independent_verification.json'
    if not out.is_relative_to((ROOT / 'outputs/private').resolve()) or target.exists():
        raise ValueError('New private audit receipt required')
    summary, plan = read(out / 'summary.json'), read(out / 'experiment_plan.json')
    assert plan['candidates'] == METHODS and not summary['assessment_outcomes_used']
    for rel, digest in read(out / 'input_signatures.json').items():
        assert sha(ROOT / rel) == digest, rel
    for rel, digest in summary['files'].items():
        assert sha(out / rel) == digest, rel
    source = ROOT / 'outputs/private/joint_surface_20261009_v1'
    old_signatures = read(source / 'input_signature.json')
    for record in old_signatures.values():
        assert sha(record['path']) == record['sha256']
    index = pd.read_parquet(old_signatures['development_index']['path']); raw = pd.read_parquet(old_signatures['features']['path'])
    original_predictions = pd.read_parquet(old_signatures['old_predictions']['path']).set_index(['station', 'time'])
    blocks = read(source / 'unit_blocks.json'); groups = read(out / 'groups.json'); receipts = read(out / 'fit_receipts.json')
    labels(index); assert set(index.station) == ALLOWED
    source_audit = read(source / 'independent_verification.json'); assert source_audit['status'] == 'passed' and source_audit['summary_sha256'] == sha(source / 'summary.json')
    history_values = 0; score_values = 0; control_values = 0; query_temperature_rows = 0; temperature_rows = 0; refits = []; contexts = {}
    for folder in sorted((out / 'contexts').iterdir()):
        key = folder.name.split('__'); forbidden = set(index.loc[index.group.isin(key), 'station'])
        train = pd.read_parquet(folder / 'training_inputs.parquet'); qx = pd.read_parquet(folder / 'query_inputs.parquet'); q = pd.read_parquet(folder / 'query_predictions.parquet')
        old_folder = source / 'contexts' / folder.name; provenance = read(old_folder / 'auxiliary_receipts.json')
        expected_train = index.loc[~index.station.isin(forbidden)]; expected_query = index.loc[index.station.isin(forbidden)]
        assert train.original_index.tolist() == expected_train.index.tolist() and q.original_index.tolist() == expected_query.index.tolist()
        for frame in [train, q]:
            assert not frame.duplicated(['station', 'time']).any() and set(frame.station) <= ALLOWED
            assert frame.time.ge('2024-11-01').all() and frame.time.lt('2025-03-01').all()
            labels(frame)
        pd.testing.assert_frame_equal(q[pd.read_parquet(old_folder / 'query_predictions.parquet').columns], pd.read_parquet(old_folder / 'query_predictions.parquet'))
        estimates = np.full(len(train), np.nan)
        for auxiliary in provenance['auxiliary']:
            r = auxiliary['receipt']; excluded = forbidden | {s for s, b in blocks.items() if b == auxiliary['block']}
            assert set(r['forbidden_stations']) == excluded and set(r['training_stations']).isdisjoint(excluded)
            assert sha(r['model_path']) == r['model_sha256']
            selected = train.station.map(blocks).eq(auxiliary['block']).to_numpy()
            ids = train.loc[selected].original_index
            with threadpool_limits(limits=2):
                predicted = joblib.load(r['model_path']).predict(raw.loc[ids, WEATHER])
            estimates[selected] = np.where(raw.loc[ids].asos_air_temp.notna(), predicted, np.nan)
        np.testing.assert_allclose(train.estimated_weather_temp, estimates, atol=1e-10, rtol=0, equal_nan=True); temperature_rows += len(train)
        full = provenance['full']; assert sha(full['model_path']) == full['model_sha256']
        assert set(full['training_stations']).isdisjoint(forbidden) and set(full['forbidden_stations']) == forbidden
        with threadpool_limits(limits=2):
            query_temperature = joblib.load(full['model_path']).predict(raw.loc[q.original_index, WEATHER])
        query_temperature = np.where(raw.loc[q.original_index].asos_air_temp.notna(), query_temperature, np.nan)
        np.testing.assert_allclose(q.estimated_weather_temp, query_temperature, atol=1e-10, rtol=0, equal_nan=True); query_temperature_rows += len(q)
        old = original_predictions.reindex(pd.MultiIndex.from_frame(q[['station', 'time']]))
        for column in ['baseline_prediction', 'baseline_score']:
            np.testing.assert_allclose(q[column], old[column], atol=0, rtol=0)
        for frame, ids, estimated in [(train, train.original_index, estimates), (qx, q.original_index, q.estimated_weather_temp.to_numpy())]:
            expected = thermal(raw.loc[ids], estimated)
            np.testing.assert_allclose(frame[FEATURES], expected, atol=1e-10, rtol=0, equal_nan=True)
            history = independently_prior(frame)
            np.testing.assert_allclose(frame[history.columns], history, atol=1e-8, rtol=0, equal_nan=True); history_values += history.size
        fitting = train.loc[train.ice.notna()].copy()
        for name in METHODS:
            columns = [c for c in FEATURES if name != 'hgb_no_distance' or c not in ['aws_distance_km', 'asos_distance_km']]
            if name == 'hgb_history':
                columns += list(independently_prior(train.iloc[:1]).columns)
                # 실제 저장 순서: 모든 평균 뒤에 모든 변화량. 계산 결과는 이름으로 정렬한다.
                columns = FEATURES+[f'{c}_prior_mean_{m}m' for c in HISTORY for m in (60, 180)]+[c+'_change_60m' for c in HISTORY]
            x, vx = fitting[columns], qx[columns]
            selected_receipts = [r for r in receipts if r['context_groups'] == key and r['candidate'] == name]
            assert len(selected_receipts) == (2 if name == 'hurdle_non_dry' else 1)
            score = np.ones(len(q))
            for r in selected_receipts:
                code = pd.to_numeric(fitting.state_raw, errors='raise').to_numpy()
                mask = code != 1 if r['stage'] == 'conditional_ice' else np.ones(len(fitting), bool)
                y = (code[mask] != 1).astype(int) if r['stage'] == 'non_dry' else fitting.loc[mask].ice.to_numpy(int)
                w = weights(y, name, r['stage'])
                assert r['rows'] == int(mask.sum()) and r['features'] == columns
                assert r['training_stations'] == sorted(set(fitting.station)) and set(r['training_stations']).isdisjoint(forbidden)
                assert r['training_matrix_sha256'] == sha(folder / 'training_inputs.parquet') and sha(r['model_path']) == r['model_sha256']
                assert r['weight_sha256'] == hashlib.sha256(np.asarray(w, dtype='<f8').tobytes()).hexdigest()
                np.testing.assert_allclose(w.sum(), r['weight_sum'], atol=1e-10, rtol=0)
                model = joblib.load(r['model_path'])
                params = plan['catboost'] if name == 'catboost400' else plan['hgb'] | ({'max_iter': 300} if name == 'hgb_long300' else {})
                actual_params = model.get_params()
                assert all(actual_params[k] == v for k, v in params.items())
                values = predict(model, vx); score *= values
                if len(key) == 1 and key[0] == sorted(groups)[0]:
                    clone = CatBoostClassifier(**params) if name == 'catboost400' else HistGradientBoostingClassifier(**params)
                    with threadpool_limits(limits=2):
                        clone.fit(x.loc[mask], y, sample_weight=w)
                    np.testing.assert_allclose(predict(clone, vx), values, atol=1e-12, rtol=0)
                    refits.append(name+':'+r['stage'])
            expected = np.where(q.fallback, q.baseline_score, score)
            np.testing.assert_allclose(q[name+'_score'], expected, atol=1e-12, rtol=0); score_values += len(q)
        np.testing.assert_array_equal(q[CONTROL+'_score'], q.binary_thermal_weather_score)
        old_model_path = old_folder / 'binary_thermal_weather.joblib'
        old_receipt = next(r for r in read(source / 'fit_receipts.json') if r['kind'] == 'classifier' and r['candidate'] == 'binary_thermal_weather' and r['context_groups'] == key)
        assert sha(old_model_path) == old_receipt['model_sha256']
        old_scores = predict(joblib.load(old_model_path), qx[FEATURES])
        np.testing.assert_allclose(q[CONTROL+'_score'], np.where(q.fallback, q.baseline_score, old_scores), atol=1e-12, rtol=0); control_values += len(q)
        contexts[tuple(key)] = q
        print('입력·이력·모델 검산', folder.name, flush=True)
    decisions = read(out / 'decisions.json'); grid_rows = 0; parts = []
    for outer in groups:
        inner = pd.read_parquet(out / outer / 'inner_predictions.parquet'); result = pd.read_parquet(out / outer / 'outer_predictions.parquet'); decision = decisions[outer]
        original = pd.concat([contexts[tuple(sorted([outer, other]))].loc[lambda f: f.group.eq(other)] for other in groups if other != outer], ignore_index=True)
        pd.testing.assert_frame_equal(inner[original.columns], original); pd.testing.assert_frame_equal(result[contexts[(outer,)].columns], contexts[(outer,)])
        assert decision['selection_groups'] == sorted(set(groups)-{outer}) and not decision['outer_labels_used_for_selection']
        base = reference_ice(inner, 'baseline_prediction'); compare(base, decision['original_report']); compare(reference_ice(inner, 'thermal_moisture'), decision['thermal_report'])
        for name in [*METHODS, CONTROL]:
            table = independent_thresholds(inner, inner[name+'_score'], inner.fallback, inner.baseline_prediction)
            saved = pd.read_csv(out / outer / (name+'_thresholds.csv'))
            np.testing.assert_allclose(table, saved, atol=1e-12, rtol=0); grid_rows += len(table)
            feasible = table.loc[(table.fp <= base['fp']) & (table.fn <= base['fn'])]; pool = feasible if len(feasible) else table.loc[table.fp <= base['fp']]
            t = float(pool.sort_values(['fixed_ice_day_f1', 'f1', 'threshold'], ascending=False).iloc[0].threshold)
            np.testing.assert_allclose(t, decision['thresholds'][name], atol=1e-15, rtol=0)
            for frame in [inner, result]:
                np.testing.assert_array_equal(frame['prediction_'+name], np.where(frame.fallback, frame.baseline_prediction, frame[name+'_score'].ge(t)).astype(int))
            a, g1 = guard(inner, 'prediction_'+name, 'baseline_prediction'); _, g2 = guard(inner, 'prediction_'+name, 'thermal_moisture')
            compare(a, decision['candidate_reports'][name]); compare(dict(original=g1, thermal14=g2, threshold_fp_fn_feasible=bool(len(feasible)), eligible=bool(all(g1.values()) and all(g2.values()) and len(feasible))), decision['guards'][name])
        eligible = [c for c in METHODS if decision['guards'][c]['eligible']]
        chosen = max(eligible, key=lambda c: (decision['candidate_reports'][c]['fixed_ice_day_f1'], decision['candidate_reports'][c]['f1'], c)) if eligible else 'original'
        assert chosen == decision['selected_candidate']
        np.testing.assert_array_equal(result.selected_prediction, result.baseline_prediction if chosen == 'original' else result['prediction_'+chosen]); parts.append(result)
        print('임계값·선택 검산', outer, flush=True)
    combined = pd.read_parquet(out / 'outer_predictions.parquet'); pd.testing.assert_frame_equal(combined, pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True))
    policies = {'original': 'baseline_prediction', 'thermal14': 'thermal_moisture', **{c: 'prediction_'+c for c in [*METHODS, CONTROL]}, 'selected': 'selected_prediction'}
    for name, column in policies.items():
        compare(reference_ice(combined, column), summary['metrics'][name])
        for reference, reference_column in [('original', 'baseline_prediction'), ('thermal14', 'thermal_moisture'), (CONTROL, 'prediction_'+CONTROL)]:
            _, checks = guard(combined, column, reference_column); compare(checks | {'eligible': all(checks.values())}, summary['development_guards'][name][reference])
    mask = combined.ice.notna() & ~combined.fallback
    for name in [*METHODS, CONTROL]:
        compare(dict(n=int(mask.sum()), positives=int(combined.loc[mask].ice.sum()), average_precision=float(average_precision_score(combined.loc[mask].ice, combined.loc[mask, name+'_score'])), probability_calibration_established=False), summary['score_metrics'][name])
    freezes = old_freezes()
    for name in ['fresh_station_validation_20261009_v2', 'temperature_blind_20261010_v1', 'temperature_mean_blind_20261010_v1']:
        verify_seal(ROOT / 'outputs/private' / name)
    assert len(receipts) == 70 and len(refits) == 7 and grid_rows == 11284
    audit = dict(status='independent_ice_methodology_audit_passed', audited_at_utc=datetime.now(timezone.utc).isoformat(), summary_sha256=sha(out / 'summary.json'),
                 audit_source_sha256=sha(Path(__file__)), history_values_verified=history_values, training_temperature_rows_replayed=temperature_rows,
                 query_temperature_rows_replayed=query_temperature_rows, reused_control_scores_replayed=control_values,
                 new_model_scores_replayed=score_values, model_fits_verified=len(receipts), representative_refits=refits, threshold_grid_rows_verified=grid_rows,
                 decisions_verified=4, ice_policies_verified=len(policies), old_frozen_files=freezes[0], reserved_frozen_files=freezes[1], model_promoted=False)
    target.write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8'); print(json.dumps(audit))


if __name__ == '__main__':
    main()
