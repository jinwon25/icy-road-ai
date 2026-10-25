"""수집 응답의 결측·중복 유형을 분류한다. 정답 선택·복구에는 사용하지 않는다."""
import csv
import re
from collections import Counter, defaultdict
import pandas as pd
from src.validation import canonical_station_id, PROTECTED_STATIONS, normalize_state


def tokens(body, station):
    station = canonical_station_id(station)
    if station in PROTECTED_STATIONS:
        raise ValueError('Protected station forbidden')
    schema, rows = [], []
    for line in body.splitlines():
        if not line.strip():
            continue
        if line.lstrip().startswith('#'):
            m = re.match(r'#\s*(\d+)\.\s*(\w+)\s*:', line.strip())
            if m:
                schema.append((int(m[1]), m[2]))
        else:
            rows.append([x.strip() for x in (next(csv.reader([line])) if ',' in line else line.split())])
    schema.sort()
    cols = [n for _, n in schema]
    if not {'TM', 'STN_ID', 'SFS'} <= set(cols) or len(cols) != len(set(cols)) or [i for i, _ in schema] != list(range(1, len(cols)+1)):
        raise ValueError('Invalid schema')
    if any(len(r) != len(cols) or canonical_station_id(r[cols.index('STN_ID')]) != station for r in rows):
        raise ValueError('Unexpected row or station')
    return cols, rows


def response_profile(body, station, start, end):
    cols, rows = tokens(body, station)
    ti, si = cols.index('TM'), cols.index('SFS')
    groups = defaultdict(list)
    invalid_times = Counter()
    for row in rows:
        if row[ti] in ['', '0', '-999']:
            invalid_times[row[ti]] += 1
        else:
            moment = pd.to_datetime(row[ti], format='%Y%m%d%H%M')
            if not pd.Timestamp(start) <= moment <= pd.Timestamp(end):
                raise ValueError('Response outside requested interval')
            groups[row[ti]].append(tuple(row))
    pairs, fields, conflicts, identical, ten = Counter(), Counter(), [], 0, {}
    for token, group in groups.items():
        unique = set(group)
        if len(unique) > 1:
            pairs['|'.join(sorted(set(r[si] for r in group)))] += 1
            changed = [cols[j] for j in range(len(cols)) if len(set(r[j] for r in group)) > 1]
            fields.update(changed)
            conflicts.append(token)
            category = 'conflict_quarantine'
        else:
            identical += len(group)-1
            value = normalize_state(group[0][si])
            category = 'valid_label' if value in (0, 1) else 'invalid_state'
        if pd.Timestamp(token).minute % 10 == 0:
            ten[token] = category
    return dict(raw_rows=len(rows), unique_valid_timestamps=len(groups), invalid_timestamp_tokens=dict(invalid_times),
        conflicting_minutes=len(conflicts), conflicting_state_pairs=dict(pairs), differing_fields=dict(fields),
        identical_duplicate_rows=identical, ten_minute_categories=ten, conflict_tokens=conflicts)
