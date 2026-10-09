"""외부 첫 겨울 정답을 예측 입력에서 분리한 채 기존 기상 입력에 연결한다."""
import argparse
import json
from pathlib import Path
import shutil
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file
from src.frozen_assessment import verify_freeze
from src.external_development_inputs import CACHE_RELATIVE, input_signature, load_cached_inputs
from src.point_inputs import PointInputBuilder
from src.validation import assert_training_stations
from scripts.baseline_ice_logistic import FEATURES
from src.physical_features import CONTEXT_FEATURES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', action='store_true', help='미완료 수집의 입력 연결만 확인. 모델 선택·학습에는 사용하지 않는다.')
    args = parser.parse_args()
    private = ROOT / 'outputs/private'
    source = private / 'external/kma_rwis_development_v1'
    summary_path = source / 'summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    if summary['status'] != 'development_download_complete' and not args.snapshot:
        raise ValueError('Complete development collection and audit required before model development')
    assert summary['reserved_validation_opened'] is False and summary['protected_observations_used'] is False
    observations_path = source / 'observations_available.parquet'
    assert sha256_file(observations_path) == summary['observations_sha256']
    observations = pd.read_parquet(observations_path)
    assert_training_stations(observations.station.unique())
    plan = json.loads((ROOT / 'config/kma_external_validation_plan.json').read_text(encoding='utf-8'))
    cutoff = pd.Timestamp(plan['development_end_kst']) + pd.Timedelta(days=1)
    assert observations.time.lt(cutoff).all() and observations.time.ge(plan['development_start_kst']).all()
    points = pd.read_csv(private / 'point_sources/weather_coordinates.csv', dtype={'station_id': str})
    meta = pd.read_csv(private / 'sensor_availability/metadata.csv', dtype={'station': str})
    meta = meta.loc[meta.kind.eq('RWIS'), ['station', 'route', 'lat', 'lon']]
    aws = pd.read_parquet(private / 'point_sources/aws.parquet')
    asos = pd.read_parquet(private / 'point_sources/asos.parquet')
    rwis = pd.read_parquet(private / 'point_sources/rwis.parquet')
    # Restrict even donor sensor-availability selection to the development winter.
    builder = PointInputBuilder(aws.loc[aws.source_time.lt(cutoff)], asos.loc[asos.source_time.lt(cutoff)],
                                rwis.loc[rwis.time.lt(cutoff)], points, meta)
    catalog = pd.read_csv(private / 'external/kma_rwis_reference/station_catalog.csv', dtype={'station': str}).set_index('station')
    physical = json.loads((private / 'physical_features/summary.json').read_text(encoding='utf-8'))
    features = FEATURES + physical['additional_features'] + CONTEXT_FEATURES
    frames, references = [], []
    cache_manifest = ROOT / CACHE_RELATIVE / 'manifest.json'
    cached_signature = input_signature(ROOT) if cache_manifest.exists() else None
    for station, part in observations.groupby('station', sort=True):
        row = catalog.loc[station]
        point = {'station': station, 'route': '통영-대전중부선' if row.route == '통영-대전중부' else row.route,
                 'lat': float(row.lat), 'lon': float(row.lon), 'elevation_m': float(row.elevation_m)}
        # Build inputs using only static target metadata and allowed donors, before joining outcomes.
        if cached_signature is None:
            frame, selected = builder.build(point, part.time)
        else:
            frame, selected = load_cached_inputs(ROOT, station, part.time, cached_signature)
        frame['elevation_m'] = point['elevation_m']
        assert set(features) <= set(frame) and not set(frame) & {'ice', 'state_raw', 'road_temp'}
        frame = frame.merge(part[['station', 'time', 'ice', 'state_raw', 'road_temp', 'spatial_group']], on=['station', 'time'], how='left', validate='one_to_one')
        assert len(frame) == len(part)
        frames.append(frame)
        references.append({'station': station, 'static_target': point, 'sources': selected})
    result = pd.concat(frames, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(result[['station', 'time', 'ice', 'state_raw', 'road_temp']], observations[['station', 'time', 'ice', 'state_raw', 'road_temp']], check_dtype=False)
    observation_hash = sha256_file(observations_path)
    name = f'external_development_features_snapshot_{observation_hash[:12]}' if args.snapshot else 'external_development_features_v1'
    out = private / name
    if out.exists():
        raise ValueError('Feature evidence already exists; preserve and audit rather than overwrite')
    out.mkdir()
    shutil.copy2(observations_path, out / 'input_observations.parquet')
    shutil.copy2(summary_path, out / 'input_audit.json')
    shutil.copy2(ROOT / 'config/kma_external_validation_plan.json', out / 'input_plan.json')
    shutil.copy2(Path(__file__), out / 'source_runner.py')
    result.to_parquet(out / 'features.parquet', index=False, compression='zstd')
    (out / 'references.json').write_text(json.dumps(references, ensure_ascii=False, indent=2), encoding='utf-8')
    signature = {'observations': observation_hash, 'audit': sha256_file(summary_path), 'plan': sha256_file(ROOT / 'config/kma_external_validation_plan.json'),
                 'runner': sha256_file(Path(__file__)), 'point_builder': sha256_file(ROOT / 'src/point_inputs.py'),
                 'sources': {str(p.relative_to(ROOT)): sha256_file(p) for p in (private / 'point_sources').iterdir() if p.is_file()}}
    if cached_signature is not None:
        signature['precomputed_input_manifest'] = sha256_file(cache_manifest)
        signature['precomputed_input_sources'] = cached_signature
    info = {'status': 'partial_input_integration_only' if args.snapshot else 'external_development_features_ready', 'model_training_permitted': not args.snapshot,
            'rows': len(result), 'stations': sorted(result.station.unique()), 'features': features,
            'valid_state_rows': int(result.ice.notna().sum()), 'ice_rows': int(result.ice.eq(1).sum()),
            'feature_nonmissing_rows': {name: int(result[name].notna().sum()) for name in features},
            'target_labels_used_for_inputs': False, 'external_dynamic_observations_used_for_inputs': False,
            'development_donor_cutoff_kst': str(cutoff), 'reserved_validation_opened': False,
            'signatures': signature, 'features_sha256': sha256_file(out / 'features.parquet'), 'frozen_files_unchanged': len(verify_freeze(ROOT)['files'])}
    (out / 'summary.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: info[k] for k in ['status', 'rows', 'valid_state_rows', 'ice_rows', 'model_training_permitted', 'frozen_files_unchanged']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
