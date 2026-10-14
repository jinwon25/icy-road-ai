"""새 4개 지점의 원문·시간 순서·온도/일별/사건 지표를 별도 계산으로 검산한다."""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.fresh_station_validation import old_freezes


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def reference_observations(body, station, start, end):
    """학습/수집 파서를 호출하지 않고 공식 열과 정시 10분 표본을 대조한다."""
    headers, rows = [], []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('#'):
            match = re.match(r'#\s*(\d+)\.\s*(\w+)\s*:', line)
            if match:
                headers.append((int(match[1]), match[2]))
        else:
            rows.append(next(csv.reader([line])) if ',' in line else line.split())
    headers.sort()
    if [i for i, _ in headers] != list(range(1, len(headers) + 1)):
        raise ValueError('Non-contiguous response schema')
    columns = [name for _, name in headers]
    if len(set(columns)) != len(columns) or not {'TM', 'STN_ID', 'SFS', 'TR1', 'LAT', 'LON'} <= set(columns):
        raise ValueError('Invalid response schema')
    if any(len(row) != len(columns) for row in rows):
        raise ValueError('Response field count differs')
    raw = pd.DataFrame(rows, columns=columns)
    if not raw.STN_ID.str.strip().eq(station).all():
        raise ValueError('Unrequested station')
    raw = raw.loc[~raw.TM.str.strip().isin(['', '0', '-999'])].copy()
    raw['time'] = pd.to_datetime(raw.TM.str.strip(), format='%Y%m%d%H%M', errors='raise')
    if not raw.time.between(start, end).all() or raw.time.duplicated().any():
        raise ValueError('Unrequested or duplicate timestamp')
    raw = raw.loc[raw.time.dt.minute.mod(10).eq(0)].copy()
    result = pd.DataFrame({'station': station, 'time': raw.time, 'state_raw': raw.SFS.str.strip()})
    state = pd.to_numeric(raw.SFS, errors='raise')
    result['ice'] = np.where(state.eq(4), 1., np.where(state.isin([1, 2, 3, 10, 11, 12, 13, 14, 15]), 0., np.nan))
    for source, dest in [('TR1', 'road_temp'), ('LAT', 'lat'), ('LON', 'lon')]:
        values = pd.to_numeric(raw[source], errors='coerce')
        result[dest] = values.mask(values.isin([-99.9, -99.2, -99.7, -999.]))
    return result.sort_values('time').reset_index(drop=True)


def counts(part, policy):
    valid = part.loc[part.ice.isin([0, 1])]
    totals = {(y, p): int((valid.ice.eq(y) & valid[policy].eq(p)).sum()) for y in [0, 1] for p in [0, 1]}
    tp, fp, fn, tn = totals[1, 1], totals[0, 1], totals[1, 0], totals[0, 0]
    return dict(n=len(valid), tp=tp, fp=fp, fn=fn, tn=tn,
                precision=tp / (tp + fp) if tp + fp else None,
                recall=tp / (tp + fn) if tp + fn else None,
                f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
                fpr=fp / (fp + tn) if fp + tn else None)


def defined_mean(values):
    values = [x for x in values if x is not None]
    return float(sum(values) / len(values)) if values else None


