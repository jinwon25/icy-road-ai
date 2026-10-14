"""공식 지점 CSV의 날짜 이력으로 고정 좌표 후보를 만든다. 관측 가용성을 보장하지 않는다."""
from pathlib import Path
import numpy as np
import pandas as pd

from src.validation import canonical_station_id, PROTECTED_STATIONS
from src.weather_features import haversine_km

COLUMN_MAP = {'지점': 'weather_station', '시작일': 'start_date', '종료일': 'end_date',
              '지점명': 'name', '위도': 'lat', '경도': 'lon', '노장해발고도(m)': 'elevation_m'}


def normalize_history(frame, kind):
    if kind not in {'AWS', 'ASOS'} or not set(COLUMN_MAP) <= set(frame):
        raise ValueError('Expected official AWS/ASOS station-history schema')
    result = frame[list(COLUMN_MAP)].rename(columns=COLUMN_MAP).copy()
    result['weather_station'] = result.weather_station.map(canonical_station_id)
    if not result.weather_station.str.fullmatch(r'[0-9]+').all():
        raise ValueError('Invalid weather station identifier')
    result['start_date'] = pd.to_datetime(result.start_date, format='%Y-%m-%d', errors='raise')
    result['end_date'] = pd.to_datetime(result.end_date, format='%Y-%m-%d', errors='raise')
    if result.start_date.isna().any() or (result.end_date.notna() & result.end_date.lt(result.start_date)).any():
        raise ValueError('Missing or inverted metadata interval')
    for col in ['lat', 'lon', 'elevation_m']:
        result[col] = pd.to_numeric(result[col], errors='raise')
    result['coordinate_valid'] = (np.isfinite(result.lat) & np.isfinite(result.lon)
                                   & result.lat.between(-90, 90) & result.lon.between(-180, 180)
                                   & ~((result.lat == 0) & (result.lon == 0)))
    result['kind'] = kind
    return result


def read_history(path, kind):
    # 공공 포털 CSV는 cp949다. HTML 오류 페이지는 CSV로 해석하지 않는다.
    prefix = Path(path).read_bytes()[:512].lower()
    if b'<html' in prefix or b'<!doctype' in prefix:
        raise ValueError('HTML response is not station metadata')
    return normalize_history(pd.read_csv(path, encoding='cp949', dtype={'지점': str}), kind)


def stable_candidates(history, start='2024-11-01', end='2025-03-01'):
    """변경일의 시각이 없어 기간 중 변경 지점·시작일 경계 지점을 제외한다."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if start.tz is not None or end.tz is not None or start >= end:
        raise ValueError('Naive ordered metadata window required')
    overlap = history.loc[history.start_date.lt(end) & (history.end_date.isna() | history.end_date.ge(start))]
    counts = overlap.groupby(['kind', 'weather_station']).size()
    rows, excluded = [], []
    for (kind, station), part in overlap.groupby(['kind', 'weather_station'], sort=True):
        row = part.iloc[0]
        covers = row.start_date < start and (pd.isna(row.end_date) or row.end_date >= end)
        if counts.loc[kind, station] != 1 or not covers or not row.coordinate_valid:
            excluded.append(dict(kind=kind, weather_station=station, overlapping_records=len(part),
                                 reason='change_or_boundary_or_invalid_coordinate'))
            continue
        rows.append(row.to_dict() | {'observations_available_verified': False, 'date_precision': 'day'})
    return pd.DataFrame(rows, columns=[*history.columns, 'observations_available_verified', 'date_precision']), pd.DataFrame(excluded)


def rank_candidates(points, candidates, existing, limit=3):
    """좌표·날짜 이력만으로 후보를 정렬하며 결빙/온도 정답은 받지 않는다."""
    if {'ice', 'state_raw', 'road_temp'} & set(points) or not isinstance(limit, int) or not 1 <= limit <= 10:
        raise ValueError('Metadata-only points and a small candidate limit required')
    points = points.copy(); points['station'] = points.station.map(canonical_station_id)
    if points.station.duplicated().any() or points.station.isin(PROTECTED_STATIONS | {'<missing>'}).any():
        raise ValueError('Duplicate, protected or missing road point')
    if not np.isfinite(points[['lat', 'lon']]).all().all():
        raise ValueError('Missing target coordinate')
    existing = {(str(k), str(s)) for k, s in existing}
    rows = []
    for point in points.itertuples():
        for kind, pool in candidates.groupby('kind'):
            ranked = sorted((haversine_km(point.lat, point.lon, row.lat, row.lon), row.weather_station, row.name)
                            for row in pool.itertuples())[:limit]
            for rank, (distance, station, name) in enumerate(ranked, 1):
                rows.append(dict(station=point.station, kind=kind, rank=rank, weather_station=station,
                                 weather_name=name, distance_km=distance,
                                 already_in_weather_cache=(kind, station) in existing,
                                 observation_data_verified=False))
    return pd.DataFrame(rows)
