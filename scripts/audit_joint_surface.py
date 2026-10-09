"""별도 계산으로 온도 교차 추정·그룹 제외·선택·예측 및 지표를 감사한다."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import average_precision_score
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validation import normalize_state
from src.external_reserved import verify_reserved_freeze
from src.frozen_assessment import verify_freeze


def read(p):
    return json.loads(Path(p).read_text('utf-8'))


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(2 ** 20), b''):
            h.update(b)
    return h.hexdigest()


def identity(frame):
    return hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).values.tobytes()).hexdigest()


def close(actual, expected):
    if actual is None or expected is None:
        assert actual is None and expected is None
    else:
        assert np.isclose(actual, expected, rtol=0, atol=1e-12), (actual, expected)


def counts(y, p):
    valid = np.isfinite(y); y = np.asarray(y)[valid]; p = np.asarray(p)[valid]
    tp = int(np.sum((y == 1) & (p == 1))); fp = int(np.sum((y == 0) & (p == 1)))
    fn = int(np.sum((y == 1) & (p == 0))); tn = int(np.sum((y == 0) & (p == 0)))
    return dict(n=len(y), tp=tp, fp=fp, fn=fn, tn=tn,
                f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
                precision=tp / (tp + fp) if tp + fp else None,
                recall=tp / (tp + fn) if tp + fn else None,
                fpr=fp / (fp + tn) if fp + tn else None)


def report(frame, prediction):
    d = frame[['station', 'time', 'ice']].copy(); d['p'] = np.asarray(prediction)
    result = counts(d.ice, d.p)
    stations = {s: counts(part.ice, part.p) for s, part in d.groupby('station')}
    daily = []; ice_by_station = {}; false_days = 0
    for (st, _), part in d.groupby(['station', d.time.dt.normalize()]):
        if part.ice.notna().sum() != 144:
            continue
        r = counts(part.ice, part.p); daily.append((st, r['f1']))
        if r['tp'] + r['fn']:
            ice_by_station.setdefault(st, []).append(r['f1'])
        elif r['fp']:
            false_days += 1
    events = []
    for _, part in d.groupby('station'):
        event = []; previous = None
        for row in part.sort_values('time').itertuples(index=False):
            if event and (row.ice != 1 or row.time - previous != pd.Timedelta(minutes=10)):
                events.append(event); event = []
            if row.ice == 1:
                event.append(int(row.p))
            previous = row.time
        if event:
            events.append(event)
    provisional = pd.DataFrame(daily, columns=['station', 'f1']).groupby('station').f1.mean().dropna()
    result.update(fixed_station_f1_zero_undefined=float(np.mean([r['f1'] or 0 for r in stations.values()])),
                  fixed_ice_day_f1=float(np.mean([np.mean(v) for v in ice_by_station.values()])) if ice_by_station else None,
                  fixed_ice_days=sum(map(len, ice_by_station.values())), fixed_ice_day_stations=len(ice_by_station),
                  complete_days=len(daily), false_alarm_nonice_days=false_days,
                  provisional_daily_station_f1=float(provisional.mean()) if len(provisional) else None,
                  events=len(events), detected_events=sum(any(e) for e in events),
                  single_slot_events=sum(len(e) == 1 for e in events),
                  detected_single_slot_events=sum(len(e) == 1 and any(e) for e in events))
    return result, stations


def independent_thresholds(d, score, fallback, baseline):
    valid = d.ice.notna().to_numpy(); f = d.loc[valid].copy()
    y = f.ice.to_numpy(dtype=int); s = np.asarray(score)[valid]
    fallback = np.asarray(fallback)[valid]; baseline = np.asarray(baseline)[valid]
    st = f.groupby('station', sort=True).ngroup().to_numpy()
    day = f.groupby(['station', f.time.dt.normalize()], sort=True).ngroup().to_numpy()
    nday = np.bincount(day); posday = np.bincount(day, weights=y)
    posst = np.bincount(st, weights=y)
    daystation = f.assign(day=day, st=st).groupby('day').st.first().to_numpy()
    included = (nday == 144) & (posday > 0)
    stationdays = np.bincount(daystation[included], minlength=len(posst)); active = stationdays > 0
    rows = []
    grid = np.unique(np.concatenate([[0.], np.geomspace(1e-6, 1., 401), [np.nextafter(1., 2.)]]))
    for t in grid:
        p = np.where(fallback, baseline, s >= t).astype(int)
        r = counts(y, p)
        st_tp = np.bincount(st, weights=p * y); st_den = posst + np.bincount(st, weights=p)
        st_f = np.divide(2 * st_tp, st_den, out=np.zeros_like(st_den), where=st_den > 0)
        day_tp = np.bincount(day, weights=p * y); day_den = posday + np.bincount(day, weights=p)
        day_f = np.divide(2 * day_tp, day_den, out=np.zeros_like(day_den), where=day_den > 0)
        total = np.bincount(daystation[included], weights=day_f[included], minlength=len(posst))
        rows.append(dict(threshold=t, tp=r['tp'], fp=r['fp'], fn=r['fn'], f1=r['f1'] or 0,
                         fixed_station_f1_zero_undefined=float(st_f.mean()),
                         fixed_ice_day_f1=float(np.mean(total[active] / stationdays[active])) if active.any() else 0.))
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--output', type=Path, help='재감사할 때 이전 영수증을 보존할 새 비공개 파일')
    args = parser.parse_args(); out = args.experiment.resolve()
    audit_output = args.output.resolve() if args.output else out / 'independent_verification.json'
    if not out.is_relative_to((ROOT / 'outputs/private').resolve()):
        parser.error('Only private local experiments allowed')
    if not audit_output.is_relative_to((ROOT / 'outputs/private').resolve()):
        parser.error('Audit receipt must stay private')
    if audit_output.exists():
        raise FileExistsError('Preserve completed audit')
    plan = read(out / 'experiment_plan.json'); summary = read(out / 'summary.json')
    assert summary['status'] == 'completed' and not summary['protected_or_reserved_outcomes_used']
    assert sha(out / 'experiment_plan.json') == summary['plan_sha256']
    assert sha(out / 'analysis_source.py') == sha(ROOT / 'scripts/evaluate_joint_surface.py')
    assert sha(out / 'joint_surface_source.py') == sha(ROOT / 'src/joint_surface.py')
    signatures = read(out / 'input_signature.json')
    for r in signatures.values():
        assert sha(r['path']) == r['sha256']
    previous_temperature_run = Path(signatures['temperature_receipts']['path']).parent
    for r in read(previous_temperature_run / 'input_signature.json').values():
        assert sha(r['path']) == r['sha256'], 'Changed source of reused temperature model'
    index = pd.read_parquet(signatures['development_index']['path'])
    temp = pd.read_parquet(signatures['temperature_index']['path'])
    raw = pd.read_parquet(signatures['features']['path'])
    pd.testing.assert_frame_equal(index[['station', 'time', 'group']], temp[['station', 'time', 'group']])
    assert index.time.ge('2024-11-01').all() and index.time.lt('2025-03-01').all()
    assert not set(index.station) & {'12410', '33411', '23402'}
    assert not index.duplicated(['station', 'time']).any()
    assert np.array_equal(index.ice, index.state_raw.map(normalize_state).to_numpy(dtype=float), equal_nan=True)
    weather = plan['regression_features']; features = plan['features']; params = plan['parameters']
    blocks = read(out / 'unit_blocks.json')
    units = {st: 'competition_' + st if g == 'competition' else g for st, g in index[['station', 'group']].drop_duplicates().itertuples(index=False)}
    order = {name: n % 3 for n, name in enumerate(sorted(set(units.values())))}
    assert blocks == {st: order[u] for st, u in units.items()}
    domain = np.isfinite(temp.road_temp) & raw.asos_air_temp.notna()
    receipts = read(out / 'fit_receipts.json'); models = {}; fit_refits = []
    for r in receipts:
        assert sha(r['model_path']) == r['model_sha256']
        model = joblib.load(r['model_path']); models[r['model_sha256']] = model
        assert all(model.get_params()[k] == v for k, v in params.items())
        assert list(model.feature_names_in_) == r['features']
        assert not set(r['forbidden_stations']) & set(r['training_stations'])
        assert not set(r['training_stations']) & {'12410', '33411', '23402'}
        if r['kind'] == 'temperature':
            mask = domain & ~index.station.isin(r['forbidden_stations'])
            assert int(mask.sum()) == r['training_rows'] and sorted(set(index.loc[mask, 'station'])) == r['training_stations']
            assert identity(temp.loc[mask, ['station', 'time', 'road_temp']]) == r['training_identity']
            if not r['reused'] and not fit_refits:
                clone = HistGradientBoostingRegressor(**params)
                with threadpool_limits(limits=2):
                    clone.fit(raw.loc[mask, weather], temp.loc[mask, 'road_temp'])
                    np.testing.assert_allclose(clone.predict(raw.loc[mask, weather].iloc[:1000]), model.predict(raw.loc[mask, weather].iloc[:1000]), atol=0, rtol=0)
                fit_refits.append('temperature')
    score_rows = 0; auxiliary_rows = 0; query_parts = {}
    old = pd.read_parquet(signatures['old_predictions']['path']).set_index(['station', 'time'])
    state_map = {'01': 0, '02': 1, '11': 1, '14': 1, '03': 2, '12': 3, '13': 4, '15': 5, '04': 6, '10': 7}
    for folder in sorted((out / 'contexts').iterdir()):
        provenance = read(folder / 'auxiliary_receipts.json'); held = provenance['forbidden_groups']
        forbidden = set(index.loc[index.group.isin(held), 'station'])
        train = index.ice.notna() & ~index.station.isin(forbidden); query = index.station.isin(forbidden)
        saved = pd.read_parquet(folder / 'training_features.parquet'); saved.index = pd.Index(saved.original_index)
        saved.index.name = None
        assert saved.original_index.tolist() == index.index[train].tolist()
        pd.testing.assert_frame_equal(saved[index.columns], index.loc[train], check_index_type=False)
        for a in provenance['auxiliary']:
            r = a['receipt']; block = a['block']
            expected = forbidden | {st for st, b in blocks.items() if b == block}
            assert expected == set(r['forbidden_stations'])
            rows = saved.auxiliary_block.eq(block); ids = saved.index[rows]
            assert set(saved.loc[rows, 'station']) <= {st for st, b in blocks.items() if b == block}
            assert not set(saved.loc[rows, 'station']) & set(r['training_stations'])
            with threadpool_limits(limits=2):
                predicted = models[r['model_sha256']].predict(raw.loc[ids, weather])
            predicted = np.where(raw.loc[ids].asos_air_temp.notna(), predicted, np.nan)
            np.testing.assert_allclose(saved.loc[rows, 'estimated_weather_temp'], predicted, rtol=0, atol=0, equal_nan=True)
            auxiliary_rows += len(ids)
        q = pd.read_parquet(folder / 'query_predictions.parquet'); ids = q.original_index.to_numpy()
        assert ids.tolist() == index.index[query].tolist()
        pd.testing.assert_frame_equal(q[index.columns].reset_index(drop=True), index.loc[query].reset_index(drop=True))
        assert set(provenance['full']['forbidden_stations']) == forbidden
        with threadpool_limits(limits=2):
            predicted = models[provenance['full']['model_sha256']].predict(raw.loc[ids, weather])
        predicted = np.where(raw.loc[ids].asos_air_temp.notna(), predicted, np.nan)
        np.testing.assert_allclose(q.estimated_weather_temp, predicted, rtol=0, atol=0, equal_nan=True)
        baseline = old.loc[pd.MultiIndex.from_frame(q[['station', 'time']])]
        np.testing.assert_array_equal(q.baseline_prediction, baseline.baseline_prediction)
        np.testing.assert_allclose(q.baseline_score, baseline.baseline_score, atol=0, rtol=0)
        np.testing.assert_array_equal(q.fallback, ~np.isfinite(predicted))
        def matrix(ids, t):
            x = raw.loc[ids, weather + ['rain15_max_3h', 'asos_snow_cm']].copy()
            x['estimated_weather_temp'] = t
            x['estimated_surface_dewpoint_gap'] = t - x.aws_dewpoint
            x['estimated_surface_air_gap'] = t - x.aws_air_temp
            wet = (x.aws_dewpoint.ge(t) | x.rain15_max_3h.gt(0) | x.asos_snow_cm.gt(0)).astype(float)
            x['moisture_evidence'] = wet.mask(x[['aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']].isna().all(axis=1) | ~np.isfinite(t))
            return x[features]
        train_x = matrix(saved.index, saved.estimated_weather_temp.to_numpy()); query_x = matrix(ids, predicted)
        pd.testing.assert_frame_equal(saved[features], train_x, check_index_type=False)
        water = raw.loc[ids, ['aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']].to_numpy()
        wet = (water[:, 0] >= predicted) | (water[:, 1] > 0) | (water[:, 2] > 0)
        fallback = ~np.isfinite(predicted) | np.isnan(water).all(axis=1)
        thermal = np.where(fallback, q.baseline_prediction, (predicted <= 0) & wet).astype(int)
        np.testing.assert_array_equal(q.thermal_moisture, thermal)
        for candidate in plan['candidates']:
            r = next(r for r in receipts if r['kind'] == 'classifier' and r['candidate'] == candidate and r['context_groups'] == held)
            assert r['matrix_sha256'] == sha(folder / 'training_features.parquet')
            assert r['training_identity'] == identity(saved)
            assert r['training_rows'] == len(saved) and r['training_stations'] == sorted(set(saved.station))
            assert set(r['forbidden_stations']) == forbidden
            model = models[r['model_sha256']]; joint = candidate == 'joint_surface_state'
            labels = np.array([state_map[str(int(float(v))).zfill(2)] for v in saved.state_raw]) if joint else saved.ice.to_numpy(dtype=int)
            assert r['label_counts'] == {str(float(k)): int(v) for k, v in pd.Series(labels).value_counts().items()}
            weights = np.where(saved.ice.eq(1), plan['ice_weight'], 1.)
            if candidate not in fit_refits:
                clone = HistGradientBoostingClassifier(**params)
                with threadpool_limits(limits=2):
                    clone.fit(train_x, labels, sample_weight=weights)
                    np.testing.assert_allclose(clone.predict_proba(query_x), model.predict_proba(query_x), rtol=0, atol=0)
                fit_refits.append(candidate)
            with threadpool_limits(limits=2):
                probabilities = model.predict_proba(query_x)
            assert np.isfinite(probabilities).all() and np.allclose(probabilities.sum(axis=1), 1)
            col = list(model.classes_).index(6 if joint else 1)
            score = np.where(q.fallback, q.baseline_score, probabilities[:, col])
            np.testing.assert_allclose(q[candidate + '_score'], score, atol=0, rtol=0)
            score_rows += len(q)
        query_parts[tuple(held)] = q
        print('Audited context:', held, flush=True)
    decisions = read(out / 'decisions.json'); outer = pd.read_parquet(out / 'outer_predictions.parquet')
    seal = read(out / 'prediction_seal.json')
    assert sha(out / 'outer_predictions.parquet') == seal['sha256']
    assert sha(out / 'decisions.json') == seal['decisions_sha256']
    threshold_rows = 0
    for group, decision in decisions.items():
        assert not decision['outer_labels_used'] and decision['decided_at_utc'] < seal['timestamp_utc']
        inner = pd.concat([query_parts[tuple(sorted([group, h]))].loc[lambda d: d.group.eq(h)] for h in decision['inner_groups']])
        br, bs = report(inner, inner.thermal_moisture)
        for key, value in br.items():
            close(value, decision['baseline'][key])
        eligible = []
        for c in plan['candidates']:
            table = independent_thresholds(inner, inner[c + '_score'], inner.fallback, inner.baseline_prediction)
            saved_table = pd.read_csv(out / 'decisions' / (group + '__' + c + '__thresholds.csv'))
            np.testing.assert_allclose(table, saved_table[table.columns], atol=1e-12, rtol=0); threshold_rows += len(table)
            feasible = table[table.fp.le(br['fp'])]
            threshold = feasible.sort_values(['fixed_ice_day_f1', 'f1', 'threshold'], ascending=False).iloc[0].threshold
            close(threshold, decision['thresholds'][c])
            p = np.where(inner.fallback, inner.baseline_prediction, inner[c + '_score'] >= threshold).astype(int)
            cr, cs = report(inner, p)
            for key, value in cr.items():
                close(value, decision['candidates'][c][key])
            checks = dict(f1_guards=all((cr[k] or 0) + 1e-12 >= (br[k] or 0) for k in ['f1', 'fixed_ice_day_f1', 'fixed_station_f1_zero_undefined']),
                          strict_improvement=any((cr[k] or 0) > (br[k] or 0) + 1e-12 for k in ['f1', 'fixed_ice_day_f1']),
                          false_alarm_budget=cr['fp'] <= br['fp'],
                          single_slot_guard=cr['detected_single_slot_events'] >= br['detected_single_slot_events'],
                          station_recall_guard=all(cs[s]['tp'] >= bs[s]['tp'] for s in bs if bs[s]['tp'] + bs[s]['fn'] >= 5))
            assert checks == decision['guards'][c]
            if all(checks.values()):
                eligible.append(c)
        selected = min(eligible, key=lambda c: (-decision['candidates'][c]['fixed_ice_day_f1'], -decision['candidates'][c]['f1'], c)) if eligible else 'thermal_moisture'
        assert decision['selected'] == selected and decision['eligible'] == eligible
        q = query_parts[(group,)]; output = outer[outer.group.eq(group)]
        for c in plan['candidates']:
            p = np.where(q.fallback, q.baseline_prediction, q[c + '_score'] >= decision['thresholds'][c]).astype(int)
            np.testing.assert_array_equal(p, output[c])
        np.testing.assert_array_equal(output.selected_prediction, output[selected])
    for policy, expected in summary['metrics'].items():
        actual, _ = report(outer, outer[policy])
        if policy in plan['candidates']:
            valid = outer.ice.notna()
            actual['average_precision'] = float(average_precision_score(outer.loc[valid, 'ice'], outer.loc[valid, policy + '_score']))
        assert actual.keys() == expected.keys()
        for key in actual:
            close(actual[key], expected[key])
    assert not outer.duplicated(['station', 'time']).any()
    assert outer.original_index.tolist() == index.index[index.group.ne('competition')].tolist()
    pd.testing.assert_frame_equal(outer[index.columns].reset_index(drop=True), index.loc[index.group.ne('competition')].reset_index(drop=True))
    release = ROOT / 'outputs/private/releases/20261007'
    external_freeze = verify_reserved_freeze(release, release / 'outputs/private/external_reserved_predictions_v1')
    original_freeze = verify_freeze(release)
    result = dict(status='passed', checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  fit_receipts=len(receipts), auxiliary_training_predictions=auxiliary_rows,
                  classifier_query_scores=score_rows, threshold_rows=threshold_rows,
                  representative_refits=fit_refits, outer_rows=len(outer), outer_policies=len(summary['metrics']),
                  frozen_external_files=len(external_freeze['files']), frozen_original_files=len(original_freeze['files']),
                  summary_sha256=sha(out / 'summary.json'), source_sha256=sha(__file__))
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
