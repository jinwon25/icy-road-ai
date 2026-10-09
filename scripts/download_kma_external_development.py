"""사전 계획의 첫 겨울만 수집하고 다음 겨울의 검증 정답은 열지 않는다."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file
from src.frozen_assessment import verify_freeze
from src.kma_rwis_download import daily_requests, load_auth_key, parse_observations, exact_ten_minute_grid
from src.kma_rwis_transport import ValidatedRoadClient


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    for attempt in range(8):
        try:
            temporary.replace(path)
            return
        except PermissionError as error:
            # Windows readers or scanners can briefly deny atomic replacement.
            # Keep the completed temporary evidence if the denial persists.
            if getattr(error, 'winerror', None) not in (5, 32) or attempt == 7:
                raise
            time.sleep(min(.1 * (2 ** attempt), 1.))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials-file', type=Path)
    parser.add_argument('--start', default='2024-11-01')
    parser.add_argument('--end', default='2025-02-28')
    parser.add_argument('--stations', nargs='+')
    parser.add_argument('--window-minutes', type=int, default=720)
    args = parser.parse_args()
    config_path = ROOT / 'config/kma_external_validation_plan.json'
    plan = json.loads(config_path.read_text(encoding='utf-8'))
    jobs = list(daily_requests(plan, args.start, args.end, args.stations, args.window_minutes))
    key = load_auth_key(args.credentials_file)
    out = ROOT / 'outputs/private/external/kma_rwis_development_v1'
    out.mkdir(parents=True, exist_ok=True)
    pinned = out / 'plan_receipt.json'
    plan_hash = sha256_file(config_path)
    if pinned.exists():
        if json.loads(pinned.read_text(encoding='utf-8'))['plan_sha256'] != plan_hash:
            raise ValueError('Plan changed after collection began; preserve data and receipt')
    else:
        frozen = verify_freeze(ROOT)
        write_json(pinned, {'plan': plan, 'plan_sha256': plan_hash,
                           'recorded_before_development_download_utc': datetime.now(timezone.utc).isoformat(),
                           'reserved_validation_opened': False, 'frozen_files_verified': len(frozen['files'])})
    manifest_path = out / 'download_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {'plan_sha256': plan_hash, 'request_window_minutes': args.window_minutes, 'records': {}}
    if manifest['plan_sha256'] != plan_hash:
        raise ValueError('Download signature changed')
    if manifest['request_window_minutes'] != args.window_minutes:
        raise ValueError('Window changed; preserve cached request partition')
    run_receipt = out / f'collection_run_{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.json'
    snapshots = out / 'source_snapshots'; snapshots.mkdir(exist_ok=True)
    for path in [Path(__file__), ROOT / 'src/kma_rwis_download.py', ROOT / 'src/kma_rwis_transport.py']:
        target = snapshots / f'{sha256_file(path)}.py'
        if target.exists():
            if target.read_bytes() != path.read_bytes():
                raise ValueError('Collector source snapshot changed; preserve evidence')
        else:
            with target.open('xb') as handle:
                handle.write(path.read_bytes())
    write_json(run_receipt, {'started_at_utc': datetime.now(timezone.utc).isoformat(), 'runner_sha256': sha256_file(Path(__file__)),
                             'parser_sha256': sha256_file(ROOT / 'src/kma_rwis_download.py'), 'plan_sha256': plan_hash,
                             'transport_sha256': sha256_file(ROOT / 'src/kma_rwis_transport.py'),
                             'start_date_kst': args.start, 'end_date_kst': args.end, 'request_window_minutes': args.window_minutes,
                             'jobs': len(jobs), 'credential_values_recorded': False, 'reserved_validation_opened': False})
    client = ValidatedRoadClient(plan, key, out / 'transport')
    for number, (station, start, end) in enumerate(jobs, 1):
        identifier = f'{station}/{start:%Y%m%d%H%M}'
        raw = out / 'raw' / f'{identifier}.txt'
        processed = out / 'ten_minute' / f'{identifier}.parquet'
        previous = manifest['records'].get(identifier)
        if previous and raw.exists() and processed.exists() and sha256_file(raw) == previous['raw_sha256'] and sha256_file(processed) == previous['ten_minute_sha256']:
            continue
        if previous or raw.exists() or processed.exists():
            raise ValueError('Incomplete or changed cached evidence; preserve and inspect before retry')
        body, transport_requests = client.fetch(station, start, end)
        frame = parse_observations(body, station, start, end)
        ten = exact_ten_minute_grid(frame)
        raw.parent.mkdir(parents=True, exist_ok=True)
        processed.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text(body, encoding='utf-8')
        ten.to_parquet(processed, index=False, compression='zstd')
        record = {'station': station, 'start_kst': start.isoformat(), 'end_kst': end.isoformat(),
                  'downloaded_at_utc': datetime.now(timezone.utc).isoformat(), 'rows_one_minute': len(frame),
                  'raw_response_rows': int(frame.attrs.get('raw_response_rows', len(frame))),
                  'invalid_timestamp_rows_excluded': int(frame.attrs.get('invalid_timestamp_rows_excluded', 0)),
                  'excluded_timestamp_token_counts': frame.attrs.get('excluded_timestamp_token_counts', {}),
                  'rows_exact_ten_minute': len(ten), 'valid_state_rows': int(ten.ice.notna().sum()),
                  'ice_rows': int(ten.ice.eq(1).sum()), 'valid_temperature_rows': int(ten.road_temp.notna().sum()),
                  'raw_sha256': sha256_file(raw), 'ten_minute_sha256': sha256_file(processed),
                  'transport_requests': transport_requests,
                  'response_coordinate_pairs': frame[['lat', 'lon']].drop_duplicates().values.tolist() if len(frame) else [],
                  'response_elevations_m': sorted(frame.elevation_m.dropna().unique().tolist()) if len(frame) else []}
        manifest['records'][identifier] = record
        manifest['updated_at_utc'] = datetime.now(timezone.utc).isoformat()
        manifest['reserved_validation_opened'] = False
        manifest['protected_observations_requested'] = False
        write_json(manifest_path, manifest)
        print(json.dumps({'job': number, 'total': len(jobs), 'station': station, 'date_kst': start.strftime('%Y-%m-%d'),
                          'minute_rows': len(frame), 'ten_minute_rows': len(ten), 'valid_states': record['valid_state_rows'], 'ice_rows': record['ice_rows'], 'transport_requests': len(transport_requests)}, ensure_ascii=False), flush=True)
    print(json.dumps({'status': 'requested_development_download_complete', 'cached_windows': len(manifest['records']),
                      'reserved_validation_opened': False, 'frozen_files_verified': len(verify_freeze(ROOT)['files'])}), flush=True)


if __name__ == '__main__':
    main()
