"""첫 겨울 외부 관측의 원문·10분 변환·좌표·결측·계획 범위를 전수 검사한다."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file
from src.frozen_assessment import verify_freeze
from src.kma_rwis_download import daily_requests, validate_development_request, parse_observations, exact_ten_minute_grid
from src.validation import PROTECTED_STATIONS
from src.weather_features import haversine_km


def main():
    out = ROOT / 'outputs/private/external/kma_rwis_development_v1'
    plan_path = ROOT / 'config/kma_external_validation_plan.json'
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    pinned = json.loads((out / 'plan_receipt.json').read_text(encoding='utf-8'))
    manifest_bytes = (out / 'download_manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    assert pinned['plan_sha256'] == manifest['plan_sha256'] == sha256_file(plan_path)
    assert pinned['reserved_validation_opened'] is False
    assert manifest['reserved_validation_opened'] is False
    assert manifest['protected_observations_requested'] is False
    expected = {f'{sid}/{start:%Y%m%d%H%M}' for sid, start, end in daily_requests(plan, plan['development_start_kst'], plan['development_end_kst'], window_minutes=manifest['request_window_minutes'])}
    assert set(manifest['records']) <= expected
    catalog = pd.read_csv(ROOT / 'outputs/private/external/kma_rwis_reference/station_catalog.csv', dtype={'station': str}).set_index('station')
    group_by_station = {str(station): group for group, stations in plan['station_groups'].items() for station in stations}
    frames = []
    minute_rows = 0
    invalid_timestamp_rows = 0
    for identifier, record in manifest['records'].items():
        station, start, end = validate_development_request(plan, record['station'], record['start_kst'], record['end_kst'])
        assert identifier == f'{station}/{start:%Y%m%d%H%M}'
        assert datetime.fromisoformat(record['downloaded_at_utc']) >= datetime.fromisoformat(pinned['recorded_before_development_download_utc'])
        raw = out / 'raw' / f'{identifier}.txt'
        ten_path = out / 'ten_minute' / f'{identifier}.parquet'
        assert sha256_file(raw) == record['raw_sha256']
        assert sha256_file(ten_path) == record['ten_minute_sha256']
        frame = parse_observations(raw.read_text(encoding='utf-8'), station, start, end)
        excluded_times = int(frame.attrs.get('invalid_timestamp_rows_excluded', 0))
        assert excluded_times == record.get('invalid_timestamp_rows_excluded', 0)
        invalid_timestamp_rows += excluded_times
        if record.get('transport_requests'):
            cursor = start
            pieces = []
            cache_root = (out / 'transport').resolve()
            for request in record['transport_requests']:
                sid, begin, finish = validate_development_request(plan, request['station'], request['start_kst'], request['end_kst'])
                assert sid == station and begin == cursor and finish <= end
                transport_path = (cache_root / request['transport_cache_path']).resolve()
                assert transport_path.is_relative_to(cache_root)
                assert sha256_file(transport_path) == request['transport_response_sha256']
                piece = parse_observations(transport_path.read_text(encoding='utf-8'), sid, begin, finish)
                assert len(piece) == request['one_minute_rows']
                pieces.append(piece)
                cursor = finish + pd.Timedelta(minutes=1)
            assert cursor == end + pd.Timedelta(minutes=1)
            reconstructed = pd.concat(pieces, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
            pd.testing.assert_frame_equal(frame, reconstructed, check_dtype=False)
        ten = exact_ten_minute_grid(frame)
        stored = pd.read_parquet(ten_path)
        pd.testing.assert_frame_equal(ten, stored, check_dtype=False)
        assert len(frame) == record['rows_one_minute'] and len(ten) == record['rows_exact_ten_minute']
        assert int(ten.ice.notna().sum()) == record['valid_state_rows']
        assert int(ten.ice.eq(1).sum()) == record['ice_rows']
        assert int(ten.road_temp.notna().sum()) == record['valid_temperature_rows']
        minute_rows += len(frame)
        if len(ten):
            frames.append(ten)
    if not frames:
        raise ValueError('No valid development observations available for audit')
    combined = pd.concat(frames, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    assert not combined.duplicated(['station', 'time']).any()
    assert not set(combined.station) & (set(plan['competition_stations_excluded_from_external_requests']) | PROTECTED_STATIONS)
    combined['spatial_group'] = combined.station.map(group_by_station)
    assert combined.spatial_group.notna().all()
    combined['route'] = combined.station.map(catalog.route)
    metrics = []
    expected_slots = len(pd.date_range(plan['development_start_kst'], pd.Timestamp(plan['development_end_kst']) + pd.Timedelta(hours=23, minutes=50), freq='10min'))
    for station in sorted(group_by_station):
        part = combined.loc[combined.station.eq(station)].copy()
        meta = catalog.loc[station]
        coords = part[['lat', 'lon']].drop_duplicates()
        distances = [haversine_km(r.lat, r.lon, meta.lat, meta.lon) * 1000 for r in coords.itertuples()]
        counts = part.groupby(part.time.dt.date).agg(rows=('time', 'size'), valid_state=('ice', 'count'), valid_temperature=('road_temp', 'count'))
        metrics.append({'station': station, 'name': meta['name'], 'route': meta.route, 'station_type': meta.station_type,
                        'spatial_group': group_by_station[station], 'ten_minute_rows': len(part), 'expected_ten_minute_rows_full_winter': expected_slots,
                        'valid_state_rows': int(part.ice.notna().sum()), 'ice_rows': int(part.ice.eq(1).sum()),
                        'valid_temperature_rows': int(part.road_temp.notna().sum()), 'fully_observed_days_available': int(counts.rows.eq(144).sum()),
                        'fully_valid_state_days_available': int(counts.valid_state.eq(144).sum()),
                        'first_time_kst': str(part.time.min()) if len(part) else None, 'last_time_kst': str(part.time.max()) if len(part) else None,
                        'coordinate_pairs': coords.values.tolist(), 'maximum_catalog_coordinate_difference_m': max(distances) if distances else None,
                        'elevations_m': sorted(part.elevation_m.dropna().unique().tolist()), 'catalog_elevation_m': float(meta.elevation_m),
                        'state_raw_counts': {str(k): int(v) for k, v in part.state_raw.value_counts(dropna=False).items()},
                        'temperature_min_c': float(part.road_temp.min()) if part.road_temp.notna().any() else None,
                        'temperature_max_c': float(part.road_temp.max()) if part.road_temp.notna().any() else None,
                        'temperature_outside_minus50_plus80_rows': int((part.road_temp.lt(-50) | part.road_temp.gt(80)).sum()),
                        'ice_with_temperature_above_2c_rows': int((part.ice.eq(1) & part.road_temp.gt(2)).sum())})
    combined_path = out / 'observations_available.parquet'
    combined.to_parquet(combined_path, index=False, compression='zstd')
    frozen = verify_freeze(ROOT)
    summary = {'status': 'development_download_complete' if set(manifest['records']) == expected else 'development_download_partial',
               'audited_at_utc': datetime.now(timezone.utc).isoformat(), 'downloaded_windows_audited': len(manifest['records']),
               'expected_windows_full_winter': len(expected), 'one_minute_rows_reparsed': minute_rows,
               'invalid_timestamp_rows_excluded': invalid_timestamp_rows,
               'exact_ten_minute_rows': len(combined), 'valid_state_rows': int(combined.ice.notna().sum()), 'ice_rows': int(combined.ice.eq(1).sum()),
               'valid_temperature_rows': int(combined.road_temp.notna().sum()), 'stations': metrics,
               'download_manifest_snapshot_sha256': hashlib.sha256(manifest_bytes).hexdigest(), 'plan_sha256': sha256_file(plan_path),
               'observations_sha256': sha256_file(combined_path), 'reserved_validation_opened': False,
               'frozen_files_unchanged': len(frozen['files']), 'protected_observations_used': False,
               'quality_flags_are_diagnostics_not_label_filters': True,
               'model_improvement_proven': False,
               'scope': 'First-winter development observations only. Current catalog is compared with response metadata, not assumed historically identical.'}
    # Keep the exact immutable manifest that this audit actually checked, even while collection continues.
    snapshot = out / f'audited_manifest_{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.json'
    snapshot.write_bytes(manifest_bytes)
    summary['download_manifest_snapshot'] = snapshot.name
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    pd.DataFrame([{k: v for k, v in record.items() if not isinstance(v, (list, dict))} for record in metrics]).to_csv(out / 'station_quality.csv', index=False, encoding='utf-8-sig')
    print(json.dumps({k: summary[k] for k in ['status', 'downloaded_windows_audited', 'expected_windows_full_winter', 'one_minute_rows_reparsed', 'exact_ten_minute_rows', 'valid_state_rows', 'ice_rows', 'frozen_files_unchanged', 'reserved_validation_opened']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