def reference_ice(frame, policy):
    """일별 분모·실제 결빙일과 10분 연속 사건을 직접 계산한다."""
    if not frame[policy].isin([0, 1]).all():
        raise ValueError('Incomplete binary predictions')
    result = counts(frame, policy)
    daily_by_station, ice_by_station, station_f1 = [], [], []
    complete, false_days, ice_days, events, detected, singles, detected_singles = [0] * 7
    for _, station in frame.groupby('station'):
        station_f1.append(counts(station, policy)['f1'])
        days, iced = [], []
        for _, day in station.groupby(station.time.dt.date):
            if len(day) != 144 or not day.ice.isin([0, 1]).all():
                continue
            complete += 1
            metric = counts(day, policy)
            days.append(metric['f1'])
            if metric['tp'] + metric['fn']:
                ice_days += 1
                iced.append(metric['f1'])
            elif metric['fp']:
                false_days += 1
        daily_by_station.append(defined_mean(days))
        ice_by_station.append(defined_mean(iced))
        episode, previous = [], None
        def close(rows):
            if not rows:
                return (0, 0, 0, 0)
            hit = any(getattr(row, policy) == 1 for row in rows)
            return (1, int(hit), int(len(rows) == 1), int(hit and len(rows) == 1))
        for row in station.sort_values('time').itertuples():
            if row.ice != 1 or (previous is not None and row.time - previous != pd.Timedelta(minutes=10)):
                e, d, s, ds = close(episode)
                events += e; detected += d; singles += s; detected_singles += ds
                episode = []
            if row.ice == 1:
                episode.append(row)
            previous = row.time
        e, d, s, ds = close(episode)
        events += e; detected += d; singles += s; detected_singles += ds
    result.update(fixed_station_f1_zero_undefined=float(np.mean([x or 0 for x in station_f1])),
                  fixed_ice_day_f1=defined_mean(ice_by_station), fixed_ice_days=ice_days,
                  fixed_ice_day_stations=sum(x is not None for x in ice_by_station), complete_days=complete,
                  false_alarm_nonice_days=false_days, provisional_daily_station_f1=defined_mean(daily_by_station),
                  events=events, detected_events=detected, single_slot_events=singles,
                  detected_single_slot_events=detected_singles)
    return result


def reference_temperature(frame, column):
    def one(part):
        errors = [float(p) - float(y) for y, p in zip(part.road_temp, part[column], strict=True)
                  if np.isfinite(y) and np.isfinite(p)]
        n = len(errors)
        return dict(n=n, mae=sum(map(abs, errors)) / n if n else None,
                    rmse=(sum(e * e for e in errors) / n) ** .5 if n else None,
                    bias=sum(errors) / n if n else None)
    stations = {str(s): one(part) for s, part in frame.groupby('station')}
    return dict(pooled=one(frame), stations=stations, stations_with_valid_temperature=sum(r['n'] > 0 for r in stations.values()),
                station_macro={k: defined_mean([r[k] for r in stations.values()]) for k in ['mae', 'rmse', 'bias']})


