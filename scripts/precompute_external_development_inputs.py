"""수집 대기 중 외부9지점 첫 겨울 전체의 정답 없는 기상 입력을 생성한다."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file
from src.external_development_inputs import CACHE_RELATIVE, development_context, input_signature, validate_input_frame
from src.frozen_assessment import verify_freeze


def write_json(path, value):
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def main():
    signature = input_signature(ROOT)
    plan, times, points, builder, donors = development_context(ROOT)
    frozen = verify_freeze(ROOT)
    out = ROOT / CACHE_RELATIVE
    out.mkdir(exist_ok=True)
    manifest_path = out / 'manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest['signature'] != signature:
            raise ValueError('Input source signature changed; preserve existing cache')
    else:
        manifest = {'status': 'development_inputs_partial_without_target_observations',
                    'started_at_utc': datetime.now(timezone.utc).isoformat(),
                    'signature': signature, 'records': {}, 'allowed_dynamic_donors': donors,
                    'target_observations_used': False, 'reserved_outcomes_used': False,
                    'model_training_started': False, 'frozen_files_unchanged': len(frozen['files']),
                    'first_time_kst': str(times.min()), 'last_time_kst': str(times.max())}
        write_json(manifest_path, manifest)
    for station, point in points.items():
        path = out / f'{station}.parquet'
        prior = manifest['records'].get(station)
        if prior:
            if sha256_file(path) != prior['sha256']:
                raise ValueError('Existing cached evidence changed')
            import pandas as pd
            validate_input_frame(pd.read_parquet(path), station, times)
            continue
        if path.exists():
            raise ValueError('Unrecorded cache file exists; preserve and inspect')
        frame, references = builder.build(point, times)
        frame['elevation_m'] = point['elevation_m']
        validate_input_frame(frame, station, times)
        for name in ['near_source', 'moisture_source']:
            if references[name] is not None and references[name] not in donors:
                raise ValueError('External or protected dynamic donor selected')
        temporary = path.with_suffix('.parquet.tmp')
        frame.to_parquet(temporary, index=False, compression='zstd')
        temporary.replace(path)
        manifest['records'][station] = {'rows': len(frame), 'sha256': sha256_file(path),
                                         'columns': frame.columns.tolist(), 'static_target': point,
                                         'references': references}
        write_json(manifest_path, manifest)
        print(json.dumps({'station': station, 'input_rows': len(frame), 'target_observations_used': False}), flush=True)
    if input_signature(ROOT) != signature:
        raise ValueError('Inputs or sources changed while computing cache')
    if set(manifest['records']) != set(points):
        raise ValueError('Missing cached station')
    manifest['status'] = 'development_inputs_complete_without_target_observations'
    manifest['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
    manifest['frozen_files_unchanged'] = len(verify_freeze(ROOT)['files'])
    write_json(manifest_path, manifest)
    print(json.dumps({'status': manifest['status'], 'rows': sum(r['rows'] for r in manifest['records'].values()),
                      'stations': len(points), 'target_observations_used': False, 'frozen_files_unchanged': manifest['frozen_files_unchanged']}), flush=True)


if __name__ == '__main__':
    main()
