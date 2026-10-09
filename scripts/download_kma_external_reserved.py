"""9지점 전체 예측 영수증을 검증한 뒤에만 별도 다음 겨울 정답을 수집한다."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file
from src.external_reserved import ReservedRoadClient, reserved_request_plan, verify_reserved_freeze
from src.frozen_assessment import verify_freeze
from src.kma_rwis_download import daily_requests, load_auth_key, parse_observations, exact_ten_minute_grid
from scripts.download_kma_external_development import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials-file', type=Path)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    private = ROOT / 'outputs/private'
    freeze = private / 'external_reserved_predictions_v1'
    if not (freeze / 'predictions_receipt.json').exists():
        if args.prepare_only:
            print(json.dumps({'status': 'blocked_until_all_predictions_fixed', 'api_requested': False}), flush=True)
            return
        raise ValueError('All nine-station predictions and model/source hashes must be fixed before reserved collection')
    receipt = verify_reserved_freeze(ROOT, freeze)
    if args.prepare_only:
        print(json.dumps({'status': 'reserved_collection_gate_verified', 'api_requested': False,
                          'prediction_rows_fixed': receipt['rows']}), flush=True)
        return
    verify_freeze(ROOT)
    key = load_auth_key(args.credentials_file)
    out = private / 'external/kma_rwis_reserved_v1'
    plan = reserved_request_plan(receipt)
    client = ReservedRoadClient(ROOT, freeze, key, out / 'transport')
    out.mkdir(parents=True, exist_ok=True)
    receipt_hash = sha256_file(freeze / 'predictions_receipt.json')
    opened = out / 'collection_receipt.json'
    if opened.exists():
        old = json.loads(opened.read_text(encoding='utf-8'))
        if old['prediction_receipt_sha256'] != receipt_hash:
            raise ValueError('Reserved predictions changed after outcome acquisition began')
    else:
        write_json(opened, {'prediction_receipt_sha256': receipt_hash,
                            'collection_started_at_utc': datetime.now(timezone.utc).isoformat(),
                            'prediction_sealed_at_utc': receipt['sealed_at_utc'],
                            'partition': 'reserved_validation', 'credential_values_recorded': False})
    manifest_path = out / 'download_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {
        'prediction_receipt_sha256': receipt_hash, 'request_window_minutes': 720, 'records': {}}
    if manifest['prediction_receipt_sha256'] != receipt_hash or manifest['request_window_minutes'] != 720:
        raise ValueError('Reserved acquisition signature changed')
    jobs = list(daily_requests(plan, plan['development_start_kst'], plan['development_end_kst'], window_minutes=720))
    for number, (station, start, end) in enumerate(jobs, 1):
        identifier = f'{station}/{start:%Y%m%d%H%M}'
        raw = out / 'raw' / f'{identifier}.txt'; processed = out / 'ten_minute' / f'{identifier}.parquet'
        previous = manifest['records'].get(identifier)
        if previous and raw.exists() and processed.exists() and sha256_file(raw) == previous['raw_sha256'] and sha256_file(processed) == previous['ten_minute_sha256']:
            continue
        if previous or raw.exists() or processed.exists():
            raise ValueError('Reserved cached evidence incomplete or changed; preserve before retry')
        body, transport = client.fetch(station, start, end)
        frame = parse_observations(body, station, start, end); ten = exact_ten_minute_grid(frame)
        raw.parent.mkdir(parents=True, exist_ok=True); processed.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text(body, encoding='utf-8'); ten.to_parquet(processed, index=False, compression='zstd')
        manifest['records'][identifier] = {'station': station, 'start_kst': start.isoformat(), 'end_kst': end.isoformat(),
            'downloaded_at_utc': datetime.now(timezone.utc).isoformat(), 'rows_one_minute': len(frame),
            'raw_response_rows': int(frame.attrs.get('raw_response_rows', len(frame))),
            'invalid_timestamp_rows_excluded': int(frame.attrs.get('invalid_timestamp_rows_excluded', 0)),
            'rows_exact_ten_minute': len(ten), 'valid_state_rows': int(ten.ice.notna().sum()),
            'ice_rows': int(ten.ice.eq(1).sum()), 'valid_temperature_rows': int(ten.road_temp.notna().sum()),
            'raw_sha256': sha256_file(raw), 'ten_minute_sha256': sha256_file(processed), 'transport_requests': transport}
        manifest.update(updated_at_utc=datetime.now(timezone.utc).isoformat(), protected_observations_requested=False)
        write_json(manifest_path, manifest)
        print(json.dumps({'job': number, 'total': len(jobs), 'station': station,
                          'date_kst': start.strftime('%Y-%m-%d'), 'ten_minute_rows': len(ten)}, ensure_ascii=False), flush=True)
    verify_reserved_freeze(ROOT, freeze)
    print(json.dumps({'status': 'reserved_download_complete_requires_single_assessment', 'windows': len(manifest['records'])}), flush=True)


if __name__ == '__main__':
    main()
