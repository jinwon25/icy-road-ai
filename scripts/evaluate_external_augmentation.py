"""완료된 외부 첫 겨울만으로 그룹 제외·중첩 후보 선택을 수행한다."""
import argparse
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file
from src.external_augmentation import (FixedDonorStateContext, matrix_with_context, select_group_candidate,
                                       fit_cache_key, CompletedFitCache)
from src.frozen_assessment import verify_freeze
from src.ice_daily_selection import choose_daily_threshold
from src.validation import assert_training_stations, binary_metrics, daily_scores, macro_scores
from scripts.baseline_ice_logistic import FEATURES
from scripts.evaluate_physical_ice import threshold_grid


def json_write(path, value):
    def scalar(item):
        if isinstance(item, np.generic):
            return item.item()
        raise TypeError(f'Unsupported JSON value type: {type(item).__name__}')
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=scalar, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def metrics(frame, scores, threshold):
    predictions = (np.asarray(scores) >= threshold).astype(int)
    valid = frame.ice.notna().to_numpy()
    gold = frame.loc[valid, 'ice'].astype(int)
    slot = binary_metrics(gold, predictions[valid])
    records = [(str(r.station), r.time, int(r.ice) if pd.notna(r.ice) else None, int(p))
               for r, p in zip(frame.itertuples(), predictions, strict=True)]
    days = daily_scores(records, minimum_coverage=1.)
    table = pd.DataFrame(days)
    actual = table.loc[table.accepted & (table.tp + table.fn).gt(0)] if len(table) else table
    return {'slot_micro': slot, 'average_precision': float(average_precision_score(gold, np.asarray(scores)[valid])) if len(gold) and gold.sum() > 0 else None,
            'daily_station_macro': macro_scores(days),
            'fixed_ice_day_f1': float(actual.groupby('station').f1.mean().mean()) if len(actual) else None,
            'false_alarm_nonice_days': int((table.accepted & (table.tp + table.fn).eq(0) & table.fp.gt(0)).sum()) if len(table) else 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true', help='수집 완료 조건·구성만 확인하고 학습하지 않는다.')
    args = parser.parse_args()
    private = ROOT / 'outputs/private'
    config_path = ROOT / 'config/external_augmentation_experiment.json'
    config = json.loads(config_path.read_text(encoding='utf-8'))
    plan_path = ROOT / config['plan']
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    groups = {name: set(stations) for name, stations in plan['station_groups'].items()}
    all_external = set().union(*groups.values())
    assert len(groups) == 4 and sum(map(len, groups.values())) == len(all_external) == 9
    assert_training_stations(all_external)
    data_path = private / 'external_development_features_v1/features.parquet'
    external_info_path = data_path.parent / 'summary.json'
    acquisition_path = private / 'external/kma_rwis_development_v1/summary.json'
    acquisition = json.loads(acquisition_path.read_text(encoding='utf-8')) if acquisition_path.exists() else {}
    ready = acquisition.get('status') == 'development_download_complete' and data_path.exists() and external_info_path.exists()
    if args.prepare_only:
        print(json.dumps({'status': 'ready_for_nested_development' if ready else 'awaiting_complete_development_data',
                          'downloaded_windows_audited': acquisition.get('downloaded_windows_audited', 0),
                          'expected_windows_full_winter': acquisition.get('expected_windows_full_winter', 2160),
                          'groups': {k: sorted(v) for k, v in groups.items()}, 'training_started': False,
                          'reserved_validation_opened': False}, ensure_ascii=False), flush=True)
        return
    if not ready:
        raise ValueError('Complete first-winter acquisition, audit and training-permitted features required')
    external_info = json.loads(external_info_path.read_text(encoding='utf-8'))
    assert external_info['model_training_permitted'] is True and external_info['reserved_validation_opened'] is False
    assert acquisition['reserved_validation_opened'] is False
    assert sha256_file(data_path) == external_info['features_sha256']
    base_path = private / 'physical_features/features.parquet'
    competition = pd.read_parquet(base_path)
    cutoff = pd.Timestamp(plan['development_end_kst']) + pd.Timedelta(days=1)
    competition = competition.loc[competition.time.ge(plan['development_start_kst']) & competition.time.lt(cutoff)].copy()
    competition['spatial_group'] = 'competition_' + competition.station
    external = pd.read_parquet(data_path)
    assert set(external.station) == all_external
    assert external.time.ge(plan['development_start_kst']).all() and external.time.lt(cutoff).all()
    for group, stations in groups.items():
        assert external.loc[external.station.isin(stations), 'spatial_group'].eq(group).all()
    physical = json.loads((private / 'physical_features/summary.json').read_text(encoding='utf-8'))
    base_features = FEATURES + physical['additional_features']
    columns = ['station', 'route', 'time', 'ice', 'state_raw', 'spatial_group', *base_features]
    data = pd.concat([competition[columns], external[columns]], ignore_index=True)
    assert_training_stations(data.station.unique())
    assert not data.duplicated(['station', 'time']).any()
    donor_ids = sorted(competition.station.unique())
    assert len(donor_ids) == 14 and not set(donor_ids) & all_external
    metadata_path = private / 'sensor_availability/metadata.csv'
    meta = pd.read_csv(metadata_path, dtype={'station': str})
    meta = meta.loc[meta.kind.eq('RWIS'), ['station', 'route', 'lat', 'lon']]
    catalog_path = private / 'external/kma_rwis_reference/station_catalog.csv'
    catalog = pd.read_csv(catalog_path, dtype={'station': str})
    extra_meta = catalog.loc[catalog.station.isin(all_external), ['station', 'route', 'lat', 'lon']].copy()
    extra_meta['route'] = extra_meta.route.replace({'통영-대전중부': '통영-대전중부선'})
    meta = pd.concat([meta, extra_meta], ignore_index=True)
    thermal_path = private / 'point_sources/rwis.parquet'
    thermal = pd.read_parquet(thermal_path)
    thermal = thermal.loc[thermal.time.lt(cutoff)]
    state_source = competition[['station', 'time', 'state_raw']]
    context = FixedDonorStateContext(data, thermal, meta, state_source, donor_ids, cutoff)
    calibration_folds = [set(donor_ids[i::config['calibration_folds']]) for i in range(config['calibration_folds'])]
    assert set().union(*calibration_folds) == set(donor_ids)
    out = private / 'external_augmentation_nested_v1'
    out.mkdir(exist_ok=True)
    signature = {'config': sha256_file(config_path), 'plan': sha256_file(plan_path), 'external_features': sha256_file(data_path),
                 'external_feature_info': sha256_file(external_info_path), 'competition_features': sha256_file(base_path),
                 'thermal': sha256_file(thermal_path), 'metadata': sha256_file(metadata_path), 'catalog': sha256_file(catalog_path),
                 'runner': sha256_file(Path(__file__)), 'augmentation': sha256_file(ROOT / 'src/external_augmentation.py'),
                 'physical_context': sha256_file(ROOT / 'src/physical_features.py'), 'state_context': sha256_file(ROOT / 'src/surface_state_context_v2.py')}
    pinned = out / 'input_signature.json'
    if pinned.exists() and json.loads(pinned.read_text(encoding='utf-8')) != signature:
        raise ValueError('Nested experiment input changed; preserve outputs')
    json_write(pinned, signature)
    comp = data.loc[data.station.isin(donor_ids) & data.ice.notna()].copy()
    valid_training = data.loc[data.ice.notna()].copy()
    fit_cache = CompletedFitCache()

    def fit_calibrated(train, forbidden, candidate, folder):
        assert not set(train.station) & set(forbidden)
        use_state = candidate == 'augmented_surface_state_v2'
        if candidate not in ['baseline', *config['candidate_names']]:
            raise ValueError('Unknown candidate')
        folder.mkdir(parents=True, exist_ok=True)
        receipt = folder / 'fit_manifest.json'
        cache_key = fit_cache_key(train, forbidden, candidate, signature)
        if receipt.exists():
            info = json.loads(receipt.read_text(encoding='utf-8'))
            assert info['fit_cache_key'] == cache_key
            assert info['candidate'] == candidate and info['training_stations'] == sorted(train.station.unique())
            assert info['forbidden_stations'] == sorted(forbidden)
            for name, checksum in info['files'].items():
                assert sha256_file(folder / name) == checksum
            fit_cache.register(cache_key, folder)
            return joblib.load(folder / 'model.joblib'), info
        if fit_cache.materialize(cache_key, folder):
            info = json.loads(receipt.read_text(encoding='utf-8'))
            print(folder.relative_to(out).as_posix(), 'identical completed fit reused; artifacts verified', flush=True)
            return joblib.load(folder / 'model.joblib'), info
        calibration = train.loc[train.station.isin(donor_ids)].copy()
        assert len(calibration) == len(comp)
        scores = np.full(len(calibration), np.nan)
        references = []
        for i, held in enumerate(calibration_folds):
            fit = train.loc[~train.station.isin(held)]
            mask = calibration.station.isin(held).to_numpy()
            check = calibration.loc[mask]
            excluded = set(forbidden) | held
            tx, r1 = matrix_with_context(fit, context, excluded, base_features, state=use_state)
            vx, r2 = matrix_with_context(check, context, excluded, base_features, state=use_state)
            model = HistGradientBoostingClassifier(**config['model'], class_weight={0: 1., 1: config['positive_weight']})
            model.fit(tx, fit.ice.astype(int))
            scores[mask] = model.predict_proba(vx)[:, 1]
            joblib.dump(model, folder / f'calibration_model_{i}.joblib')
            references.extend([{**r, 'role': role, 'calibration_fold': i} for role, rs in [('fit', r1), ('check', r2)] for r in rs])
            print(folder.relative_to(out).as_posix(), f'calibration {i+1}/3', flush=True)
        assert np.isfinite(scores).all()
        threshold, inner_f1, trace = choose_daily_threshold(calibration, scores, threshold_grid(scores))
        oof = calibration[['station', 'time', 'ice']].copy();oof['score'] = scores
        oof.to_parquet(folder / 'calibration_oof.parquet', index=False, compression='zstd')
        trace.to_csv(folder / 'threshold_trace.csv', index=False)
        tx, refs = matrix_with_context(train, context, forbidden, base_features, state=use_state)
        references.extend([{**r, 'role': 'full_fit', 'calibration_fold': None} for r in refs])
        model = HistGradientBoostingClassifier(**config['model'], class_weight={0: 1., 1: config['positive_weight']})
        model.fit(tx, train.ice.astype(int));joblib.dump(model, folder / 'model.joblib')
        json_write(folder / 'references.json', references)
        info = {'candidate': candidate, 'training_stations': sorted(train.station.unique()), 'training_rows': len(train),
                'training_ice_rows': int(train.ice.eq(1).sum()), 'forbidden_stations': sorted(forbidden),
                'calibration_stations': sorted(calibration.station.unique()), 'calibration_rows': len(calibration),
                'threshold': threshold, 'inner_daily_f1': inner_f1, 'features': tx.columns.tolist(),
                'reserved_validation_opened': False}
        info['files'] = {p.name: sha256_file(p) for p in folder.iterdir() if p.is_file() and p.suffix != '.tmp'}
        info['fit_cache_key'] = cache_key
        json_write(receipt, info)
        fit_cache.register(cache_key, folder)
        return model, info

    nested_rows, choices, outer_frames = [], {}, []
    with threadpool_limits(limits=config['max_compute_threads']):
        baseline, baseline_info = fit_calibrated(comp, all_external, 'baseline', out / 'baseline')
        for outer_group, outer_stations in groups.items():
            for check_group, check_stations in groups.items():
                if check_group == outer_group:
                    continue
                excluded = outer_stations | check_stations
                train = valid_training.loc[~valid_training.station.isin(excluded)]
                check = data.loc[data.station.isin(check_stations)].copy()
                bx, refs = matrix_with_context(check, context, all_external, base_features)
                base_score = baseline.predict_proba(bx)[:, 1]
                base_metrics = metrics(check, base_score, baseline_info['threshold'])
                nested_rows.append({'outer_held_group': outer_group, 'validation_group': check_group, 'candidate': 'baseline',
                                    'training_excluded_groups': list(groups), **base_metrics['slot_micro']})
                for candidate in config['candidate_names']:
                    folder = out / outer_group / 'selection' / check_group / candidate
                    model, info = fit_calibrated(train, excluded, candidate, folder)
                    vx, refs = matrix_with_context(check, context, excluded, base_features, state=candidate == 'augmented_surface_state_v2')
                    score = model.predict_proba(vx)[:, 1]
                    assert np.isfinite(score).all()
                    result = check[['station', 'time', 'ice']].copy();result['score'] = score;result['prediction'] = (score >= info['threshold']).astype(int)
                    result['baseline_score'] = base_score;result['baseline_prediction'] = (base_score >= baseline_info['threshold']).astype(int)
                    result.to_parquet(folder / 'selection_predictions.parquet', index=False, compression='zstd')
                    report = metrics(check, score, info['threshold'])
                    json_write(folder / 'selection_metrics.json', report);json_write(folder / 'selection_references.json', refs)
                    nested_rows.append({'outer_held_group': outer_group, 'validation_group': check_group, 'candidate': candidate,
                                        'training_excluded_groups': [outer_group, check_group], **report['slot_micro']})
            decision = select_group_candidate(pd.DataFrame(nested_rows), outer_group, config['candidate_names'])
            choices[outer_group] = decision
            candidate = decision['selected_candidate']
            if candidate == 'baseline':
                model, info = baseline, baseline_info;model_relative = 'baseline/model.joblib'
            else:
                train = valid_training.loc[~valid_training.station.isin(outer_stations)]
                folder = out / outer_group / 'selected_model'
                model, info = fit_calibrated(train, outer_stations, candidate, folder)
                model_relative = (folder / 'model.joblib').relative_to(out).as_posix()
            decision.update({'model_path': model_relative, 'model_sha256': sha256_file(out / model_relative),
                             'threshold': info['threshold'], 'features': info['features'], 'training_stations': info['training_stations']})
            json_write(out / outer_group / 'decision.json', decision)
            # This first-winter outer diagnostic is computed only after that group's choice.
            check = data.loc[data.station.isin(outer_stations)].copy()
            vx, refs = matrix_with_context(check, context, outer_stations, base_features, state=candidate == 'augmented_surface_state_v2')
            score = model.predict_proba(vx)[:, 1]
            bx, base_refs = matrix_with_context(check, context, all_external, base_features)
            base_score = baseline.predict_proba(bx)[:, 1]
            result = check[['station', 'time', 'ice']].copy();result['group'] = outer_group;result['selected_candidate'] = candidate
            result['score'] = score;result['prediction'] = (score >= info['threshold']).astype(int)
            result['baseline_score'] = base_score;result['baseline_prediction'] = (base_score >= baseline_info['threshold']).astype(int)
            result['threshold'] = info['threshold'];result['baseline_threshold'] = baseline_info['threshold']
            result.to_parquet(out / outer_group / 'outer_development_predictions.parquet', index=False, compression='zstd')
            outer_frames.append(result)
            print(outer_group, candidate, 'development selection complete; reserved winter unopened', flush=True)
    combined = pd.concat(outer_frames, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    assert not combined.duplicated(['station', 'time']).any()
    combined.to_parquet(out / 'outer_development_predictions.parquet', index=False, compression='zstd')
    pd.DataFrame(nested_rows).to_json(out / 'nested_selection_metrics.json', orient='records', force_ascii=False, indent=2)
    json_write(out / 'decisions.json', choices)
    good = combined.loc[combined.ice.notna()]
    summary = {'status': 'nested_first_winter_development_complete_reserved_winter_unopened', 'rows': len(combined),
               'slot_micro': {'baseline': binary_metrics(good.ice.astype(int), good.baseline_prediction), 'selected': binary_metrics(good.ice.astype(int), good.prediction)},
               'group_choices': choices, 'signature': signature, 'reserved_validation_opened': False,
               'protected_outcomes_used': False, 'frozen_files_unchanged': len(verify_freeze(ROOT)['files']),
               'scope': 'Nested first-winter development selection. Requires saved next-winter predictions and a separate reserved-winter assessment.'}
    json_write(out / 'summary.json', summary)
    print(json.dumps({k: summary[k] for k in ['status', 'rows', 'slot_micro', 'reserved_validation_opened', 'frozen_files_unchanged']}, ensure_ascii=False, default=lambda value: value.item() if isinstance(value, np.generic) else str(value)), flush=True)


if __name__ == '__main__':
    main()
