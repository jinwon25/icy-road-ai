"""전이 모델 재실행·별도 상태 재귀·일별 지표·지역 분리·선택을 독립 대조한다."""
import argparse
from collections import Counter, defaultdict
from pathlib import Path
import sys
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_icing_transition import read, write, load_inputs, features, score_name
from scripts.evaluate_thermal_classification import available
from scripts.evaluate_method_blending import preservation


def independent_metrics(frame, prediction):
    y = frame.ice.to_numpy(float); p = np.asarray(prediction, float)
    valid = np.isin(y, [0, 1]) & np.isfinite(p)
    pop = sorted(frame.station.unique())
    codes, keys = pd.factorize(pd.MultiIndex.from_arrays([frame.station[valid], frame.time[valid].dt.normalize()]), sort=True)
    y, p = y[valid], p[valid]
    n = np.bincount(codes, minlength=len(keys))
    tp = np.bincount(codes, weights=(y == 1) & (p == 1), minlength=len(keys))
    fp = np.bincount(codes, weights=(y == 0) & (p == 1), minlength=len(keys))
    fn = np.bincount(codes, weights=(y == 1) & (p == 0), minlength=len(keys))
    output = {'fp': int(fp.sum()), 'tp': int(tp.sum()), 'fn': int(fn.sum())}
    for metric, numerator, denominator in [('precision', tp, tp+fp), ('recall', tp, tp+fn), ('f1', 2*tp, 2*tp+fp+fn)]:
        by_station = defaultdict(list)
        for i in np.flatnonzero((n >= 144) & (denominator > 0)):
            by_station[keys[i][0]].append(float(numerator[i] / denominator[i]))
        averages = [float(np.mean(by_station[s])) for s in pop if by_station[s]]
        output[metric+'_available_station_mean'] = float(np.mean(averages)) if averages else None
        if metric == 'f1':
            output['f1_fixed_population'] = float(sum(averages) / len(pop))
    return output


def independent_events(frame, prediction, baseline):
    y, p, b = frame.ice.to_numpy(float), np.asarray(prediction), np.asarray(baseline)
    counter = Counter(); old_hit = new_hit = False; ongoing = False; previous = None
    def finish():
        counter['observed_events'] += 1
        counter['baseline_detected'] += int(old_hit); counter['candidate_detected'] += int(new_hit)
        counter['lost_events'] += int(old_hit and not new_hit); counter['gained_events'] += int(new_hit and not old_hit)
    for station, moment, target, pred, base in zip(frame.station, frame.time.to_numpy().view('int64'), y, p, b):
        active = target == 1 and np.isfinite(pred) and np.isfinite(base)
        contiguous = previous is not None and station == previous[0] and moment - previous[1] == 600_000_000_000
        if ongoing and (not active or not contiguous):
            finish(); ongoing = False
        if active:
            if not ongoing: old_hit = new_hit = False
            old_hit |= base == 1; new_hit |= pred == 1; ongoing = True
        previous = station, moment
    if ongoing: finish()
    return {k: counter[k] for k in ['observed_events', 'baseline_detected', 'candidate_detected', 'lost_events', 'gained_events']}


