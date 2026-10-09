"""기상청 지점별 매분자료 수집의 인증·범위·스키마·정답 보존 규칙."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
import os
from pathlib import Path
import re

import pandas as pd

from src.validation import PROTECTED_STATIONS, canonical_station_id, normalize_state


class RwisResponseError(ValueError):
    """요청 URL이나 인증값을 포함하지 않는 API 오류."""


def load_auth_key(credentials_file=None):
    key = os.getenv('KMA_AUTH_KEY', '').strip()
    if key:
        return key
    if credentials_file is None:
        raise ValueError('KMA_AUTH_KEY is not configured')
    found = []
    for line in Path(credentials_file).read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].strip()
        if '=' not in line:
            continue
        name, value = line.split('=', 1)
        if name.strip() == 'KMA_AUTH_KEY':
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            found.append(value)
    if len(found) != 1 or not found[0].strip():
        raise ValueError('Expected one nonempty KMA_AUTH_KEY assignment')
    return found[0].strip()


def validate_development_request(plan, station, start, end):
    station = canonical_station_id(station)
    allowed = {str(s) for group in plan['station_groups'].values() for s in group}
    blocked = set(plan['competition_stations_excluded_from_external_requests']) | PROTECTED_STATIONS
    if station in blocked or station not in allowed:
        raise ValueError('Station outside the permitted external development plan')
    if plan['collector_permitted_partition'] != 'development_only':
        raise ValueError('Unexpected collection partition')
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if start.tz is not None or end.tz is not None:
        raise ValueError('Use explicit naive KST request timestamps')
    first = pd.Timestamp(plan['development_start_kst'])
    after = pd.Timestamp(plan['development_end_kst']) + pd.Timedelta(days=1)
    if not first <= start <= end < after:
        raise ValueError('Reserved validation winter is closed; development dates only')
    if end - start >= pd.Timedelta(minutes=plan['request_maximum_minutes']):
        raise ValueError('Request interval exceeds the permitted 24-hour window')
    return station, start, end


def daily_requests(plan, start_date, end_date, stations=None, window_minutes=1440):
    allowed = [str(s) for group in plan['station_groups'].values() for s in group]
    selected = allowed if stations is None else list(map(str, stations))
    if len(selected) != len(set(selected)):
        raise ValueError('Duplicate requested station')
    if not isinstance(window_minutes, int) or not 1 <= window_minutes <= 1440:
        raise ValueError('Window must be between one minute and one day')
    first, last = datetime.fromisoformat(start_date), datetime.fromisoformat(end_date)
    if first.time() != datetime.min.time() or last.time() != datetime.min.time() or first > last:
        raise ValueError('Invalid inclusive date range')
    day = first
    while day <= last:
        for station in selected:
            cursor = day
            after = day + timedelta(days=1)
            while cursor < after:
                end = min(cursor + timedelta(minutes=window_minutes), after) - timedelta(minutes=1)
                station, begin, finish = validate_development_request(plan, station, cursor, end)
                yield station, begin, finish
                cursor = end + timedelta(minutes=1)
        day += timedelta(days=1)


def parse_observations(body, station, start, end):
    """스키마를 검사하고 미정의 정답은 결측으로 남긴다."""
    station = canonical_station_id(station)
    if station in PROTECTED_STATIONS:
        raise ValueError('Protected observations may not be parsed')
    schema = []
    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('#'):
            match = re.match(r'#\s*(\d+)\.\s*(\w+)\s*:', line)
            if match:
                schema.append((int(match.group(1)), match.group(2)))
            continue
        rows.append(next(csv.reader([line])) if ',' in line else line.split())
    schema.sort()
    columns = [name for _, name in schema]
    required = {'TM', 'STN_ID', 'LAT', 'LON', 'HT', 'SFS', 'TR1'}
    if not required <= set(columns) or len(columns) != len(set(columns)) or [i for i, _ in schema] != list(range(1, len(schema) + 1)):
        raise RwisResponseError('Missing or invalid official road-observation schema')
    if any(len(row) != len(columns) for row in rows):
        raise RwisResponseError('Unexpected road-observation field count')
    frame = pd.DataFrame(rows, columns=columns)
    if frame.empty:
        return pd.DataFrame(columns=['station', 'time', 'state_raw', 'road_temp', 'ice', 'lat', 'lon', 'elevation_m', *columns])
    frame['station'] = frame.STN_ID.map(canonical_station_id)
    if not frame.station.eq(station).all():
        raise RwisResponseError('Response contains an unrequested station')
    raw_rows = len(frame)
    missing_time = frame.TM.str.strip().isin(['', '0', '-999'])
    excluded_tokens = frame.loc[missing_time, 'TM'].str.strip().value_counts().to_dict()
    frame = frame.loc[~missing_time].copy()
    excluded = {'raw_response_rows': raw_rows, 'invalid_timestamp_rows_excluded': int(missing_time.sum()),
                'excluded_timestamp_token_counts': {str(k): int(v) for k, v in excluded_tokens.items()}}
    if frame.empty:
        result = pd.DataFrame(columns=['station', 'time', 'state_raw', 'road_temp', 'ice', 'lat', 'lon', 'elevation_m', *columns])
        result.attrs.update(excluded)
        return result
    try:
        frame['time'] = pd.to_datetime(frame.TM.str.strip(), format='%Y%m%d%H%M', errors='raise')
    except (ValueError, TypeError):
        raise RwisResponseError('Invalid KST observation timestamp') from None
    if not frame.time.between(pd.Timestamp(start), pd.Timestamp(end)).all():
        raise RwisResponseError('Response outside requested time interval')
    if frame.duplicated(['station', 'time']).any():
        raise RwisResponseError('Duplicate station/time returned')
    frame['state_raw'] = frame.SFS.str.strip()
    frame['ice'] = frame.state_raw.map(normalize_state).astype(float)
    for source, dest in [('TR1', 'road_temp'), ('LAT', 'lat'), ('LON', 'lon'), ('HT', 'elevation_m')]:
        values = pd.to_numeric(frame[source], errors='coerce')
        frame[dest] = values.mask(values.isin([-99.9, -99.2, -99.7, -999.]))
    if frame[['lat', 'lon']].isna().any().any() or not frame.lat.between(33, 39).all() or not frame.lon.between(124, 132).all():
        raise RwisResponseError('Invalid response coordinates')
    result = frame.sort_values(['station', 'time']).reset_index(drop=True)
    if excluded['invalid_timestamp_rows_excluded']:
        result.attrs.update(excluded)
    return result


def exact_ten_minute_grid(frame):
    if frame.empty:
        return frame.copy()
    return frame.loc[frame.time.dt.minute.mod(10).eq(0) & frame.time.dt.second.eq(0)].copy().reset_index(drop=True)
