"""공개 지점 이력·거리 후보를 별도 계산으로 검산하고 관측 수집 전 계획을 고정한다."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha

DEFAULT = ROOT / 'outputs/private/weather_network_review_20261010_v1'
SOURCE = ROOT / 'outputs/private/releases/20261007/outputs/private/point_sources'
START, END = pd.Timestamp('2024-11-01'), pd.Timestamp('2025-03-01')


def distance_km(lat, lon, other_lat, other_lon):
    """벡터 함수와 별개로 구면 거리를 계산한다."""
    a, b, c, d = map(math.radians, (lat, lon, other_lat, other_lon))
    h = math.sin((c-a)/2)**2 + math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 6371.0088 * 2 * math.atan2(math.sqrt(h), math.sqrt(max(0, 1-h)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, default=DEFAULT)
    review = parser.parse_args().review.resolve()
    out = review / 'metadata_analysis'
    receipt = out / 'independent_verification.json'
    if not review.is_relative_to((ROOT / 'outputs/private').resolve()) or receipt.exists():
        raise ValueError('Existing private metadata analysis and new audit receipt required')
    summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
    for rel, digest in summary['source_signatures'].items():
        assert sha(ROOT / rel) == digest, rel
    for name, digest in summary['files'].items():
        assert sha(out / name) == digest, name

    # 생산 모듈의 정규화·기간 필터·순위 함수를 호출하지 않는다.
    reference = []
    stable, excluded = [], []
    for kind in ['AWS', 'ASOS']:
        raw = pd.read_csv(review / f'portal_station_lists_v2/{kind}.csv', encoding='cp949', dtype={'지점': str})
        for item in raw.to_dict('records'):
            reference.append(dict(kind=kind, weather_station=item['지점'], start_date=pd.Timestamp(item['시작일']),
                                  end_date=pd.Timestamp(item['종료일']) if pd.notna(item['종료일']) else pd.NaT,
                                  lat=float(item['위도']), lon=float(item['경도'])))
    frame = pd.DataFrame(reference)
    for key, rows in frame.groupby(['kind', 'weather_station']):
        active = [r for r in rows.itertuples() if r.start_date < END and (pd.isna(r.end_date) or r.end_date >= START)]
        if not active:
            continue
        r = active[0]
        valid = math.isfinite(r.lat) and math.isfinite(r.lon) and -90 <= r.lat <= 90 and -180 <= r.lon <= 180 and (r.lat, r.lon) != (0, 0)
        if len(active) == 1 and r.start_date < START and (pd.isna(r.end_date) or r.end_date >= END) and valid:
            stable.append(dict(kind=key[0], weather_station=key[1], lat=r.lat, lon=r.lon))
        else:
            excluded.append(key)
    reference_candidates = pd.DataFrame(stable)
    saved = pd.read_csv(out / 'stable_first_winter_candidates.csv', dtype={'weather_station': str})
    keys = ['kind', 'weather_station']
    pd.testing.assert_frame_equal(saved[keys+['lat', 'lon']].sort_values(keys).reset_index(drop=True),
                                  reference_candidates.sort_values(keys).reset_index(drop=True), check_dtype=False)
    saved_exclusions = pd.read_csv(out / 'date_boundary_or_change_exclusions.csv', dtype={'weather_station': str})
    assert set(map(tuple, saved_exclusions[keys].to_numpy())) == set(excluded)
    assert not saved.observations_available_verified.any()
    points = pd.read_csv(out / 'development_points.csv', dtype={'station': str})
    allowed = {'12103', '12209', '12210', '12211', '12409', '23202', '23203', '23204', '23403',
               '33103', '33206', '33409', '33410', '33412', '12207', '12408', '23205', '23404',
               '33205', '33207', '33408', '33413', '33414'}
    assert set(points.station) == allowed and len(points) == 23
    coordinates = pd.read_csv(SOURCE / 'weather_coordinates.csv', dtype={'station_id': str})
    existing = set(zip(coordinates.kind, coordinates.station_id))
    ranks = pd.read_csv(out / 'development_weather_shortlist.csv', dtype={'station': str, 'weather_station': str})
    distances = pd.read_csv(out / 'development_distance_comparison.csv', dtype={'station': str, 'metadata_candidate_station': str})
    checks = 0
    for point in points.itertuples():
        for kind in ['AWS', 'ASOS']:
            pool = reference_candidates.loc[reference_candidates.kind.eq(kind)]
            ordered = sorted((distance_km(point.lat, point.lon, r.lat, r.lon), r.weather_station) for r in pool.itertuples())[:3]
            selected = ranks.loc[ranks.station.eq(point.station) & ranks.kind.eq(kind)].sort_values('rank')
            assert selected.weather_station.tolist() == [s for _, s in ordered]
            assert selected['rank'].tolist() == [1, 2, 3]
            np.testing.assert_allclose(selected.distance_km, [d for d, _ in ordered], rtol=0, atol=1e-9)
            assert selected.already_in_weather_cache.tolist() == [(kind, s) in existing for _, s in ordered]
            old = coordinates.loc[coordinates.kind.eq(kind)]
            nearest_old = min(distance_km(point.lat, point.lon, r.latitudes, r.longitudes) for r in old.itertuples())
            saved_distance = distances.loc[distances.station.eq(point.station) & distances.kind.eq(kind)].iloc[0]
            np.testing.assert_allclose([saved_distance.current_cache_nearest_km, saved_distance.metadata_candidate_km],
                                       [nearest_old, ordered[0][0]], rtol=0, atol=1e-9)
            checks += len(ordered)
    assert not ranks.observation_data_verified.any() and not distances.observed_weather_improvement_verified.any()

    cache_checks = pd.read_csv(out / 'existing_cache_metadata_review.csv', dtype={'weather_station': str})
    gaps = []
    for c in cache_checks.itertuples():
        match = reference_candidates.loc[reference_candidates.kind.eq(c.kind) & reference_candidates.weather_station.eq(c.weather_station)]
        assert len(match) == c.stable_metadata_records
        gap = None
        if len(match) == 1:
            m = match.iloc[0]
            np.testing.assert_allclose([c.historical_lat, c.historical_lon], [m.lat, m.lon], rtol=0, atol=1e-10)
            gap = distance_km(m.lat, m.lon, c.original_lat, c.original_lon) * 1000
        gaps.append(dict(kind=c.kind, weather_station=c.weather_station, gap_m=gap,
                         historical_coordinate_verified=len(match) == 1))
    gap_frame = pd.DataFrame(gaps)
    gap_frame.to_csv(out / 'cache_coordinate_gaps.csv', index=False, encoding='utf-8-sig')
    # 원본 기상 캐시의 기간만 확인한다. 도로 정답이나 완료 평가 예측은 읽지 않는다.
    aws_path = SOURCE / 'aws.parquet'
    aws = pd.read_parquet(aws_path, columns=['station', 'source_time', 'lat', 'lon'])
    winter = aws.loc[aws.source_time.ge(START) & aws.source_time.lt(END)]
    late = aws.loc[aws.station.eq('341')]
    official_341 = frame.loc[frame.kind.eq('AWS') & frame.weather_station.eq('341')]
    assert len(official_341) == 1 and official_341.iloc[0].start_date == pd.Timestamp('2025-12-10')
    assert len(late) == 11664 and not winter.station.eq('341').any()
    assert late.source_time.min() == pd.Timestamp('2025-12-10')
    # 기존 개발 연결은 첫 겨울 캐시의 비어 있지 않은 관측소만 후보에 넣는다.
    inventory_result = dict(cached_station_count=aws.station.nunique(), first_winter_station_count=winter.station.nunique(),
                            aws341=dict(official_start_date='2025-12-10', cached_first_time=str(late.source_time.min()),
                                        cached_last_time=str(late.source_time.max()), cached_rows=len(late), first_winter_rows=0,
                                        finding='late_start_not_first_winter_relocation'))
    (out / 'cache_period_check.json').write_text(json.dumps(inventory_result, indent=2) + '\n', encoding='utf-8')

    nearest = ranks.loc[ranks.kind.eq('AWS') & ranks['rank'].eq(1) & ~ranks.already_in_weather_cache]
    addition_ids = sorted(nearest.weather_station.unique())
    assert addition_ids == ['614', '647', '730', '914']
    plan = dict(status='planned_only_actual_api_403', created_at_utc=datetime.now(timezone.utc).isoformat(),
                experiment='expand_AWS_only_keep_existing_ASOS_and_weather14_model_settings',
                target_road_stations=sorted(allowed), development_start_kst=str(START), development_end_exclusive_kst=str(END),
                additional_AWS_stations=addition_ids, ASOS_expansion_deferred=['238', '264'],
                source_selection='metadata_only_nearest_missing_AWS; third_rank_fallback_requires_separate_plan',
                input_mapping=dict(air_temp='TA', humidity='HM', wind_speed='WS10', rain_15m='RN-15m', dewpoint='TD'),
                observation_time='KST; preserve original minute rows and exact ten-minute slots; no interpolated timestamps',
                missing_policy='API documentation: values <= -50 are missing/error; apply only to new API records',
                maximum_request_hours=24, minimum_request_interval_seconds=1.3,
                source_join='strictly before target time; age <= 60 minutes; no target road temperature or state',
                initial_history='retain cold-start coverage; do not invent preceding 3h or 72h weather history',
                metadata_coordinates='use first-winter stable dated metadata; do not overwrite old competition caches',
                gates=['complete raw-response/hash/coordinate/time/unit/duplicate/range audit before feature construction',
                       'same 23 development stations and 4 nested spatial groups; same model/settings and valid-row denominators',
                       'improve macro MAE and RMSE; each station MAE harm <= 5%; near-freezing MAE must not worsen',
                       'report Ice daily metrics, events, station concentration and FP/FN using fixed temperature/moisture policy',
                       'do not reuse protected, opened 8/4 or evaluated next-winter outcomes for selection'],
                access_required='AWS minute-data service utilization approval must be checked; no access grant inferred from silence',
                actual_collection_complete=False, candidate_promoted=False)
    (out / 'aws_expansion_plan.json').write_text(json.dumps(plan, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    result = dict(status='independent_metadata_audit_passed', audited_at_utc=datetime.now(timezone.utc).isoformat(),
                  summary_sha256=sha(out / 'summary.json'), audit_source_sha256=sha(Path(__file__)),
                  history_rows_verified=len(frame), stable_counts=reference_candidates.groupby('kind').size().to_dict(),
                  exclusion_groups_verified=len(excluded), development_stations_verified=len(points), candidate_ranks_verified=checks,
                  cache_coordinate_records_verified=len(gaps), coordinate_gap_over_20m=int(gap_frame.gap_m.gt(20).sum()),
                  cache_period_check=inventory_result, aws_cache_sha256=sha(aws_path),
                  actual_weather_collection_complete=False, observations_available_claimed=False,
                  new_files={p.name: sha(p) for p in out.iterdir() if p.name not in summary['files'] and p.name != 'summary.json'})
    with receipt.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, allow_nan=False); handle.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