def compare(actual, expected):
    if isinstance(expected, dict):
        if set(actual) != set(expected):
            raise ValueError('Metric keys differ')
        for k in expected:
            compare(actual[k], expected[k])
    elif expected is None:
        if actual is not None:
            raise ValueError('Undefined metric differs')
    else:
        np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, default=ROOT / 'outputs/private/temperature_blind_20261010_v1')
    out = parser.parse_args().experiment.resolve()
    if not out.is_relative_to((ROOT / 'outputs/private').resolve()):
        raise ValueError('Private experiment required')
    target = out / 'independent_verification.json'
    if target.exists():
        raise FileExistsError('Preserve previous independent audit')
    seal, audit, summary, manifest = [read(out / name) for name in
        ['prediction_seal.json', 'prediction_audit.json', 'summary.json', 'download_manifest.json']]
    chronology = [seal['sealed_at_utc'], audit['audited_at_utc'], manifest['first_request_utc'],
                  manifest['completed_at_utc'], summary['evaluated_at_utc']]
    times = list(map(datetime.fromisoformat, chronology))
    if not all(a < b for a, b in zip(times, times[1:])) or seal['new_outcomes_present_at_seal'] is not False:
        raise ValueError('Seal/audit/request/evaluation chronology differs')
    if audit['new_outcomes_present'] is not False or audit['status'] != 'passed' or manifest['status'] != 'complete':
        raise ValueError('Incomplete pre-request audit or collection')
    for rel, digest in seal['files'].items():
        path = (out / rel).resolve()
        if not path.is_relative_to(out) or sha(path) != digest:
            raise ValueError('Sealed evidence changed')
    for entry in read(out / 'input_signature.json').values():
        if sha(entry['path']) != entry['sha256']:
            raise ValueError('Source input changed')
    for entry in [audit, summary]:
        if entry['seal_sha256'] != sha(out / 'prediction_seal.json'):
            raise ValueError('Seal reference differs')
    if summary['evaluation_sha256'] != sha(out / 'evaluation.parquet'):
        raise ValueError('Evaluation changed')
    plan = read(out / 'plan.json')
    stations = sorted(s for group in plan['station_groups'].values() for s in group)
    grid = pd.date_range(plan['development_start_kst'], pd.Timestamp(plan['development_end_kst']) + pd.Timedelta(days=1), freq='10min', inclusive='left')
    q = pd.read_parquet(out / 'predictions.parquet')
    if sorted(q.station.unique()) != stations or q.duplicated(['station', 'time']).any() or len(q) != len(grid) * len(stations):
        raise ValueError('Prediction domain differs')
    for _, part in q.groupby('station'):
        if not pd.DatetimeIndex(part.time).equals(grid):
            raise ValueError('Planned slot missing')
    expected_requests = {f'{s}_{d:%Y%m%d}0000' for s in stations for d in pd.date_range(grid.min().normalize(), grid.max().normalize())}
    if set(manifest['records']) != expected_requests:
        raise ValueError('Requested daily windows differ')
    observations = []
    validated_transport_count = 0
    for name, record in manifest['records'].items():
        file = out / 'observations' / (name + '.parquet')
        if sha(file) != record['sha256'] or record['station'] not in stations:
            raise ValueError('Observation changed')
        raw_parts = []
        for receipt in record['transport']:
            validated_transport_count += 1
            raw = (out / 'transport' / receipt['transport_cache_path']).resolve()
            if not raw.is_relative_to(out / 'transport') or sha(raw) != receipt['transport_response_sha256']:
                raise ValueError('Transport response changed')
            raw_parts.append(reference_observations(raw.read_text(encoding='utf-8'), record['station'],
                                                   pd.Timestamp(record['start_kst']), pd.Timestamp(record['end_kst'])))
        observed = pd.concat(raw_parts).sort_values('time').reset_index(drop=True)
        saved = pd.read_parquet(file)
        pd.testing.assert_frame_equal(observed, saved[observed.columns].reset_index(drop=True), check_dtype=False)
        if len(saved) != record['rows']:
            raise ValueError('Manifest row count differs')
        observations.append(observed)
    observed = pd.concat(observations, ignore_index=True)
    if observed.duplicated(['station', 'time']).any():
        raise ValueError('Duplicate observations')
    frame = q.merge(observed, on=['station', 'time'], how='left', validate='one_to_one')
    saved = pd.read_parquet(out / 'evaluation.parquet')
    pd.testing.assert_frame_equal(frame, saved[frame.columns], check_dtype=False)
    points = pd.read_csv(out / 'points.csv', dtype={'station': str}).set_index('station')
    coordinate_checks = []
    for station, part in observed.groupby('station'):
        lat, lon = points.loc[station, ['lat', 'lon']].astype(float)
        pairs = part[['lat', 'lon']].drop_duplicates()
        delta = float((pairs - [lat, lon]).abs().max().max())
        a = np.radians(pairs.lat.to_numpy()); b = np.radians(pairs.lon.to_numpy())
        h = np.sin((a - np.radians(lat)) / 2) ** 2 + np.cos(a) * np.cos(np.radians(lat)) * np.sin((b - np.radians(lon)) / 2) ** 2
        distances = 6371008.8 * 2 * np.arcsin(np.sqrt(h))
        coordinate_checks.append(dict(station=station, catalogue_lat=lat, catalogue_lon=lon,
                                      response_coordinates=pairs.to_dict('records'), maximum_distance_m=float(distances.max()),
                                      maximum_difference_degrees=delta, within_rounding_tolerance=delta <= .00011))
    maximum_coordinate_error = max(c['maximum_difference_degrees'] for c in coordinate_checks)
    # 지점 ID·원문·지표 검증과 물리적 위치 검증을 구분한다. 사후 좌표 변경은 금지한다.
    coordinates_verified = all(c['within_rounding_tolerance'] for c in coordinate_checks)
    intervals = []
    for run in sorted(out.glob('collection_run_*')):
        receipt = read(run / 'receipt.json')
        path = run / 'request_start_intervals.json'
        if receipt['status'] != 'complete' or receipt['prediction_seal_sha256'] != sha(out / 'prediction_seal.json') or sha(path) != receipt['request_start_intervals_sha256']:
            raise ValueError('Incomplete collection receipt')
        if sha(run / 'collector_source.py') != receipt['source_sha256']:
            raise ValueError('Collector snapshot changed')
        intervals += read(path)
    # 큰 구간의 실패를 둘로 나눈 부모 요청도 공유 타이머에 기록된다.
    minimum_attempts = 2 * validated_transport_count - len(expected_requests)
    if len(intervals) + 1 < minimum_attempts or min(intervals) < plan['minimum_request_interval_seconds']:
        raise ValueError('Global minimum request interval not verified')
    receipts = read(out / 'fit_receipts.json')
    with threadpool_limits(limits=2):
        for fit in receipts:
            if set(stations) & set(fit['training_stations']) or {'12410', '33411', '23402'} & set(fit['training_stations']):
                raise ValueError('New/protected targets in training')
            model = joblib.load(out / (fit['name'] + '.joblib'))
            for station, part in q.groupby('station'):
                inputs = pd.read_parquet(out / f'inputs_{station}.parquet')
                p = np.where(inputs.asos_air_temp.notna(), model.predict(inputs[fit['features']]), np.nan)
                np.testing.assert_allclose(p, part[fit['name']], rtol=0, atol=0, equal_nan=True)
                water = inputs[['aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']].to_numpy()
                wet = (water[:, 0] >= p) | (water[:, 1] > 0) | (water[:, 2] > 0)
                ruled = np.where(~np.isfinite(p) | np.isnan(water).all(axis=1), part.original_ice, ((p <= 0) & wet).astype(int))
                np.testing.assert_array_equal(ruled, part['thermal_hgb' + fit['name'][-3:]])
    for policy in plan['frozen_ice_policies']:
        compare(reference_ice(frame, policy), summary['ice_metrics'][policy])
    for name in plan['temperature_comparison']:
        compare(reference_temperature(frame, name), summary['temperature'][name])
        compare(reference_temperature(frame.loc[frame.road_temp.between(-2, 2)], name), summary['near_freezing'][name])
    base, candidate = [summary['temperature'][name] for name in ['weather_hgb100', 'weather_hgb300']]
    gate = all(candidate['station_macro'][k] < base['station_macro'][k] for k in ['mae', 'rmse']) and all(
        candidate['stations'][s]['mae'] <= r['mae'] * 1.05 for s, r in base['stations'].items() if r['n'])
    if gate != summary['temperature_primary_gate_passed']:
        raise ValueError('Predeclared primary gate differs')
    coverage = [dict(station=str(s), planned_rows=len(part), received_rows=int(part.state_raw.notna().sum()),
                     defined_state_rows=int(part.ice.isin([0, 1]).sum()), ice_rows=int(part.ice.eq(1).sum()))
                for s, part in frame.groupby('station')]
    if coverage != summary['coverage']:
        raise ValueError('Coverage differs')
    if old_freezes() != (seal['original_frozen_files'], seal['reserved_frozen_files']):
        raise ValueError('Existing frozen assessments changed')
    result = dict(status='independent_blind_metrics_passed_location_review_required' if not coordinates_verified else 'independent_blind_audit_passed',
                  audited_at_utc=datetime.now(timezone.utc).isoformat(),
                  observations=len(observed), prediction_rows=len(q), checked_temperature_predictions=len(q) * 2,
                  planned_daily_requests=len(manifest['records']), raw_transport_responses=validated_transport_count,
                  request_attempts=len(intervals) + 1, request_intervals=len(intervals),
                  attempts_without_saved_response=len(intervals) + 1 - validated_transport_count,
                  minimum_request_interval_seconds=min(intervals), interval_below_plan_count=sum(x < plan['minimum_request_interval_seconds'] for x in intervals),
                  maximum_coordinate_difference_degrees=maximum_coordinate_error,
                  coordinates_verified=coordinates_verified, coordinate_checks=coordinate_checks,
                  chronology_utc=chronology, temperature_primary_gate_passed=summary['temperature_primary_gate_passed'],
                  no_retraining_or_reselection=True, summary_sha256=sha(out / 'summary.json'), auditor_sha256=sha(__file__),
                  original_frozen_files=seal['original_frozen_files'], reserved_frozen_files=seal['reserved_frozen_files'])
    with target.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
