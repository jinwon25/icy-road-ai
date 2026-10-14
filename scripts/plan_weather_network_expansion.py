"""확보한 공식 지점 이력으로 기상망 확장 후보를 만들고 기존 캐시와 거리를 대조한다."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.weather_station_history import read_history, stable_candidates, rank_candidates

DEFAULT = ROOT / 'outputs/private/weather_network_review_20261010_v1'
SOURCE = ROOT / 'outputs/private/releases/20261007/outputs/private'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, default=DEFAULT)
    review = parser.parse_args().review.resolve(); out = review / 'metadata_analysis'
    if not review.is_relative_to((ROOT / 'outputs/private').resolve()) or out.exists():
        raise ValueError('New private metadata analysis required')
    manifest = json.loads((review / 'portal_station_manifest_v2.json').read_text(encoding='utf-8'))
    histories = []
    signatures = {str(Path(__file__).relative_to(ROOT)): sha(Path(__file__)),
                  'src/weather_station_history.py': sha(ROOT / 'src/weather_station_history.py')}
    for entry in manifest:
        path = review / entry['path']
        if entry['html_received'] or sha(path) != entry['sha256']:
            raise ValueError('Official portal did not return verified CSV')
        signatures[str(path.relative_to(ROOT))] = sha(path)
        histories.append(read_history(path, entry['kind']))
    history = pd.concat(histories, ignore_index=True)
    candidates, excluded = stable_candidates(history)
    data_path = ROOT / 'outputs/private/temperature_loss_20261010_v1/development_inputs.parquet'
    # 정답·기온을 읽지 않고 이미 고정된 개발 지점 ID만 사용한다.
    development_ids = set(pd.read_parquet(data_path, columns=['station']).station)
    meta_path = SOURCE / 'sensor_availability/metadata.csv'
    catalogue_path = SOURCE / 'external/kma_rwis_reference/station_catalog.csv'
    weather_path = SOURCE / 'point_sources/weather_coordinates.csv'
    metadata = pd.read_csv(meta_path, dtype={'station': str})
    catalog = pd.read_csv(catalogue_path, dtype={'station': str}).set_index('station')
    official = metadata.loc[metadata.kind.eq('RWIS') & metadata.station.isin(development_ids), ['station', 'lat', 'lon']]
    points = official.copy()
    missing = sorted(development_ids - set(points.station))
    points = pd.concat([points, catalog.loc[missing, ['lat', 'lon']].reset_index()], ignore_index=True)
    if len(points) != 23 or points.station.nunique() != 23:
        raise ValueError('Expected 23 development points only')
    coordinates = pd.read_csv(weather_path, dtype={'station_id': str})
    cache = {(r.kind, r.station_id) for r in coordinates.itertuples()}
    ranked = rank_candidates(points, candidates, cache)
    # 과거 목록과 현재 단일 좌표의 차이는 숨기지 않고 별도로 남긴다.
    cache_checks = []
    for row in coordinates.itertuples():
        same = candidates.loc[candidates.kind.eq(row.kind) & candidates.weather_station.eq(row.station_id)]
        cache_checks.append(dict(kind=row.kind, weather_station=row.station_id, stable_metadata_records=len(same),
                                 historical_lat=float(same.iloc[0].lat) if len(same) == 1 else None,
                                 historical_lon=float(same.iloc[0].lon) if len(same) == 1 else None,
                                 original_lat=float(row.latitudes), original_lon=float(row.longitudes)))
    distance_rows = []
    from src.weather_features import haversine_km
    for point in points.itertuples():
        for kind, pool in coordinates.groupby('kind'):
            old_distance = min(haversine_km(point.lat, point.lon, r.latitudes, r.longitudes) for r in pool.itertuples())
            new = ranked.loc[ranked.station.eq(point.station) & ranked.kind.eq(kind) & ranked['rank'].eq(1)].iloc[0]
            distance_rows.append(dict(station=point.station, kind=kind, current_cache_nearest_km=old_distance,
                                      metadata_candidate_km=float(new.distance_km), metadata_candidate_station=new.weather_station,
                                      nearest_candidate_in_cache=bool(new.already_in_weather_cache),
                                      observed_weather_improvement_verified=False))
    for path in [data_path, meta_path, catalogue_path, weather_path]:
        signatures[str(path.relative_to(ROOT))] = sha(path)
    out.mkdir()
    history.to_parquet(out / 'official_station_history.parquet', index=False, compression='zstd')
    candidates.to_csv(out / 'stable_first_winter_candidates.csv', index=False, encoding='utf-8-sig')
    excluded.to_csv(out / 'date_boundary_or_change_exclusions.csv', index=False, encoding='utf-8-sig')
    points.to_csv(out / 'development_points.csv', index=False, encoding='utf-8-sig')
    ranked.to_csv(out / 'development_weather_shortlist.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(cache_checks).to_csv(out / 'existing_cache_metadata_review.csv', index=False, encoding='utf-8-sig')
    distances = pd.DataFrame(distance_rows)
    distances.to_csv(out / 'development_distance_comparison.csv', index=False, encoding='utf-8-sig')
    for rel, digest in signatures.items():
        if sha(ROOT / rel) != digest:
            raise ValueError('Metadata input changed')
    aws_probe = json.loads((review / 'aws_probe_manifest.json').read_text(encoding='utf-8'))
    result = dict(status='metadata_expansion_shortlist_only', created_at_utc=datetime.now(timezone.utc).isoformat(),
                  history_rows=history.groupby('kind').size().to_dict(),
                  stable_candidate_stations=candidates.groupby('kind').size().to_dict(),
                  excluded_station_groups=len(excluded), development_points=len(points),
                  shortlisted_rows=len(ranked), nearest_missing_from_cache=distances.groupby('kind').nearest_candidate_in_cache.apply(lambda s: int((~s).sum())).to_dict(),
                  actual_weather_collection_complete=False, weather_api_http_status=aws_probe.get('http_status'),
                  source_signatures=signatures, files={p.name: sha(p) for p in out.iterdir()})
    (out / 'summary.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['status', 'history_rows', 'stable_candidate_stations', 'excluded_station_groups',
                                           'development_points', 'nearest_missing_from_cache', 'weather_api_http_status']}))


if __name__ == '__main__':
    main()
