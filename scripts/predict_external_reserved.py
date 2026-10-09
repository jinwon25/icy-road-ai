"""외부 다음 겨울 정답 없이9지점의 분류·온도 예측과 모델·소스를 고정한다."""
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
from src.external_augmentation import FixedDonorStateContext, matrix_with_context
from src.external_reserved import reserved_times, seal_reserved_predictions
from src.external_temperature import predict_temperature
from src.frozen_assessment import verify_freeze
from src.point_inputs import PointInputBuilder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    private = ROOT / 'outputs/private'
    folders = {'ice': private / 'external_augmentation_nested_v1', 'temperature': private / 'external_temperature_nested_v1'}
    ready = all((folder / 'summary.json').exists() for folder in folders.values())
    if args.prepare_only:
        print(json.dumps({'status': 'ready_to_predict_and_freeze' if ready else 'awaiting_completed_development_selection',
                          'reserved_predictions_saved': False, 'reserved_validation_opened': False}), flush=True)
        return
    if not ready:
        raise ValueError('Complete first-winter classification and temperature selection before reserved predictions')
    plan_path = ROOT / 'config/kma_external_validation_plan.json'
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    summaries = {name: json.loads((folder / 'summary.json').read_text(encoding='utf-8')) for name, folder in folders.items()}
    expected_status = {'ice': 'nested_first_winter_development_complete_reserved_winter_unopened',
                       'temperature': 'nested_first_winter_temperature_complete_reserved_winter_unopened'}
    for name, summary in summaries.items():
        assert summary['status'] == expected_status[name] and not summary['reserved_validation_opened']
        decisions_path = folders[name] / 'decisions.json'
        assert json.loads(decisions_path.read_text(encoding='utf-8')) == summary['group_choices']
    signature_sources = {
        'ice': {'config': 'config/external_augmentation_experiment.json', 'plan': 'config/kma_external_validation_plan.json',
                'external_features': 'outputs/private/external_development_features_v1/features.parquet',
                'external_feature_info': 'outputs/private/external_development_features_v1/summary.json',
                'competition_features': 'outputs/private/physical_features/features.parquet',
                'thermal': 'outputs/private/point_sources/rwis.parquet', 'metadata': 'outputs/private/sensor_availability/metadata.csv',
                'catalog': 'outputs/private/external/kma_rwis_reference/station_catalog.csv',
                'runner': 'scripts/evaluate_external_augmentation.py', 'augmentation': 'src/external_augmentation.py',
                'physical_context': 'src/physical_features.py', 'state_context': 'src/surface_state_context_v2.py'},
        'temperature': {'config': 'config/external_temperature_experiment.json', 'plan': 'config/kma_external_validation_plan.json',
                        'external': 'outputs/private/external_development_features_v1/features.parquet',
                        'external_info': 'outputs/private/external_development_features_v1/summary.json',
                        'competition': 'outputs/private/physical_features/features.parquet',
                        'thermal': 'outputs/private/point_sources/rwis.parquet',
                        'runner': 'scripts/evaluate_external_temperature.py', 'temperature': 'src/external_temperature.py'}}
    for name, sources in signature_sources.items():
        for key, relative in sources.items():
            if sha256_file(ROOT / relative) != summaries[name]['signature'][key]:
                raise ValueError('Development model source or input changed before reserved prediction')
    if (private / 'external/kma_rwis_reserved_v1').exists():
        raise ValueError('Reserved observations already present; new predictions prohibited')
    out = private / 'external_reserved_predictions_v1'
    if out.exists():
        raise FileExistsError('Reserved prediction evidence exists; preserve rather than overwrite')
    verify_freeze(ROOT)
    source = private / 'point_sources'
    aws = pd.read_parquet(source / 'aws.parquet'); asos = pd.read_parquet(source / 'asos.parquet')
    thermal = pd.read_parquet(source / 'rwis.parquet')
    competition_path = private / 'physical_features/features.parquet'
    competition = pd.read_parquet(competition_path)
    cutoff = pd.Timestamp(plan['development_end_kst']) + pd.Timedelta(days=1)
    meta = pd.read_csv(private / 'sensor_availability/metadata.csv', dtype={'station': str})
    meta = meta.loc[meta.kind.eq('RWIS'), ['station', 'route', 'lat', 'lon']]
    donors = set(thermal.station)
    assert len(donors) == 14 and donors == set(meta.station) == set(competition.station)
    external_ids = set().union(*map(set, plan['station_groups'].values()))
    assert not donors & external_ids
    builder = PointInputBuilder(aws, asos, thermal, pd.read_csv(source / 'weather_coordinates.csv', dtype={'station_id': str}), meta)
    # Fix reference availability using development data even though inference uses
    # strictly prior observations from later allowed development donor stations.
    available_aws = set(aws.loc[aws.source_time.lt(cutoff) & aws.air_temp.notna(), 'station'])
    available_asos = set(asos.loc[asos.source_time.lt(cutoff), 'station'])
    builder.aws = {station: rows for station, rows in builder.aws.items() if station in available_aws}
    builder.asos = {station: rows for station, rows in builder.asos.items() if station in available_asos}
    builder.moisture = set(thermal.loc[thermal.time.lt(cutoff) & thermal.humidity.notna(), 'station'])
    catalog_path = private / 'external/kma_rwis_reference/station_catalog.csv'
    catalog = pd.read_csv(catalog_path, dtype={'station': str})
    points = catalog.loc[catalog.station.isin(external_ids), ['station', 'route', 'lat', 'lon', 'elevation_m']].copy()
    points['route'] = points.route.replace({'통영-대전중부': '통영-대전중부선'})
    assert len(points) == 9 and points.station.is_unique
    times = reserved_times(plan)
    out.mkdir()
    frames, mappings = [], []
    for point in points.to_dict(orient='records'):
        frame, references = builder.build(point, times)
        frame['elevation_m'] = point['elevation_m']
        assert not set(frame) & {'ice', 'state_raw', 'road_temp'}
        frame.to_parquet(out / f"inputs_{point['station']}.parquet", index=False, compression='zstd')
        frames.append(frame); mappings.append({'station': point['station'], 'references': references})
    inputs = pd.concat(frames, ignore_index=True)
    context = FixedDonorStateContext(inputs, thermal, pd.concat([meta, points[meta.columns]], ignore_index=True),
                                     competition[['station', 'time', 'state_raw']], donors, cutoff)
    physical_path = private / 'physical_features/summary.json'
    base_features = FEATURES + json.loads(physical_path.read_text(encoding='utf-8'))['additional_features']
    baseline_info = json.loads((folders['ice'] / 'baseline/fit_manifest.json').read_text(encoding='utf-8'))
    for name in folders:
        fit_info = json.loads((folders[name] / 'baseline/fit_manifest.json').read_text(encoding='utf-8'))
        expected_hash = fit_info['files']['model.joblib'] if name == 'ice' else fit_info['model_sha256']
        assert sha256_file(folders[name] / 'baseline/model.joblib') == expected_hash
    baseline_ice = joblib.load(folders['ice'] / 'baseline/model.joblib')
    baseline_temperature = joblib.load(folders['temperature'] / 'baseline/model.joblib')
    results = []
    with threadpool_limits(limits=2):
        for group, stations in plan['station_groups'].items():
            frame = inputs.loc[inputs.station.isin(stations)]
            ice_decision = summaries['ice']['group_choices'][group]
            temp_decision = summaries['temperature']['group_choices'][group]
            for name, decision in [('ice', ice_decision), ('temperature', temp_decision)]:
                assert not set(stations) & set(decision['training_stations'])
                assert group not in decision['selection_groups']
                assert sha256_file(folders[name] / decision['model_path']) == decision['model_sha256']
            selected_ice = joblib.load(folders['ice'] / ice_decision['model_path'])
            selected_temperature = joblib.load(folders['temperature'] / temp_decision['model_path'])
            bx, base_refs = matrix_with_context(frame, context, external_ids, base_features)
            sx, selected_refs = matrix_with_context(frame, context, set(stations), base_features,
                                                   state=ice_decision['selected_candidate'] == 'augmented_surface_state_v2')
            assert list(bx) == baseline_info['features'] and list(sx) == ice_decision['features']
            result = frame[['station', 'time']].copy()
            result['group'] = group; result['selected_candidate'] = ice_decision['selected_candidate']
            result['temperature_candidate'] = temp_decision['selected_candidate']
            result['baseline_ice_score'] = baseline_ice.predict_proba(bx)[:, 1]
            result['selected_ice_score'] = selected_ice.predict_proba(sx)[:, 1]
            result['baseline_threshold'] = baseline_info['threshold']; result['selected_threshold'] = ice_decision['threshold']
            result['baseline_prediction'] = (result.baseline_ice_score >= result.baseline_threshold).astype(int)
            result['selected_prediction'] = (result.selected_ice_score >= result.selected_threshold).astype(int)
            result['baseline_temperature_c'] = predict_temperature(baseline_temperature, frame, FEATURES)
            result['selected_temperature_c'] = predict_temperature(selected_temperature, frame, FEATURES)
            results.append(result)
            json_write(out / f'{group}_context_references.json', {'baseline': base_refs, 'selected': selected_refs})
            print(group, 'reserved predictions saved without outcomes', flush=True)
    result = pd.concat(results, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    result.to_parquet(out / 'predictions.parquet', index=False, compression='zstd')
    json_write(out / 'point_references.json', mappings)
    json_write(out / 'group_decisions.json', {name: summary['group_choices'] for name, summary in summaries.items()})
    frozen_files = [competition_path.relative_to(ROOT).as_posix(), physical_path.relative_to(ROOT).as_posix(), catalog_path.relative_to(ROOT).as_posix()]
    for directory in [ROOT / 'src', ROOT / 'scripts', ROOT / 'config', source, *folders.values()]:
        frozen_files.extend(p.relative_to(ROOT).as_posix() for p in directory.rglob('*') if p.is_file()
                            and '__pycache__' not in p.parts and p.suffix != '.tmp')
    frozen_files.append('outputs/private/sensor_availability/metadata.csv')
    receipt = seal_reserved_predictions(ROOT, out, plan_path, frozen_files)
    print(json.dumps({'status': receipt['status'], 'rows': receipt['rows'], 'reserved_validation_opened': False}), flush=True)


if __name__ == '__main__':
    main()
