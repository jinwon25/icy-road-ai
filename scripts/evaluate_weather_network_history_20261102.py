"""한 후보·고정12적합으로 풍속 공간 이력의 추가 정보만 비교한다."""
import gc
from pathlib import Path
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_objective_icing import read, write, now, verify_preserved
from scripts.evaluate_weather_history_spatial_20261101 import report
from scripts.evaluate_weather_space_time import sensitivity
from src.weather_network_history import network_history_features
from src.road_weather_transfer import features, baselines, balanced_weights, constrain
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network


def main():
    config = ROOT/'config/weather_network_history_20261102.json'
    plan = read(config); out = ROOT/plan['output']; reference = ROOT/plan['reference']
    assert sha(ROOT/plan['input']) == plan['input_sha256']
    summary = read(reference/'summary.json'); audit = read(reference/'independent_verification.json')
    assert audit['status'] == 'passed' and audit['summary_sha256'] == sha(reference/'summary.json')
    cache = reference/'network_features.parquet'
    assert sha(cache) == summary['files']['network_features.parquet']
    paths = [config, Path(__file__), ROOT/'src/weather_network_history.py',
             ROOT/'src/weather_history_stable.py', ROOT/'src/weather_temporal.py',
             ROOT/'src/road_weather_transfer.py', ROOT/plan['input'], cache,
             reference/'summary.json', reference/'independent_verification.json']
    signatures = {p.relative_to(ROOT).as_posix(): sha(p) for p in paths}
    frozen = verify_preserved()
    if out.exists():
        assert read(out/'plan.json')['signatures'] == signatures
        if (out/'summary.json').exists():
            raise FileExistsError('Preserve completed network history experiment')
    else:
        out.mkdir(parents=True)
        write(out/'plan.json', dict(at_utc=now(), settings=plan, signatures=signatures, preservation=frozen))
    f = pd.read_parquet(ROOT/plan['input']).sort_values(['station', 'time']).reset_index(drop=True)
    assert not set(f.station) & set(plan['blocked_stations'])
    assert not {'road_temp', 'ice', 'state_raw'} & set(f)
    network = pd.read_parquet(cache)
    with deny_network() as attempts:
        x = network_history_features(f, network)
    assert not attempts and x.shape == (len(f), 147)
    x.to_parquet(out/'features.parquet', index=False, compression='zstd')
    current_x = pd.concat([features(f), network], axis=1)
    asos, nearest = baselines(f, plan['target'])
    valid = np.isfinite(asos) & np.isfinite(nearest) & np.isfinite(f[plan['target']])
    groups = sorted(set(f.group)-{'competition'}); assert len(groups) == 4
    fits = []; reports = {}
    for mode in ['joint', 'spatial']:
        folder = out/mode; folder.mkdir(exist_ok=True); parts = []
        for year in ([2024, 2025] if mode == 'joint' else [None]):
            for held in groups:
                train = valid & f.group.ne(held); query = valid & f.group.eq(held)
                if year is not None:
                    train &= f.winter.ne(year); query &= f.winter.eq(year)
                assert not set(f.loc[train, 'station']) & set(f.loc[query, 'station'])
                if year is not None: assert not set(f.loc[train, 'winter']) & set(f.loc[query, 'winter'])
                stem = held+('_'+str(year) if year is not None else '')
                ref = reference/plan['target']/mode/(stem+'.joblib')
                meta = read(ref.with_suffix('.json')); assert sha(ref) == meta['model_sha256']
                with deny_network() as attempts, threadpool_limits(limits=2):
                    current = constrain(joblib.load(ref).predict(current_x.loc[query])+nearest[query], plan['target'])
                assert not attempts
                np.testing.assert_array_equal(current, np.load(ref.with_suffix('.npy'), allow_pickle=False))
                model_path = folder/(stem+'.joblib'); meta_path = model_path.with_suffix('.json')
                pred_path = model_path.with_suffix('.npy')
                if meta_path.exists():
                    record = read(meta_path)
                    assert sha(model_path) == record['model_sha256'] and sha(pred_path) == record['prediction_sha256']
                    predicted = np.load(pred_path, allow_pickle=False)
                else:
                    if model_path.exists() or pred_path.exists(): raise FileExistsError('Unrecorded fit')
                    started = time.perf_counter(); model = HistGradientBoostingRegressor(**plan['model'])
                    with deny_network() as attempts, threadpool_limits(limits=2):
                        model.fit(x.loc[train], f.loc[train, plan['target']].to_numpy()-nearest[train],
                                  sample_weight=balanced_weights(f.loc[train]))
                        predicted = constrain(model.predict(x.loc[query])+nearest[query], plan['target'])
                    assert not attempts and np.isfinite(predicted).all()
                    joblib.dump(model, model_path, compress=3); np.save(pred_path, predicted, allow_pickle=False)
                    record = dict(held=held, mode=mode, query_winter=year, training_rows=int(train.sum()),
                        query_rows=int(query.sum()), training_stations=sorted(f.loc[train, 'station'].unique()),
                        query_stations=sorted(f.loc[query, 'station'].unique()),
                        training_winters=sorted(int(v) for v in f.loc[train, 'winter'].unique()),
                        features=list(x), model_sha256=sha(model_path), prediction_sha256=sha(pred_path),
                        reference_model=ref.relative_to(ROOT).as_posix(), reference_model_sha256=sha(ref),
                        seconds=time.perf_counter()-started, network_attempts=0)
                    write(meta_path, record); del model; gc.collect()
                fits.append(record)
                p = f.loc[query, ['station', 'time', 'group', 'winter']].copy()
                p['observed'] = f.loc[query, plan['target']]
                p['cold_input'] = np.abs(f.loc[query, 'asos_air_temp']) <= 3
                p['current'] = current; p['network_history_residual'] = predicted; parts.append(p)
                print('FIT', len(fits), '/12', mode, held, year, round(record['seconds'], 1), flush=True)
        p = pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
        assert not p.duplicated(['station', 'time']).any()
        p.to_parquet(folder/'predictions.parquet', index=False, compression='zstd')
        measures = {c: report(p, c) for c in ['current', plan['candidate']]}
        boot = sensitivity(p, plan['candidate'], 'current', plan['bootstrap'])
        b = measures['current']; c = measures[plan['candidate']]; g = plan['gates']
        gates = dict(pooled=c['pooled']['mae'] <= b['pooled']['mae']*(1-g['minimum_mae_reduction']),
            both_winters=all(c['winters'][y]['mae'] <= v['mae']*g['maximum_winter_mae_ratio'] for y, v in b['winters'].items()),
            every_region=all(c['regions'][r]['mae'] <= v['mae']*g['maximum_region_mae_ratio'] for r, v in b['regions'].items()),
            cold=c['cold']['mae'] <= b['cold']['mae']*g['maximum_cold_mae_ratio'],
            date_sensitivity=boot['quantiles'][2] < 0)
        reports[mode] = dict(metrics=measures, bootstrap=boot, gates=gates, primary_success=all(gates.values()))
        print('REPORT', mode, b['pooled']['mae'], c['pooled']['mae'], gates, flush=True)
    assert len(fits) == 12 and verify_preserved() == frozen
    write(out/'summary.json', dict(status='network_history_complete', at_utc=now(), reports=reports, fits=fits,
        eligible_for_adoption=all(r['primary_success'] for r in reports.values()), production_model_changed=False,
        new_independent_assessment=False, protected_outcomes_read=False, preservation=frozen,
        files={p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*') if p.is_file()}))
    print('COMPLETE', flush=True)


if __name__ == '__main__':
    main()
