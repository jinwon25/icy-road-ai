"""여섯 결빙 대안을 같은 첫 겨울 공간 중첩 분할에서 비교한다."""
import argparse
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
from pathlib import Path
import shutil
import sys
import time

import catboost
from catboost import CatBoostClassifier
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.ice_methodology import CANDIDATES, HISTORY_COLUMNS, HISTORY_FEATURES, causal_history, candidate_features, training_weights, hurdle_labels, binary_score
from src.joint_surface import FEATURES, WEATHER, thermal_features, unit_blocks, threshold_prediction, threshold_table
from src.method_blending import domain, ice_guard
from src.thermal_ice import diagnostic_report
from scripts.evaluate_method_blending import preservation, read, write, PRIVATE

SOURCE = PRIVATE / 'joint_surface_20261009_v1'
CONFIG = ROOT / 'config/ice_methodology_experiment.json'
DEFAULT = PRIVATE / 'ice_methodology_20261010_v1'
CONTROL = 'binary100_control'


def signature_weights(w):
    return hashlib.sha256(np.asarray(w, dtype='<f8').tobytes()).hexdigest()


def threshold_choice(frame, name, baseline):
    table = threshold_table(frame, frame[name+'_score'], frame.fallback, frame.baseline_prediction)
    feasible = table.loc[table.fp.le(baseline['fp']) & table.fn.le(baseline['fn'])]
    pool = feasible if len(feasible) else table.loc[table.fp.le(baseline['fp'])]
    if pool.empty:
        raise ValueError('No threshold with baseline FP budget')
    threshold = float(pool.sort_values(['fixed_ice_day_f1', 'f1', 'threshold'], ascending=False).iloc[0].threshold)
    return threshold, table, bool(len(feasible))


