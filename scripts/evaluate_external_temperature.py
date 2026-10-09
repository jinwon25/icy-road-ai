"""외부 첫 겨울의 온도 보강을 평가 그룹과 후보 선택 그룹으로 분리한다."""
import argparse
import json
from pathlib import Path
import sys

import joblib
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.baseline_ice_logistic import FEATURES
from scripts.evaluate_external_augmentation import json_write
from src.data_source import sha256_file
from src.external_temperature import join_training_temperatures, fit_weather_temperature, predict_temperature, paired_temperature_metrics, select_temperature_candidate
from src.frozen_assessment import verify_freeze
from src.validation import assert_training_stations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    private = ROOT / 'outputs/private'
    config_path = ROOT / 'config/external_temperature_experiment.json'
    config = json.loads(config_path.read_text(encoding='utf-8'))
    plan_path = ROOT / config['plan']; plan = json.loads(plan_path.read_text(encoding='utf-8'))
    groups = {name: set(stations) for name, stations in plan['station_groups'].items()}
    external_ids = set().union(*groups.values())
    acquisition_path = private / 'external/kma_rwis_development_v1/summary.json'
    acquisition = json.loads(acquisition_path.read_text(encoding='utf-8')) if acquisition_path.exists() else {}
    feature_path = private / 'external_development_features_v1/features.parquet'
    feature_info_path = feature_path.parent / 'summary.json'
    ready = acquisition.get('status') == 'development_download_complete' and feature_path.exists() and feature_info_path.exists()
    if args.prepare_only:
        print(json.dumps({'status': 'ready_for_nested_temperature' if ready else 'awaiting_complete_development_data',
                          'training_started': False, 'reserved_validation_opened': False}), flush=True)
        return
    if not ready:
        raise ValueError('Complete first-winter collection, audit and training-permitted features required')
    feature_info = json.loads(feature_info_path.read_text(encoding='utf-8'))
    assert feature_info['model_training_permitted'] and not feature_info['reserved_validation_opened']
    assert not acquisition['reserved_validation_opened']
    assert sha256_file(feature_path) == feature_info['features_sha256']
    comp_path = private / 'physical_features/features.parquet'
    competition = pd.read_parquet(comp_path)
    cutoff = pd.Timestamp(plan['development_end_kst']) + pd.Timedelta(days=1)
    competition = competition.loc[competition.time.ge(plan['development_start_kst']) & competition.time.lt(cutoff)].copy()
    thermal_path = private / 'point_sources/rwis.parquet'
    thermal = pd.read_parquet(thermal_path, columns=['station', 'time', 'road_temp'])
    competition = join_training_temperatures(competition, thermal, set(competition.station))
    external = pd.read_parquet(feature_path)
    assert set(external.station) == external_ids and external.time.ge(plan['development_start_kst']).all() and external.time.lt(cutoff).all()
    donor_ids = set(competition.station)
    assert len(donor_ids) == 14 and not donor_ids & external_ids
    for frame in (competition, external):
        assert_training_stations(frame.station.unique())
        assert not frame.duplicated(['station', 'time']).any()
    columns = ['station', 'time', 'road_temp', *FEATURES]
    data = pd.concat([competition[columns], external[columns]], ignore_index=True)
    out = private / 'external_temperature_nested_v1'; out.mkdir(exist_ok=True)
    signature = {'config': sha256_file(config_path), 'plan': sha256_file(plan_path), 'external': sha256_file(feature_path),
                 'external_info': sha256_file(feature_info_path), 'competition': sha256_file(comp_path), 'thermal': sha256_file(thermal_path),
                 'runner': sha256_file(Path(__file__)), 'temperature': sha256_file(ROOT / 'src/external_temperature.py')}
    pinned = out / 'input_signature.json'
    if pinned.exists() and json.loads(pinned.read_text(encoding='utf-8')) != signature:
        raise ValueError('Temperature experiment changed; preserve previous evidence')
    json_write(pinned, signature)

    def fit(train, forbidden, candidate, folder):
        assert not set(train.station) & forbidden
        folder.mkdir(parents=True, exist_ok=True); receipt = folder / 'fit_manifest.json'
        if receipt.exists():
            info = json.loads(receipt.read_text(encoding='utf-8'))
            assert info['candidate'] == candidate and info['training_stations'] == sorted(train.station.unique())
            assert info['forbidden_stations'] == sorted(forbidden)
            assert sha256_file(folder / 'model.joblib') == info['model_sha256']
            return joblib.load(folder / 'model.joblib'), info
        model, fitted = fit_weather_temperature(train, FEATURES, config['ridge_alpha'])
        joblib.dump(model, folder / 'model.joblib')
        info = {'candidate': candidate, 'features': FEATURES, 'training_stations': sorted(train.station.unique()),
                'training_rows_after_domain_filter': len(fitted), 'forbidden_stations': sorted(forbidden),
                'model_sha256': sha256_file(folder / 'model.joblib'), 'reserved_validation_opened': False}
        json_write(receipt, info)
        return model, info

    comparisons, decisions, predictions = [], {}, []
    with threadpool_limits(limits=config['max_compute_threads']):
        baseline, baseline_info = fit(competition, external_ids, 'baseline', out / 'baseline')
        for outer, held in groups.items():
            for check_group, checked in groups.items():
                if check_group == outer:
                    continue
                excluded = held | checked
                candidate, info = fit(data.loc[~data.station.isin(excluded)], excluded, 'augmented_weather_ridge', out / outer / 'selection' / check_group)
                check = external.loc[external.station.isin(checked)]
                b = predict_temperature(baseline, check, FEATURES); c = predict_temperature(candidate, check, FEATURES)
                report = {'outer_held_group': outer, 'validation_group': check_group,
                          'training_excluded_groups': [outer, check_group], **paired_temperature_metrics(check, b, c)}
                comparisons.append(report)
                result = check[['station', 'time', 'road_temp']].copy()
                result['baseline_temperature_c'] = b; result['candidate_temperature_c'] = c
                folder = out / outer / 'selection' / check_group
                result.to_parquet(folder / 'selection_predictions.parquet', index=False, compression='zstd')
                json_write(folder / 'selection_metrics.json', report)
            decision = select_temperature_candidate(comparisons, outer)
            if decision['selected_candidate'] == 'baseline':
                model, info = baseline, baseline_info; relative = 'baseline/model.joblib'
            else:
                folder = out / outer / 'selected_model'
                model, info = fit(data.loc[~data.station.isin(held)], held, 'augmented_weather_ridge', folder)
                relative = (folder / 'model.joblib').relative_to(out).as_posix()
            decision.update({'model_path': relative, 'model_sha256': sha256_file(out / relative),
                             'features': FEATURES, 'training_stations': info['training_stations']})
            decisions[outer] = decision; json_write(out / outer / 'decision.json', decision)
            # Evaluate this group's first-winter temperatures only after choosing.
            check = external.loc[external.station.isin(held)]
            b = predict_temperature(baseline, check, FEATURES); c = predict_temperature(model, check, FEATURES)
            result = check[['station', 'time', 'road_temp']].copy(); result['group'] = outer
            result['baseline_temperature_c'] = b; result['selected_temperature_c'] = c
            predictions.append(result)
            print(outer, decision['selected_candidate'], 'first-winter temperature selection complete', flush=True)
    combined = pd.concat(predictions, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    combined.to_parquet(out / 'outer_development_predictions.parquet', index=False, compression='zstd')
    json_write(out / 'decisions.json', decisions)
    json_write(out / 'nested_selection_metrics.json', comparisons)
    summary = {'status': 'nested_first_winter_temperature_complete_reserved_winter_unopened', 'rows': len(combined),
               'paired_metrics': paired_temperature_metrics(combined, combined.baseline_temperature_c, combined.selected_temperature_c),
               'group_choices': decisions, 'signature': signature, 'reserved_validation_opened': False,
               'frozen_files_unchanged': len(verify_freeze(ROOT)['files']), 'protected_outcomes_used': False,
               'scope': 'First-winter development comparison only; next-winter predictions must be fixed before labels are obtained.'}
    json_write(out / 'summary.json', summary)
    print(json.dumps({k: summary[k] for k in ['status', 'rows', 'paired_metrics', 'reserved_validation_opened']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