def check_study(study, source):
    summary = read(study / 'summary.json'); frame = pd.read_parquet(study / 'predictions.parquet')
    for relative, signature in summary['files'].items():
        assert sha(study / relative) == signature, relative
    reports = summary['reports']; checks = 0
    for method, records in reports.items():
        for year in ['all', 2024, 2025]:
            f = frame if year == 'all' else frame.loc[frame.winter.eq(year)]
            actual = independent_metrics(f, f[method])
            for metric in ['f1_fixed_population', 'precision_available_station_mean', 'recall_available_station_mean']:
                expected = records[str(year)][metric]
                if expected is None: assert actual[metric] is None
                else: np.testing.assert_allclose(actual[metric], expected, rtol=0, atol=1e-12)
            checks += 1
        assert independent_events(frame, frame[method], frame.current) == records['events']
    decisions = read(study / 'decisions.json'); groups = sorted(decisions); selection_checks = 0
    source_plan = read(source / 'plan.json')['settings']; names = [s['name'] for s in source_plan['candidates']]
    models = {n+'_m'+str(round(a*100)): (n, score_name(a)) for n in names for a in source_plan['memory_strengths']}
    cached = {}
    def load(name, key):
        model, column = models[name]; relative = model + '/' + '__'.join(key) + '.parquet'
        if relative not in cached: cached[relative] = pd.read_parquet(source / relative)
        return cached[relative], column
    for outer, decision in decisions.items():
        for method, choice in decision['choices'].items():
            candidate = choice['candidate']; inner_parts = []
            for held in groups:
                if held == outer: continue
                q, column = load(next(iter(models)) if candidate == 'asos_zero' else candidate, tuple(sorted([outer, held])))
                f = q.loc[q.group.eq(held)].copy()
                score = f.asos_air_temp.le(0) if candidate == 'asos_zero' else f[column]
                f['p'] = np.where(f.available, score >= choice['threshold'], np.nan); inner_parts.append(f)
            inner = pd.concat(inner_parts, ignore_index=True)
            assert not set(inner.station) & set(decision['held_stations'])
            r = independent_metrics(inner, inner.p)
            np.testing.assert_allclose(r['f1_fixed_population'], choice['mean_f1'], atol=1e-12, rtol=0)
            assert r['fp'] == choice['fp']
            winters = [independent_metrics(inner.loc[inner.winter.eq(y)], inner.loc[inner.winter.eq(y), 'p'])['f1_fixed_population'] for y in [2024, 2025]]
            np.testing.assert_allclose(min(winters), choice['worst_winter_f1'], atol=1e-12, rtol=0)
            q, column = load(next(iter(models)) if candidate == 'asos_zero' else candidate, (outer,))
            score = q.asos_air_temp.le(0) if candidate == 'asos_zero' else q[column]
            expected = np.where(q.available, score >= choice['threshold'], np.nan)
            actual = frame.loc[frame.group.eq(outer), method].to_numpy()
            np.testing.assert_array_equal(actual, expected)
            selection_checks += 1
    return dict(metric_checks=checks, event_checks=len(reports), nested_selection_checks=selection_checks,
                summary_sha256=sha(study/'summary.json'), predictions_sha256=sha(study/'predictions.parquet'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', required=True, type=Path); parser.add_argument('--exact', type=Path); parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(); study, out = args.study.resolve(), args.output.resolve()
    if out.exists() or not out.is_relative_to((ROOT/'outputs/private').resolve()): raise ValueError('New private audit output required')
    out.mkdir(parents=True); plan = read(study/'plan.json'); summary = read(study/'summary.json')
    for path, signature in plan['signatures'].items(): assert sha(ROOT/path) == signature, path
    for path, signature in summary['files'].items(): assert sha(study/path) == signature, path
    frozen = preservation(); data, _ = load_inputs(plan['settings']); valid = available(data).to_numpy(bool)
    # pandas shift를 재사용하지 않고 지점별 마지막 시각/상태를 직접 추적한다.
    previous = np.full(len(data), np.nan); last = {}
    for i, (station, t, y) in enumerate(zip(data.station, data.time.to_numpy().view('int64'), data.ice)):
        old = last.get(station)
        if old is not None and t-old[0] == 600_000_000_000 and valid[i] and old[2] and np.isfinite(y) and np.isfinite(old[1]): previous[i] = old[1]
        last[station] = t, y, valid[i]
    feature_cache = {}; total_values = 0; max_error = 0.; receipts = []
    for receipt in read(study/'fit_receipts.json'):
        spec = next(s for s in plan['settings']['candidates'] if s['name'] == receipt['candidate'])
        key = receipt['excluded_groups']; query_mask = data.group.isin(key); train = data.loc[~query_mask & np.isfinite(previous)]
        assert sorted(train.station.unique()) == receipt['training_stations'] and len(train) == receipt['training_rows']
        assert not set(train.station) & set(receipt['query_stations'])
        np.testing.assert_equal(float(train.ice.mean()), receipt['prior'])
        if spec['weights'] == 'row':
            weights = np.ones(len(train))
        else:
            prev = previous[~query_mask & np.isfinite(previous)]
            strata = list(zip(train.station, train.winter, prev, train.ice))
            frequencies = Counter(strata); kinds = defaultdict(set)
            for station, winter, old, new in frequencies:
                kinds[(station, winter)].add((old, new))
            weights = np.array([1. / (frequencies[k] * len(kinds[k[:2]])) for k in strata])
            weights /= weights.mean(); weights = np.minimum(weights, 20.); weights /= weights.mean()
        np.testing.assert_allclose([weights.min(), weights.max(), weights.mean()],
                                   [receipt['weight_min'], receipt['weight_max'], receipt['weight_mean']], atol=1e-12, rtol=0)
        if spec['features'] not in feature_cache: feature_cache[spec['features']] = features(data, spec['features'])
        x = feature_cache[spec['features']].loc[query_mask].copy(); x['previous_ice_state'] = 0.
        stem = study/spec['name']/'__'.join(key); model = joblib.load(stem.with_suffix('.joblib')); q = pd.read_parquet(stem.with_suffix('.parquet'))
        assert list(x) == receipt['features'] == list(model.feature_names_in_)
        with threadpool_limits(limits=2):
            p0 = model.predict_proba(x)[:,1]; x['previous_ice_state'] = 1.; p1 = model.predict_proba(x)[:,1]
        np.testing.assert_array_equal(p0, q.p0); np.testing.assert_array_equal(p1, q.p1)
        for a in plan['settings']['memory_strengths']:
            expected = np.full(len(q), np.nan); states = {}; prior = receipt['prior']
            for i, (station, t, ok) in enumerate(zip(q.station, q.time.to_numpy().view('int64'), q.available)):
                old = states.get(station)
                if not ok:
                    states.pop(station, None); continue
                last_state = old[1] if old is not None and t-old[0] == 600_000_000_000 else prior
                mix = a*last_state+(1-a)*prior
                expected[i] = p0[i] + (p1[i]-p0[i])*mix
                states[station] = t, expected[i]
            actual = q[score_name(a)].to_numpy()
            np.testing.assert_allclose(expected, actual, rtol=0, atol=2e-12, equal_nan=True)
            total_values += len(q); max_error = max(max_error, float(np.nanmax(np.abs(expected-actual))))
        receipts.append(dict(candidate=spec['name'], excluded_groups=key, model_sha256=sha(stem.with_suffix('.joblib')), rows=len(q)))
        write(out/'progress.json', dict(models_replayed=len(receipts), planned_models=30))
        print('모델·상태 재검산', spec['name'], key, flush=True)
    checks = {'fixed_grid': check_study(study, study)}
    if args.exact: checks['exact_threshold'] = check_study(args.exact.resolve(), study)
    assert preservation() == frozen
    write(out/'receipt.json', dict(status='icing_transition_independently_verified', models_replayed=len(receipts), state_values_checked=total_values,
          state_max_absolute_error=max_error, checks=checks, models=receipts, frozen_counts=frozen, protected_labels_read=False,
          audit_code_sha256=sha(Path(__file__)), new_independent_assessment=False))


if __name__ == '__main__': main()