def fit_one(plan, candidate, x, y, weights, path):
    if candidate == 'catboost400':
        model = CatBoostClassifier(**plan['catboost'])
    else:
        model = HistGradientBoostingClassifier(**(plan['hgb'] | ({'max_iter': 300} if candidate == 'hgb_long300' else {})))
    started = time.perf_counter()
    with threadpool_limits(limits=2):
        model.fit(x, y.astype(int), sample_weight=weights)
    joblib.dump(model, path, compress=3)
    return model, dict(model_path=str(path), model_sha256=sha(path), candidate=candidate, rows=len(x), features=list(x),
                       weight_sha256=signature_weights(weights), weight_sum=float(weights.sum()),
                       label_counts={str(k): int(v) for k, v in pd.Series(y).value_counts().items()},
                       fit_seconds=time.perf_counter()-started)


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, default=DEFAULT)
    out = parser.parse_args().output.resolve()
    if out.exists() or not out.is_relative_to(PRIVATE.resolve()):
        raise ValueError('New private experiment directory required')
    plan = read(CONFIG)
    if plan['candidates'] != list(CANDIDATES) or plan['history_columns'] != list(HISTORY_COLUMNS):
        raise ValueError('Fixed library differs')
    freeze = preservation(); previous = read(SOURCE / 'independent_verification.json')
    if previous['status'] != 'passed' or previous['summary_sha256'] != sha(SOURCE / 'summary.json'):
        raise ValueError('Independently audited cross-fit source required')
    signatures = {}
    def pin(path):
        signatures[str(path.relative_to(ROOT))] = sha(path)
    for p in [Path(__file__), CONFIG, ROOT / 'src/ice_methodology.py', ROOT / 'src/joint_surface.py', ROOT / 'src/method_blending.py', ROOT / 'src/thermal_ice.py', ROOT / 'scripts/evaluate_method_blending.py', SOURCE / 'summary.json', SOURCE / 'independent_verification.json', SOURCE / 'input_signature.json', SOURCE / 'fit_receipts.json']:
        pin(p)
    paths = read(SOURCE / 'input_signature.json')
    for k in ['development_index', 'features']:
        p = Path(paths[k]['path']); pin(p)
        if sha(p) != paths[k]['sha256']:
            raise ValueError('Original development input changed')
    index = domain(pd.read_parquet(paths['development_index']['path']))
    weather = pd.read_parquet(paths['features']['path'])[WEATHER+['rain15_max_3h', 'asos_snow_cm']]
    if len(index) != len(weather) or set(index.station) != set(unit_blocks(index)):
        raise ValueError('Misaligned development weather')
    blocks = unit_blocks(index); groups = sorted(set(index.group)-{'competition'})
    out.mkdir(); shutil.copy2(Path(__file__), out / 'analysis_source.py'); shutil.copy2(ROOT / 'src/ice_methodology.py', out / 'methodology_source.py')
    write(out / 'experiment_plan.json', plan | dict(started_at_utc=datetime.now(timezone.utc).isoformat(),
          versions=dict(sklearn=sklearn.__version__, catboost=catboost.__version__, numpy=np.__version__, pandas=pd.__version__),
          new_independent_assessment=False, library_frozen_before_new_fits=True))
    write(out / 'groups.json', {g: sorted(set(index.loc[index.group.eq(g), 'station'])) for g in groups})
    receipts, cache = [], {}
    for key in [*(tuple([g]) for g in groups), *combinations(groups, 2)]:
        old_folder = SOURCE / 'contexts' / '__'.join(key)
        folder = out / 'contexts' / '__'.join(key); folder.mkdir(parents=True)
        for filename in ['training_features.parquet', 'query_predictions.parquet', 'auxiliary_receipts.json']:
            pin(old_folder / filename)
        saved = pd.read_parquet(old_folder / 'training_features.parquet')
        q = domain(pd.read_parquet(old_folder / 'query_predictions.parquet')).copy()
        provenance = read(old_folder / 'auxiliary_receipts.json')
        forbidden = set(index.loc[index.group.isin(key), 'station'])
        if set(provenance['forbidden_groups']) != set(key) or set(q.station) != forbidden:
            raise ValueError('Wrong query exclusions')
        # 정답 미정의 행도 기상 이력에 포함한다. 정답의 유효 여부를 이력 결측 신호로 만들지 않는다.
        complete = index.loc[~index.station.isin(forbidden)].copy(); complete['original_index'] = complete.index
        temperature = pd.Series(np.nan, index=complete.index)
        temperature.loc[saved.original_index] = saved.estimated_weather_temp.to_numpy()
        extra = complete.index.difference(saved.original_index)
        for auxiliary in provenance['auxiliary']:
            r = auxiliary['receipt']; model_path = Path(r['model_path']); pin(model_path)
            if sha(model_path) != r['model_sha256'] or forbidden & set(r['training_stations']):
                raise ValueError('Invalid auxiliary temperature receipt')
            rows = extra[complete.loc[extra].station.map(blocks).eq(auxiliary['block'])]
            if set(complete.loc[rows].station) & set(r['training_stations']):
                raise ValueError('Own station entered history temperature model')
            if len(rows):
                model = joblib.load(model_path)
                with threadpool_limits(limits=2):
                    estimates = model.predict(weather.loc[rows, WEATHER])
                temperature.loc[rows] = np.where(weather.loc[rows].asos_air_temp.notna(), estimates, np.nan)
        x_all = thermal_features(weather.loc[complete.index], temperature)
        history_input = pd.concat([complete[['station', 'time']], x_all], axis=1)
        history = causal_history(history_input)
        training = pd.concat([complete[['station', 'time', 'group', 'ice', 'state_raw', 'original_index']], x_all, history], axis=1)
        mask = training.ice.notna(); train = training.loc[mask].copy()
        pd.testing.assert_frame_equal(train[FEATURES].reset_index(drop=True), saved[FEATURES].reset_index(drop=True))
        if set(train.station) & forbidden:
            raise ValueError('Held group entered classifier fit')
        training.to_parquet(folder / 'training_inputs.parquet', index=False, compression='zstd')
        qx = thermal_features(weather.loc[q.original_index], q.estimated_weather_temp)
        qx.index = q.index
        query_input = pd.concat([q[['station', 'time']], qx], axis=1)
        qh = causal_history(query_input)
        pd.concat([q[['station', 'time', 'original_index']], qx, qh], axis=1).to_parquet(folder / 'query_inputs.parquet', index=False, compression='zstd')
        q[CONTROL+'_score'] = q.binary_thermal_weather_score
        for name in CANDIDATES:
            tx = candidate_features(train, name, train[HISTORY_FEATURES] if name == 'hgb_history' else None)
            vx = candidate_features(qx, name, qh if name == 'hgb_history' else None)
            labels = train.ice.to_numpy(int)
            if name == 'hurdle_non_dry':
                non_dry, official = hurdle_labels(train.state_raw)
                np.testing.assert_array_equal(official, labels)
                stages = [('non_dry', np.ones(len(train), bool), non_dry, training_weights(non_dry, positive_weight=1.)),
                          ('conditional_ice', non_dry.astype(bool), labels[non_dry == 1], training_weights(labels[non_dry == 1], positive_weight=20.))]
                score = np.ones(len(q))
                for stage, rows, y, weights in stages:
                    model, receipt = fit_one(plan, name, tx.loc[rows], y, weights, folder / (name+'_'+stage+'.joblib'))
                    with threadpool_limits(limits=2):
                        score *= binary_score(model, vx)
                    receipt['stage'] = stage; receipts.append(receipt)
            else:
                weights = training_weights(labels, balanced=name == 'hgb_balanced', positive_weight=20.)
                model, receipt = fit_one(plan, name, tx, labels, weights, folder / (name+'.joblib'))
                with threadpool_limits(limits=2):
                    score = binary_score(model, vx)
                receipt['stage'] = 'binary'; receipts.append(receipt)
            for r in receipts:
                if 'context_groups' not in r:
                    r.update(context_groups=list(key), training_stations=sorted(set(train.station)), forbidden_stations=sorted(forbidden),
                             training_matrix_sha256=sha(folder / 'training_inputs.parquet'))
            q[name+'_score'] = np.where(q.fallback, q.baseline_score, score)
            (out / 'fit_receipts.json').write_text(json.dumps(receipts, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
            print('학습 완료', '__'.join(key), name, round(receipts[-1]['fit_seconds'], 2), flush=True)
        q.to_parquet(folder / 'query_predictions.parquet', index=False, compression='zstd'); cache[key] = q
    write(out / 'input_signatures.json', signatures)
    decisions, parts = {}, []
    for outer in groups:
        directory = out / outer; directory.mkdir()
        inner = pd.concat([cache[tuple(sorted([outer, held]))].loc[lambda f: f.group.eq(held)] for held in groups if held != outer], ignore_index=True)
        original, os, _, _ = diagnostic_report(inner, inner.baseline_prediction)
        thermal, ts, _, _ = diagnostic_report(inner, inner.thermal_moisture)
        reports, thresholds, guards = {}, {}, {}
        for name in [*CANDIDATES, CONTROL]:
            threshold, table, feasible = threshold_choice(inner, name, original); thresholds[name] = threshold
            table.to_csv(directory / (name+'_thresholds.csv'), index=False)
            inner['prediction_'+name] = threshold_prediction(inner[name+'_score'], threshold, inner.fallback, inner.baseline_prediction)
            r, stations, _, _ = diagnostic_report(inner, inner['prediction_'+name]); reports[name] = r
            ok1, g1 = ice_guard(r, original, stations, os); ok2, g2 = ice_guard(r, thermal, stations, ts)
            guards[name] = dict(original=g1, thermal14=g2, threshold_fp_fn_feasible=feasible, eligible=bool(ok1 and ok2 and feasible))
        eligible = [c for c in CANDIDATES if guards[c]['eligible']]
        chosen = max(eligible, key=lambda c: (reports[c]['fixed_ice_day_f1'], reports[c]['f1'], c)) if eligible else 'original'
        decision = dict(outer_group=outer, selection_groups=sorted(set(groups)-{outer}), selected_candidate=chosen, thresholds=thresholds,
                        original_report=original, thermal_report=thermal, candidate_reports=reports, guards=guards, outer_labels_used_for_selection=False)
        write(directory / 'decision.json', decision); decisions[outer] = decision
        inner.to_parquet(directory / 'inner_predictions.parquet', index=False, compression='zstd')
        result = cache[(outer,)].copy()
        for name in [*CANDIDATES, CONTROL]:
            result['prediction_'+name] = threshold_prediction(result[name+'_score'], thresholds[name], result.fallback, result.baseline_prediction)
        result['selected_candidate'] = chosen
        result['selected_prediction'] = result.baseline_prediction if chosen == 'original' else result['prediction_'+chosen]
        result.to_parquet(directory / 'outer_predictions.parquet', index=False, compression='zstd'); parts.append(result)
        print('내부 선택', outer, chosen, flush=True)
    combined = pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    combined.to_parquet(out / 'outer_predictions.parquet', index=False, compression='zstd')
    policies = {'original': 'baseline_prediction', 'thermal14': 'thermal_moisture', **{c: 'prediction_'+c for c in [*CANDIDATES, CONTROL]}, 'selected': 'selected_prediction'}
    metrics, stations, guards = {}, {}, {}
    for name, column in policies.items():
        r, st, days, events = diagnostic_report(combined, combined[column]); metrics[name] = r; stations[name] = st
        st.to_csv(out / (name+'_stations.csv'), index=False); days.to_csv(out / (name+'_days.csv'), index=False); events.to_csv(out / (name+'_events.csv'), index=False)
    for name in policies:
        g = {}
        for comparator in ['original', 'thermal14', CONTROL]:
            ok, checks = ice_guard(metrics[name], metrics[comparator], stations[name], stations[comparator]); g[comparator] = checks | {'eligible': ok}
        guards[name] = g
    usable = combined.ice.notna() & ~combined.fallback; score_metrics = {}
    for name in [*CANDIDATES, CONTROL]:
        s, y = combined.loc[usable, name+'_score'].to_numpy(), combined.loc[usable, 'ice'].to_numpy()
        score_metrics[name] = dict(n=len(y), positives=int(y.sum()), average_precision=float(average_precision_score(y, s)), probability_calibration_established=False)
    write(out / 'decisions.json', decisions)
    for rel, digest in signatures.items():
        if sha(ROOT / rel) != digest:
            raise ValueError('Pinned study source changed during fit')
    if preservation() != freeze or metrics['original']['n'] != 155118 or len(receipts) != 70:
        raise ValueError('Frozen assessment, denominator or fit library differs')
    summary = dict(status='six_ice_methods_development_complete', completed_at_utc=datetime.now(timezone.utc).isoformat(),
                   new_model_fits=len(receipts), temperature_fits=0, contexts=len(cache), outer_rows=len(combined),
                   metrics=metrics, score_metrics=score_metrics, development_guards=guards, choices={g: d['selected_candidate'] for g, d in decisions.items()},
                   threshold_grid_rows=4*7*403, old_frozen_files=freeze[0], reserved_frozen_files=freeze[1],
                   model_promoted=False, new_independent_assessment=False, assessment_outcomes_used=False,
                   files={p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob('*')) if p.is_file()})
    write(out / 'summary.json', summary)
    print(json.dumps({k: summary[k] for k in ['status', 'new_model_fits', 'choices']}))


if __name__ == '__main__':
    main()
