"""별도 달력 rolling·지표·분할·재학습으로 공간 이력 비교를 검산한다."""
import gc
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_objective_icing import read, write, now, verify_preserved
from scripts.audit_road_weather_transfer import compare, measure
from scripts.audit_weather_temporal import bootstrap
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from src.weather_network_history import network_history_features


def independent_report(p, column):
    return dict(pooled=measure(p, column),
        winters={str(y): measure(q, column) for y, q in p.groupby('winter')},
        regions={g: measure(q, column) for g, q in p.groupby('group')},
        cold=measure(p.loc[p.cold_input], column))


def main():
    plan = read(ROOT/'config/weather_network_history_20261102.json'); out = ROOT/plan['output']
    if (out/'independent_verification.json').exists(): raise FileExistsError('Preserve completed verification')
    frozen = read(out/'plan.json'); summary = read(out/'summary.json')
    for path, digest in frozen['signatures'].items(): assert sha(ROOT/path) == digest, path
    for path, digest in summary['files'].items(): assert sha(out/path) == digest, path
    assert verify_preserved() == frozen['preservation'] == summary['preservation']
    f = pd.read_parquet(ROOT/plan['input']).sort_values(['station', 'time']).reset_index(drop=True)
    assert not set(f.station) & set(plan['blocked_stations']) and not {'road_temp', 'ice', 'state_raw'} & set(f)
    x = pd.read_parquet(out/'features.parquet')
    network = pd.read_parquet(ROOT/plan['reference']/'network_features.parquet')
    stable_path = ROOT/'outputs/private/weather_humidity_stable_20261101_v1/features.parquet'
    stable_summary = read(stable_path.parent/'summary.json')
    assert sha(stable_path) == stable_summary['files']['features.parquet']
    stable = pd.read_parquet(stable_path)
    pd.testing.assert_frame_equal(x.loc[:, list(stable)], stable, check_exact=True)
    pd.testing.assert_frame_equal(x.loc[:, list(network)], network, check_exact=True)
    checked = stable.size+network.size; prefix = 0; max_error = 0.
    for (station, winter), part in f.groupby(['station', 'winter'], sort=True):
        order = part.sort_values('time').index
        times = pd.DatetimeIndex(part.loc[order, 'time'])
        dense = network.loc[order, [c for c in network if c.endswith('_idw')]].copy()
        dense.index = times
        dense = dense.reindex(pd.date_range(times.min(), times.max(), freq='10min'))
        for hours, minimum in [(3, 6), (24, 48)]:
            counts = dense.notna().astype(float).rolling(hours*6, min_periods=1).sum().reindex(times)
            means = dense.rolling(hours*6, min_periods=minimum).mean().reindex(times)
            for column in dense:
                values = dict(mean=means[column].to_numpy(),
                    departure=network.loc[order, column].to_numpy()-means[column].to_numpy(),
                    coverage=counts[column].to_numpy()/(hours*6))
                for kind, value in values.items():
                    actual = x.loc[order, f'{column}_{kind}_{hours}h'].to_numpy()
                    np.testing.assert_allclose(actual, value, rtol=1e-12, atol=1e-10, equal_nan=True)
                    good = np.isfinite(actual) & np.isfinite(value)
                    if good.any(): max_error = max(max_error, float(np.max(np.abs(actual[good]-value[good]))))
                    checked += len(actual)
        if station in ['12207', '23205', '33205']:
            start = pd.Timestamp(f'{winter}-12-15')
            selected = part.time.ge(start-pd.Timedelta(days=1)) & part.time.lt(start+pd.Timedelta(days=1))
            ids = part.loc[selected].index
            short = network_history_features(f.loc[ids].reset_index(drop=True), network.loc[ids].reset_index(drop=True))
            q = f.loc[ids, 'time'].ge(start).to_numpy()
            pd.testing.assert_frame_equal(short.loc[q].reset_index(drop=True), x.loc[ids[q]].reset_index(drop=True), check_exact=True)
            prefix += int(q.sum())*len(x.columns)
    print('FEATURE AUDIT', checked, 'values, prefix exact', prefix, flush=True)
    del stable; gc.collect()
    a = f.asos_wind_speed.where((f.asos_age_minutes > 0) & (f.asos_age_minutes <= 60)).to_numpy()
    b = f.aws_wind_speed.where((f.aws_age_minutes > 0) & (f.aws_age_minutes <= 15)).to_numpy()
    nearest = np.where(np.isfinite(b), b, a)
    valid = np.isfinite(a) & np.isfinite(nearest) & np.isfinite(f.wind_speed)
    predictions = 0; metric_checks = 0; refits = []
    for mode, record in summary['reports'].items():
        p = pd.read_parquet(out/mode/'predictions.parquet')
        expected = f.loc[valid & f.group.ne('competition')]
        pd.testing.assert_frame_equal(p[['station', 'time', 'group', 'winter']],
            expected[['station', 'time', 'group', 'winter']].reset_index(drop=True), check_exact=True)
        np.testing.assert_array_equal(p.observed, expected.wind_speed)
        np.testing.assert_array_equal(p.cold_input, np.abs(expected.asos_air_temp) <= 3)
        for spec in [s for s in summary['fits'] if s['mode'] == mode]:
            held = spec['held']; year = spec['query_winter']
            train = valid & f.group.ne(held); query = valid & f.group.eq(held)
            if year is not None: train &= f.winter.ne(year); query &= f.winter.eq(year)
            assert int(train.sum()) == spec['training_rows'] and int(query.sum()) == spec['query_rows']
            assert not set(f.loc[train, 'station']) & set(f.loc[query, 'station'])
            assert sorted(f.loc[train, 'station'].unique()) == spec['training_stations']
            assert sorted(int(y) for y in f.loc[train, 'winter'].unique()) == spec['training_winters']
            if year is not None: assert set(f.loc[train, 'winter']) == {2025 if year == 2024 else 2024}
            stem = held+('_'+str(year) if year is not None else '')
            path = out/mode/(stem+'.joblib')
            assert sha(path) == spec['model_sha256'] and list(x) == spec['features']
            q = p.loc[p.group.eq(held)]
            if year is not None: q = q.loc[q.winter.eq(year)]
            with deny_network() as attempts, threadpool_limits(limits=2):
                predicted = np.maximum(joblib.load(path).predict(x.loc[query])+nearest[query], 0)
            assert not attempts
            np.testing.assert_array_equal(predicted, q[plan['candidate']])
            np.testing.assert_array_equal(predicted, np.load(path.with_suffix('.npy'), allow_pickle=False))
            reference = ROOT/spec['reference_model']; assert sha(reference) == spec['reference_model_sha256']
            current = x.loc[:, list(joblib.load(reference).feature_names_in_)]
            with deny_network() as attempts, threadpool_limits(limits=2):
                repeated = np.maximum(joblib.load(reference).predict(current.loc[query])+nearest[query], 0)
            assert not attempts; np.testing.assert_array_equal(repeated, q.current)
            predictions += len(q)*2; del current
            if held == 'honam_baekyang' and year in [2024, None]:
                counts = f.loc[train].groupby(['station', 'winter']).station.transform('size').to_numpy(float)
                weights = 1/counts; weights /= weights.mean()
                model = HistGradientBoostingRegressor(**plan['model'])
                with deny_network() as attempts, threadpool_limits(limits=2):
                    model.fit(x.loc[train], f.loc[train, 'wind_speed'].to_numpy()-nearest[train], sample_weight=weights)
                    repeated = np.maximum(model.predict(x.loc[query])+nearest[query], 0)
                assert not attempts; np.testing.assert_array_equal(repeated, predicted)
                refits.append(dict(mode=mode, held=held, query_winter=year, exact=True)); del model
                print('REFIT AUDIT', mode, held, year, 'exact', flush=True)
            gc.collect()
        for column, values in record['metrics'].items(): metric_checks += compare(independent_report(p, column), values)
        boot = bootstrap(p, plan['candidate'], 'current', plan['bootstrap'])
        metric_checks += compare(boot, record['bootstrap'])
        c = independent_report(p, plan['candidate']); b = independent_report(p, 'current'); g = plan['gates']
        gates = dict(pooled=c['pooled']['mae'] <= b['pooled']['mae']*(1-g['minimum_mae_reduction']),
            both_winters=all(c['winters'][y]['mae'] <= v['mae']*g['maximum_winter_mae_ratio'] for y, v in b['winters'].items()),
            every_region=all(c['regions'][r]['mae'] <= v['mae']*g['maximum_region_mae_ratio'] for r, v in b['regions'].items()),
            cold=c['cold']['mae'] <= b['cold']['mae']*g['maximum_cold_mae_ratio'], date_sensitivity=boot['quantiles'][2] < 0)
        assert gates == record['gates'] and all(gates.values()) == record['primary_success']
    assert summary['eligible_for_adoption'] == all(r['primary_success'] for r in summary['reports'].values())
    assert len(refits) == 2 and verify_preserved() == frozen['preservation']
    write(out/'independent_verification.json', dict(status='passed', at_utc=now(), summary_sha256=sha(out/'summary.json'),
        audit_code_sha256=sha(Path(__file__)),
        feature_values_checked=checked, maximum_mathematical_difference=max_error, prefix_exact_values=prefix,
        prediction_values_exact=predictions, metric_checks=metric_checks, representative_refits=refits,
        protected_outcomes_read=False, new_independent_assessment=False, production_model_changed=False))
    print('AUDIT PASSED', checked, 'features', predictions, 'predictions', metric_checks, 'metrics', flush=True)


if __name__ == '__main__':
    main()
