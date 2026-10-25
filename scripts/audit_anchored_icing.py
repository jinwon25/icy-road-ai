"""저장 모델·전처리·제한 보정·전체 내부 후보 선택·일별 성능을 독립 검산한다."""
import argparse
from itertools import combinations
from pathlib import Path
import sys
import warnings
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.anchored_icing import linear_features
from src.two_winter import validate
from src.data_source import sha256_file as sha
from scripts.evaluate_synoptic_icing import read, write, KEYS
from scripts.evaluate_thermal_classification import available
from scripts.audit_icing_transition import independent_metrics, independent_events
from scripts.audit_synoptic_icing import independent_weights
from scripts.evaluate_method_blending import preservation


def manual_prediction(frame, spec, scores):
    air = frame.asos_air_temp.to_numpy(float)
    if 'threshold' in spec:
        alarm = air <= spec['threshold']
    else:
        correction = (scores[spec['model']] * 2 - 1) * spec['bound']
        if spec['direction'] == 'reject_only':
            correction[correction > 0] = 0
        alarm = air <= correction
        far = np.abs(air) > spec['bound']
        assert np.array_equal(alarm[far], air[far] <= 0)
        if spec['direction'] == 'reject_only':
            assert not (alarm & (air > 0)).any()
    return np.where(frame.available, alarm, np.nan)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); study = args.study.resolve(); out = args.output.resolve()
    if out.exists() or not out.is_relative_to((ROOT / 'outputs/private').resolve()):
        raise ValueError('New private output required')
    summary = read(study / 'summary.json'); plan = read(study / 'plan.json')['settings']
    for name, digest in summary['source_signatures'].items():
        assert sha(ROOT / name) == digest, name
    for name, digest in summary['files'].items():
        assert sha(study / name) == digest, name
    frozen = preservation(); out.mkdir(parents=True)
    data = validate(pd.read_parquet(ROOT / plan['data'])).sort_values(['station', 'time']).reset_index(drop=True)
    f = pd.read_parquet(study / 'predictions.parquet'); x = linear_features(data); valid = available(data)
    groups = sorted(set(data.group) - {'competition'})
    contexts = [*((g,) for g in groups), *combinations(groups, 2)]
    specs = read(study / 'policies.json'); cache = {}; replays = 0
    for spec in plan['linear_models']:
        name = spec['name']; cache[name] = {}
        for key in contexts:
            stem = study / name / '__'.join(key)
            record = read(stem.with_suffix('.json'))
            assert sha(stem.with_suffix('.joblib')) == record['model_sha256']
            assert sha(stem.with_suffix('.parquet')) == record['prediction_sha256']
            qm = data.group.isin(key); tm = ~qm & valid & data.ice.isin([0, 1]); train = data.loc[tm]
            assert not set(train.station) & set(data.loc[qm, 'station'])
            assert sorted(train.station.unique()) == record['training_stations']
            assert sorted(data.loc[qm, 'station'].unique()) == record['query_stations']
            assert len(train) == record['training_rows'] and int(qm.sum()) == record['query_rows']
            w = independent_weights(train) if spec['weights'] == 'day' else np.ones(len(train))
            np.testing.assert_allclose([w.sum(), np.average(train.ice, weights=w)],
                [record['training_weight_sum'], record['weighted_positive_fraction']], rtol=1e-14, atol=1e-10)
            model = joblib.load(stem.with_suffix('.joblib')); raw = x.loc[tm].to_numpy(float)
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', RuntimeWarning)
                median = np.nanmedian(raw, axis=0)
            median = np.nan_to_num(median)
            np.testing.assert_array_equal(median, model[0].statistics_)
            missing = np.isnan(raw).any(axis=0)
            np.testing.assert_array_equal(np.flatnonzero(missing), model[0].indicator_.features_)
            imputed = np.where(np.isnan(raw), median, raw)
            transformed = np.column_stack([imputed, np.isnan(raw[:, missing]).astype(float)])
            np.testing.assert_allclose(transformed.mean(axis=0), model[1].mean_, rtol=1e-12, atol=1e-12)
            np.testing.assert_allclose(transformed.var(axis=0), model[1].var_, rtol=1e-11, atol=1e-11)
            q = pd.read_parquet(stem.with_suffix('.parquet'))
            pd.testing.assert_frame_equal(q[KEYS].reset_index(drop=True), data.loc[qm, KEYS].reset_index(drop=True))
            np.testing.assert_array_equal(q.available, valid[qm])
            with threadpool_limits(limits=2):
                np.testing.assert_array_equal(model.predict_proba(x.loc[qm])[:, 1], q.score)
            cache[name][key] = q; replays += 1
            write(out / 'progress.json', dict(models_replayed=replays))
    prior = ROOT / plan['prior_study']; cached = 0
    for spec in read(prior / 'plan.json')['settings']['candidates']:
        name = spec['name']; cache[name] = {}
        for key in contexts:
            stem = prior / name / '__'.join(key); record = read(stem.with_suffix('.json'))
            assert sha(stem.with_suffix('.parquet')) == record['prediction_sha256']
            q = pd.read_parquet(stem.with_suffix('.parquet'))
            pd.testing.assert_frame_equal(q[KEYS].reset_index(drop=True), data.loc[data.group.isin(key), KEYS].reset_index(drop=True))
            cache[name][key] = q; cached += 1
    # 모든 후보의 내부 지표를 별도 날짜 집계로 다시 산출한다. 선택 후보만 대조하지 않는다.
    decisions = read(study / 'decisions.json'); inner_checks = 0; selections = 0; bounded = 0
    for outer in groups:
        q = pd.concat([cache[next(iter(cache))][tuple(sorted([outer, h]))].loc[lambda p: p.group.eq(h)]
                       for h in groups if h != outer], ignore_index=True)
        scores = {n: np.concatenate([c[tuple(sorted([outer, h]))].loc[lambda p: p.group.eq(h), 'score']
                                    for h in groups if h != outer]) for n, c in cache.items()}
        table = pd.read_csv(study / (outer + '_selection.csv'), float_precision='round_trip').set_index('candidate')
        for name, spec in specs.items():
            pred = manual_prediction(q, spec, scores); measured = []
            for year in ['all', 2024, 2025]:
                mask = np.ones(len(q), bool) if year == 'all' else q.winter.eq(year).to_numpy()
                metric = independent_metrics(q.loc[mask], pred[mask]); measured.append(metric['f1_fixed_population'])
                if year == 'all':
                    assert metric['fp'] == table.loc[name, 'fp'] and metric['tp'] == table.loc[name, 'tp'] and metric['fn'] == table.loc[name, 'fn']
                inner_checks += 1
            np.testing.assert_allclose(measured, table.loc[name, ['mean_f1', 'f1_2024', 'f1_2025']].to_numpy(float), rtol=0, atol=1e-12)
            np.testing.assert_allclose(min(measured[1:]), table.loc[name, 'worst_winter_f1'], rtol=0, atol=1e-12)
            retention = []
            for _, idx in q.groupby(['group', 'winter']).indices.items():
                base_positive = q.iloc[idx].ice.eq(1).to_numpy() & q.iloc[idx].asos_air_temp.le(0).to_numpy() & q.iloc[idx].available.to_numpy()
                if base_positive.any():
                    retention.append(np.count_nonzero((pred[idx] == 1) & base_positive) / base_positive.sum())
            np.testing.assert_allclose(min(retention, default=1.), table.loc[name, 'minimum_group_winter_retention'], atol=1e-12, rtol=0)
        for track, choice in decisions[outer].items():
            rows = table.reset_index().to_dict('records'); metric = track
            if track == 'retention_guard':
                base = table.loc['asos_zero']
                rows = [r for r in rows if r['minimum_group_winter_retention'] >= .98 and
                        r['f1_2024'] >= base.f1_2024 and r['f1_2025'] >= base.f1_2025]
                metric = 'mean_f1'
            winner = min(rows, key=lambda r: (-r[metric], r['fp'], r['complexity'], r['candidate']))
            assert winner['candidate'] == choice['candidate']; selections += 1
            np.testing.assert_array_equal(f.loc[f.group.eq(outer), 'selected_' + track], f.loc[f.group.eq(outer), winner['candidate']])
        outer_q = f.loc[f.group.eq(outer)]
        outer_scores = {n: c[(outer,)].sort_values(['station', 'time']).score.to_numpy() for n, c in cache.items()}
        for name, spec in specs.items():
            np.testing.assert_array_equal(manual_prediction(outer_q, spec, outer_scores), outer_q[name]); bounded += 1
        print('AUDITED', outer, inner_checks, flush=True)
    metrics = 0
    for name, report in summary['reports'].items():
        for year in ['all', 2024, 2025]:
            part = f if year == 'all' else f.loc[f.winter.eq(year)]
            actual = independent_metrics(part, part[name])
            for metric in ['f1_fixed_population', 'precision_available_station_mean', 'recall_available_station_mean']:
                expected = report[str(year)][metric]
                if expected is None:
                    assert actual[metric] is None
                else:
                    np.testing.assert_allclose(actual[metric], expected, atol=1e-12, rtol=0)
            metrics += 1
        assert independent_events(f, f[name], f.current) == report['events']
    regions = pd.read_csv(study / 'regions.csv', float_precision='round_trip')
    base_regions = regions.loc[regions.method.eq('asos_zero')].set_index('group').f1_fixed_population
    secondary = {}
    for name, report in summary['reports'].items():
        r = regions.loc[regions.method.eq(name)].set_index('group').f1_fixed_population
        secondary[name] = dict(beats_asos=report['all']['f1_fixed_population'] > summary['reports']['asos_zero']['all']['f1_fixed_population'],
            both_winters_noninferior=all(report[str(y)]['f1_fixed_population'] >= summary['reports']['asos_zero'][str(y)]['f1_fixed_population'] for y in [2024, 2025]),
            noninferior_regions=int(r.ge(base_regions).sum()))
    write(out / 'asos_secondary_checks.json', secondary)
    assert preservation() == frozen
    receipt = dict(status='anchored_icing_independently_verified', models_replayed=replays, preprocessing_checks=replays,
        training_weight_checks=replays, previously_audited_score_files=cached, inner_metric_checks=inner_checks,
        nested_selection_checks=selections, outer_policy_checks=bounded, metric_checks=metrics, event_checks=len(summary['reports']),
        source_summary_sha256=sha(study / 'summary.json'), predictions_sha256=sha(study / 'predictions.parquet'),
        audit_code_sha256=sha(Path(__file__)), secondary_checks_sha256=sha(out / 'asos_secondary_checks.json'),
        protected_labels_read=False, production_changed=False, frozen_counts=list(frozen))
    write(out / 'receipt.json', receipt); print(receipt, flush=True)


if __name__ == '__main__':
    main()
