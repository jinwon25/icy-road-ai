"""공식 PDF의 정적 지점 목록에서 대회 사용 지점을 제외한 후보를 만든다."""
import re
import pandas as pd
from src.validation import canonical_station_id, PROTECTED_STATIONS

ROUTE_ALIASES = {'통영-대전선': '통영-대전중부', '통영-대전중부': '통영-대전중부',
                 '서해안': '서해안', '호남선': '호남선'}
STATE_TYPES = {'거점', '기본', '목표(결빙)'}


def parse_catalog(text):
    rows = []
    for line in text.splitlines():
        if not re.match(r'^\s*\d{5}\s', line):
            continue
        parts = line.split()
        if len(parts) != 7:
            raise ValueError(f'Unparsed catalog row: {line}')
        station, name, route, kind, elevation, lat, lon = parts
        rows.append({'station': station, 'name': name, 'route_raw': route,
                     'route': ROUTE_ALIASES.get(route, route), 'station_type': kind,
                     'elevation_m': float(elevation.removesuffix('m')), 'lat': float(lat), 'lon': float(lon)})
    frame = pd.DataFrame(rows)
    if frame.empty or frame.station.duplicated().any() or not frame.lat.between(33, 39).all() or not frame.lon.between(124, 132).all():
        raise ValueError('Invalid official static catalog')
    return frame


def select_candidates(catalog, competition_ids):
    blocked = {canonical_station_id(x) for x in competition_ids} | PROTECTED_STATIONS
    frame = catalog.copy()
    frame['already_in_competition_scope'] = frame.station.map(canonical_station_id).isin(blocked)
    frame['state_capable_type_candidate'] = frame.station_type.isin(STATE_TYPES)
    frame['target_route_candidate'] = frame.route.isin({'서해안', '호남선', '통영-대전중부'})
    frame['independent_station_candidate'] = ~frame.already_in_competition_scope & frame.state_capable_type_candidate
    selected = frame.loc[frame.independent_station_candidate & frame.target_route_candidate].copy()
    if set(selected.station) & blocked:
        raise AssertionError('Competition station selected')
    return frame, selected
