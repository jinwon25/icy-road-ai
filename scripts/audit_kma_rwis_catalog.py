"""공식 정적 목록만 읽어 독립 관측 후보를 추출한다. 관측 API는 호출하지 않는다."""
import json
import os
import sys
from pathlib import Path
import pandas as pd
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.kma_station_catalog import parse_catalog, select_candidates
from src.data_source import sha256_file
from src.validation import PROTECTED_STATIONS
from src.weather_features import haversine_km
from src.frozen_assessment import verify_freeze


def main():
    private = ROOT / 'outputs/private'; out = private / 'external/kma_rwis_reference'
    manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
    for record in manifest['files']:
        assert sha256_file(out / record['path']) == record['sha256']
    reader = PdfReader(out / 'road_stations.pdf')
    text = '\n\n'.join(page.extract_text(extraction_mode='layout') for page in reader.pages)
    catalog = parse_catalog(text); assert len(catalog) == 366
    metadata = pd.read_csv(private / 'sensor_availability/metadata.csv', dtype={'station': str})
    competition_ids = set(metadata.station) | PROTECTED_STATIONS
    annotated, selected = select_candidates(catalog, competition_ids)
    assert competition_ids <= set(catalog.station)
    dev = catalog.loc[catalog.station.isin(metadata.loc[metadata.kind.eq('RWIS'), 'station'])]
    known = catalog.loc[catalog.station.isin(competition_ids)]
    validated_max = float(json.loads((private / 'segment_inference_v1/audit.json').read_text(encoding='utf-8'))['max_reference_distance_km'])
    for i, row in selected.iterrows():
        same = dev.loc[dev.route.eq(row.route)]
        distances = [(haversine_km(row.lat, row.lon, x.lat, x.lon), x.station) for x in same.itertuples()]
        distance, station = min(distances)
        nearest_used = min(haversine_km(row.lat, row.lon, x.lat, x.lon) for x in known.itertuples())
        selected.loc[i, 'nearest_development_station'] = station
        selected.loc[i, 'nearest_development_distance_km'] = distance
        selected.loc[i, 'nearest_competition_site_distance_km'] = nearest_used
        selected.loc[i, 'geographic_screen_pass'] = bool(distance <= validated_max and nearest_used >= 1.)
    annotated.to_csv(out / 'station_catalog.csv', index=False, encoding='utf-8-sig')
    selected.to_csv(out / 'independent_station_candidates.csv', index=False, encoding='utf-8-sig')
    frozen = verify_freeze(ROOT)
    key_present = bool(os.getenv('KMA_AUTH_KEY'))
    access_path = private / 'kma_api_access_check_20261009.json'
    access = json.loads(access_path.read_text(encoding='utf-8')) if access_path.exists() else {}
    verified_access = access.get('http_status') == 200 and access.get('data_rows_returned', 0) > 0
    download_path = private / 'external/kma_rwis_development_v1/download_manifest.json'
    download = json.loads(download_path.read_text(encoding='utf-8')) if download_path.exists() else {}
    cached = len(download.get('records', {}))
    summary = {'status': 'static_candidates_first_winter_development_collection_started' if cached else ('static_candidates_observations_not_downloaded' if key_present or verified_access else 'static_candidates_only_api_key_not_configured'), 'catalog_rows': len(catalog),
               'api_key_configured': key_present or verified_access,
               'api_key_environment_configured': key_present,
               'api_access_previously_verified': verified_access,
               'competition_station_ids_excluded': sorted(competition_ids),
               'candidate_rows_all_routes': int(annotated.independent_station_candidate.sum()),
               'candidate_rows_target_routes': len(selected), 'target_route_counts': selected.groupby('route').size().to_dict(),
               'geographic_screen_candidate_ids': selected.loc[selected.geographic_screen_pass.eq(True), 'station'].tolist(),
               'geographic_screen_max_reference_km': validated_max, 'co_location_exclusion_radius_km': 1.,
               'geographic_screen_semantics': 'Analysis screening only; neither independence nor generalization is proven.',
               'actual_state_data_available_unconfirmed': True, 'historical_metadata_validity_unconfirmed': True,
               'observations_downloaded': bool(cached), 'observation_windows_cached_at_catalog_audit': cached,
               'observation_scope': 'first_winter_development_only' if cached else 'none',
               'reserved_validation_opened': False, 'protected_observations_downloaded': False,
               'api_authkey_environment_name': 'KMA_AUTH_KEY', 'frozen_files_unchanged': len(frozen['files']),
               'source_pdf_sha256': sha256_file(out / 'road_stations.pdf'),
               'catalog_sha256': sha256_file(out / 'station_catalog.csv'),
               'candidates_sha256': sha256_file(out / 'independent_station_candidates.csv')}
    (out / 'catalog_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__': main()
