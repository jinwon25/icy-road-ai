"""사전 고정 48적합: 지역과 겨울 동시 제외, 현 입력 대 과거 기상 이력."""
import argparse
from datetime import datetime, timezone
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
from src.weather_temporal import temporal_features, split_masks
from src.road_weather_transfer import baselines, constrain, balanced_weights, regression_numbers
from src.data_source import sha256_file as sha
from src.development_resampling import circular_day_indices
from src.offline_runtime import deny_network
from scripts.evaluate_objective_icing import read, write, verify_preserved


def metrics(f, column):
    measure = lambda q: regression_numbers(q.observed, q[column])
    return dict(pooled=measure(f),
        directions={str(k): measure(q) for k, q in f.groupby('winter')},
        regions={k: measure(q) for k, q in f.groupby('group')},
        cold=measure(f.loc[f.cold_input]))


def sensitivity(f, candidate, reference, settings):
    totals = []
    for year, q in f.groupby('winter'):
        q = q.copy(); q['date'] = q.time.dt.normalize()
        q['delta'] = np.abs(q[candidate]-q.observed)-np.abs(q[reference]-q.observed)
        calendar = pd.date_range(f'{year}-11-01', f'{year+1}-02-28', freq='D')
        daily = q.groupby('date').agg(delta=('delta', 'sum'), n=('delta', 'size')).reindex(calendar, fill_value=0)
        indices = circular_day_indices(len(calendar), settings['block_days'], settings['repetitions'], settings['seed']+int(year)-2024)
        totals.append(daily.to_numpy()[indices].sum(axis=1))
    total = sum(totals); delta = total[:, 0]/total[:, 1]
    return dict(quantiles=np.quantile(delta, [.025,.5,.975]).tolist(),
        fraction_improved=float((delta < 0).mean()), repetitions=len(delta),
        interpretation='fixed_development_date_sensitivity_not_new_population_confidence')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'config/weather_temporal_20261101.json')
    args = parser.parse_args(); config = args.config.resolve(); plan = read(config)
    out = ROOT/plan['output']; source = ROOT/plan['input']
    assert sha(source) == plan['input_sha256']
    signatures = {p.relative_to(ROOT).as_posix(): sha(p) for p in [config, Path(__file__),
        ROOT/'src/weather_temporal.py', ROOT/'src/road_weather_transfer.py', source]}
    frozen = verify_preserved()
    if out.exists():
        assert read(out/'plan.json')['signatures'] == signatures
        if (out/'summary.json').exists(): raise FileExistsError('Preserve completed temporal experiment')
    else:
        out.mkdir(parents=True)
        write(out/'plan.json', dict(at_utc=datetime.now(timezone.utc).isoformat(), settings=plan,
            signatures=signatures, preservation=frozen))
    f = pd.read_parquet(source).sort_values(['station','time']).reset_index(drop=True)
    assert not set(f.station) & set(plan['blocked_stations'])
    assert not {'ice','road_temp','state_raw'} & set(f)
    with deny_network() as attempts:
        base, history = temporal_features(f)
    assert not attempts
    xs = {'instant_residual': base, 'history_residual': history}
    for name, x in xs.items():
        path = out/(name+'_features.parquet')
        if path.exists(): pd.testing.assert_frame_equal(pd.read_parquet(path), x, check_exact=True)
        else: x.to_parquet(path, index=False, compression='zstd')
    groups = sorted(set(f.group)-{'competition'}); assert len(groups) == 4
    fits = []; all_reports = {}
    for target in plan['targets']:
        asos, nearest = baselines(f, target)
        valid = np.isfinite(f[target]) & np.isfinite(asos) & np.isfinite(nearest)
        folder = out/target; folder.mkdir(exist_ok=True); parts = []
        for year in [2024,2025]:
            for held in groups:
                train, query = split_masks(f, valid, held, year)
                train_frame = f.loc[train]; query_frame = f.loc[query]
                result = query_frame[['station','time','group','winter']].copy()
                result['observed'] = query_frame[target]
                result['asos'] = asos[query]; result['aws_fallback'] = nearest[query]
                result['cold_input'] = np.abs(f.loc[query,'asos_air_temp']) <= 3
                for candidate, x in xs.items():
                    stem = f'{candidate}_{held}_{year}'
                    model_path = folder/(stem+'.joblib'); meta_path = folder/(stem+'.json')
                    pred_path = folder/(stem+'.npy')
                    if meta_path.exists():
                        record = read(meta_path)
                        assert sha(model_path) == record['model_sha256']
                        assert sha(pred_path) == record['prediction_sha256']
                        predicted = np.load(pred_path, allow_pickle=False)
                    else:
                        if model_path.exists() or pred_path.exists(): raise FileExistsError('Unrecorded partial fit')
                        start = time.perf_counter(); model = HistGradientBoostingRegressor(**plan['model'])
                        with deny_network() as attempts, threadpool_limits(limits=2):
                            model.fit(x.loc[train], f.loc[train,target].to_numpy()-nearest[train],
                                sample_weight=balanced_weights(train_frame))
                            predicted = constrain(model.predict(x.loc[query])+nearest[query], target)
                        assert not attempts and np.isfinite(predicted).all()
                        joblib.dump(model, model_path, compress=3); np.save(pred_path, predicted, allow_pickle=False)
                        record = dict(target=target, candidate=candidate, held=held, query_winter=year,
                            direction=plan['directions'][str(year)], training_rows=int(train.sum()),
                            query_rows=int(query.sum()), training_stations=sorted(train_frame.station.unique()),
                            training_winters=sorted(int(y) for y in train_frame.winter.unique()),
                            query_stations=sorted(query_frame.station.unique()), features=list(x),
                            model_sha256=sha(model_path), prediction_sha256=sha(pred_path),
                            seconds=time.perf_counter()-start, network_attempts=0)
                        write(meta_path, record)
                    fits.append(record); result[candidate] = predicted
                    print('FIT',len(fits),'/48',target,candidate,year,held,round(record['seconds'],1),flush=True)
                parts.append(result)
        p = pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
        assert not p.duplicated(['station','time']).any()
        p.to_parquet(folder/'predictions.parquet',index=False,compression='zstd')
        reports = {c:metrics(p,c) for c in ['asos','aws_fallback',*plan['candidates']]}
        reference = reports[plan['reference_candidate']]; candidate = reports[plan['primary_candidate']]
        bootstrap = sensitivity(p,plan['primary_candidate'],plan['reference_candidate'],plan['bootstrap'])
        gates = dict(pooled=candidate['pooled']['mae'] <= reference['pooled']['mae']*(1-plan['gates']['minimum_mae_reduction_vs_instant']),
            both_directions=all(candidate['directions'][y]['mae'] <= b['mae']*plan['gates']['maximum_direction_mae_ratio'] for y,b in reference['directions'].items()),
            every_region=all(candidate['regions'][g]['mae'] <= b['mae']*plan['gates']['maximum_region_mae_ratio'] for g,b in reference['regions'].items()),
            cold=candidate['cold']['mae'] <= reference['cold']['mae']*plan['gates']['maximum_cold_air_mae_ratio'],
            date_sensitivity=bootstrap['quantiles'][2] < 0)
        all_reports[target] = dict(metrics=reports, history_gates=gates, history_success=all(gates.values()),
            history_vs_instant_bootstrap=bootstrap,
            instant_vs_aws_bootstrap=sensitivity(p,'instant_residual','aws_fallback',plan['bootstrap']))
    assert len(fits) == 48 and verify_preserved() == frozen
    summary = dict(status='weather_temporal_complete', reports=all_reports, fits=fits,
        production_model_changed=False, new_independent_assessment=False, preservation=frozen,
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()})
    write(out/'summary.json',summary)
    print('COMPLETE', {t:r['history_success'] for t,r in all_reports.items()},flush=True)


if __name__ == '__main__': main()
