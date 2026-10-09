"""Prespecified HGB benchmark; thresholds from inner station OOF only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.baseline_ice_logistic import FEATURES, add_time_features, choose_threshold
from src.data_source import sha256_file
from src.ice_daily_selection import choose_daily_threshold
from src.validation import assert_training_stations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke', action='store_true', help='First two outer folds; all rows retained')
    args = parser.parse_args()
    private = ROOT / 'outputs/private'
    config_path = ROOT / 'config/ice_nonlinear_experiment.json'
    config = json.loads(config_path.read_text(encoding='utf-8'))
    feature_path = private / 'ice_fallback_features/features.parquet'
    data = add_time_features(pd.read_parquet(feature_path))
    data['station'] = data.station.astype(str)
    assert_training_stations(data.station.unique())
    if data.duplicated(['station', 'time']).any():
        raise ValueError('Duplicate target station/time')
    splits_path = private / 'validation/splits.json'
    folds = json.loads(splits_path.read_text(encoding='utf-8'))['outer_folds']
    if args.smoke:
        folds = folds[:2]
    out = private / ('smoke_ice_nonlinear' if args.smoke else 'ice_nonlinear')
    out.mkdir(parents=True, exist_ok=True)
    predictions, thresholds, traces, manifests = [], [], [], []
    with threadpool_limits(limits=config['max_compute_threads']):
        for outer in folds:
            held = str(outer['validation_station'])
            train = data.loc[data.station.ne(held) & data.ice.notna()].reset_index(drop=True)
            valid = data.loc[data.station.eq(held)].copy()
            if set(train.station) != set(outer['training_stations']) or valid.empty:
                raise ValueError('Frozen outer split mismatch')
            oof = np.full(len(train), np.nan)
            visits = np.zeros(len(train), dtype=int)
            for i, inner in enumerate(outer['inner_folds']):
                mask = train.station.isin(inner['stations']).to_numpy()
                fit, check = train.loc[~mask], train.loc[mask]
                if held in set(fit.station) | set(check.station) or set(fit.station) & set(check.station):
                    raise ValueError('Station leakage')
                if fit.ice.nunique() != 2 or check.empty:
                    raise ValueError('Invalid inner classes or station split')
                model = HistGradientBoostingClassifier(**config['model'])
                model.fit(fit[FEATURES], fit.ice.astype(int))
                oof[mask] = model.predict_proba(check[FEATURES])[:, 1]
                visits[mask] += 1
                manifests.append({'outer_held': held, 'inner_index': i,
                                  'fit_stations': sorted(fit.station.unique()),
                                  'validation_stations': sorted(check.station.unique())})
                print(f'{held}: inner fold {i + 1}/3 complete', flush=True)
            if not np.isfinite(oof).all() or not (visits == 1).all():
                raise ValueError('Inner OOF coverage invalid')
            slot_t, slot_f1 = choose_threshold(train.ice.to_numpy(dtype=int), oof)
            daily_t, daily_f1, trace = choose_daily_threshold(train, oof)
            trace['outer_held'] = held
            traces.append(trace)
            model = HistGradientBoostingClassifier(**config['model'])
            model.fit(train[FEATURES], train.ice.astype(int))
            score = model.predict_proba(valid[FEATURES])[:, 1]
            if not np.isfinite(score).all():
                raise ValueError('Invalid outer scores')
            result = valid[['station', 'route', 'time', 'ice', 'state_raw']].copy()
            result['model_score'] = score
            result['pred_slot'] = (score >= slot_t).astype(int)
            result['pred_daily'] = (score >= daily_t).astype(int)
            predictions.append(result)
            thresholds.append({'station': held, 'slot_threshold': slot_t, 'daily_threshold': daily_t,
                               'inner_slot_f1': slot_f1, 'inner_station_daily_f1': daily_f1,
                               'train_rows': len(train), 'train_positives': int(train.ice.sum())})
            print(f'{held}: outer complete, slot threshold={slot_t:.6f}, daily threshold={daily_t:.2f}', flush=True)
    prediction = pd.concat(predictions, ignore_index=True)
    if prediction.duplicated(['station', 'time']).any():
        raise ValueError('Duplicate outer predictions')
    prediction.to_parquet(out / 'predictions.parquet', index=False, compression='zstd')
    pd.DataFrame(thresholds).to_csv(out / 'thresholds.csv', index=False, encoding='utf-8-sig')
    pd.concat(traces, ignore_index=True).to_csv(out / 'inner_daily_threshold_trace.csv', index=False, encoding='utf-8-sig')
    (out / 'fold_manifest.json').write_text(json.dumps(manifests, indent=2), encoding='utf-8')
    source_config = json.loads((ROOT / 'config/data_source.json').read_text(encoding='utf-8'))
    summary = {'status': 'development_only_prespecified_nonlinear', 'smoke': args.smoke,
               'data_release': source_config['release'], 'archive_sha256': source_config['sha256'],
               'stations': prediction.station.nunique(), 'target_rows': len(prediction),
               'valid_labels': int(prediction.ice.notna().sum()), 'ice_slots': int(prediction.ice.sum()),
               'features': FEATURES, 'config': config,
               'score_semantics': 'class-weighted score; not calibrated Ice probability',
               'feature_sha256': sha256_file(feature_path), 'split_sha256': sha256_file(splits_path),
               'experiment_config_sha256': sha256_file(config_path)}
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: summary[key] for key in ('status', 'smoke', 'stations', 'target_rows', 'ice_slots')}), flush=True)


if __name__ == '__main__':
    main()
