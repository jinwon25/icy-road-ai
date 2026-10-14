"""호남 2곳 평균 후보의 원문·예측·사전 온도/결빙 조건을 별도 검산한다."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.fresh_station_validation import old_freezes, verify_seal
from scripts.audit_temperature_blind_validation import (
    read, reference_observations, reference_temperature, reference_ice, counts, compare,
)


def temperature_gate(base, candidate, near_base, near_candidate):
    """없는 지점·빈 저온 분모로 통과하지 않으며 지점 손실 상한을 유지한다."""
    if set(base['stations']) != set(candidate['stations']):
        raise ValueError('Station denominators differ')
    for station, values in base['stations'].items():
        if values['n'] != candidate['stations'][station]['n']:
            raise ValueError('Temperature denominators differ')
    if near_base['pooled']['n'] != near_candidate['pooled']['n']:
        raise ValueError('Near-freezing denominators differ')
    if not base['stations'] or any(r['n'] == 0 for r in base['stations'].values()):
        return False
    if near_base['pooled']['n'] == 0:
        return False
    return bool(
        all(candidate['station_macro'][k] < base['station_macro'][k] for k in ['mae', 'rmse'])
        and all(candidate['stations'][s]['mae'] <= r['mae'] * 1.05 for s, r in base['stations'].items())
        and near_candidate['pooled']['mae'] <= near_base['pooled']['mae']
    )


def ice_gate(frame, baseline='thermal_weather14', candidate='thermal_equal_mean'):
    """수집 전에 정한 결빙 기준을 적용한다. 양성이 없으면 입증 불가이다."""
    base, proposed = reference_ice(frame, baseline), reference_ice(frame, candidate)
    if base['tp'] + base['fn'] == 0:
        return dict(status='not_estimable_without_positive_ice', passed=False, checks={}, positive_stations=[])
    def nonworse_defined(key):
        return base[key] is not None and proposed[key] is not None and proposed[key] >= base[key]
    positive = [str(s) for s, p in frame.groupby('station') if p.ice.eq(1).any()]
    recall_ok = all(counts(p, candidate)['recall'] >= counts(p, baseline)['recall']
                    for _, p in frame.groupby('station') if p.ice.eq(1).any())
    checks = dict(false_positives_nonincreasing=proposed['fp'] <= base['fp'],
                  false_negatives_nonincreasing=proposed['fn'] <= base['fn'],
                  daily_f1_nonworse=nonworse_defined('provisional_daily_station_f1'),
                  actual_ice_day_f1_nonworse=nonworse_defined('fixed_ice_day_f1'),
                  each_positive_station_recall_nonworse=bool(recall_ok),
                  single_slot_detection_nonworse=proposed['detected_single_slot_events'] >= base['detected_single_slot_events'])
    return dict(status='evaluated', passed=all(checks.values()), checks=checks, positive_stations=positive)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, default=ROOT / 'outputs/private/temperature_mean_blind_20261010_v1')
    out = parser.parse_args().experiment.resolve()
    if not out.is_relative_to((ROOT / 'outputs/private').resolve()):
        raise ValueError('Private experiment required')
    target = out / 'independent_verification.json'
    if target.exists():
        raise FileExistsError('Preserve once-opened audit')
    seal = verify_seal(out)
    audit, summary, manifest, plan = [read(out / n) for n in
        ['prediction_audit.json', 'summary.json', 'download_manifest.json', 'plan.json']]
    chronology = [seal['sealed_at_utc'], audit['audited_at_utc'], manifest['first_request_utc'],
                  manifest['completed_at_utc'], summary['evaluated_at_utc']]
    times = list(map(datetime.fromisoformat, chronology))
    if not all(a < b for a, b in zip(times, times[1:])):
        raise ValueError('Seal/audit/request/evaluation order differs')
    if (seal['new_outcomes_present_at_seal'] is not False or audit['new_outcomes_present'] is not False
            or audit['status'] != 'passed' or manifest['status'] != 'complete'):
        raise ValueError('Incomplete pre-request isolation')
    for entry in [audit, summary]:
        if entry['seal_sha256'] != sha(out / 'prediction_seal.json'):
            raise ValueError('Seal reference differs')
    if summary['evaluation_sha256'] != sha(out / 'evaluation.parquet'):
        raise ValueError('Evaluation changed')
    stations = sorted(s for group in plan['station_groups'].values() for s in group)
    if stations != ['23102', '23407'] or set(stations) & set(plan['competition_stations_excluded_from_external_requests']):
        raise ValueError('New validation domain differs')
    if plan['weights'] != [.5, .5] or plan['development_start_kst'] != '2024-11-01' or plan['development_end_kst'] != '2025-02-28':
        raise ValueError('Predeclared candidate or period differs')
    design_dir = ROOT / 'outputs/private/temperature_mean_validation_design_20261010_v1'
    design = read(design_dir / 'design_receipt.json')
    if (design['outcomes_read'] is not False or sorted(design['selected_stations']) != stations
            or datetime.fromisoformat(design['created_at_utc']) >= times[0]
            or sha(design_dir / 'metadata_screen.csv') != design['screen_sha256']):
        raise ValueError('Metadata-only selection order differs')
    for name, digest in {**design['request_manifest_signatures'], **design['static_source_signatures']}.items():
        if sha(ROOT / name) != digest:
            raise ValueError('Pre-selection evidence changed')
    for name in design['request_manifest_signatures']:
        previous = read(ROOT / name)
        if any(record['station'] in stations for record in previous['records'].values()):
            raise ValueError('Selected validation station previously requested')
    grid = pd.date_range('2024-11-01', '2025-03-01', freq='10min', inclusive='left')
    q = pd.read_parquet(out / 'predictions.parquet')
    if sorted(q.station.unique()) != stations or len(q) != len(grid) * len(stations) or q.duplicated(['station', 'time']).any():
        raise ValueError('Prediction grid differs')
    for _, part in q.groupby('station'):
        if not pd.DatetimeIndex(part.time).equals(grid):
            raise ValueError('Missing planned slot')
    expected_requests = {f'{s}_{d:%Y%m%d}0000' for s in stations for d in pd.date_range(grid.min().normalize(), grid.max().normalize())}
    if set(manifest['records']) != expected_requests:
        raise ValueError('Full daily request domain differs')
    observations, raw_count = [], 0
    for name, record in manifest['records'].items():
        start, end = pd.Timestamp(record['start_kst']), pd.Timestamp(record['end_kst'])
        if (record['station'] not in stations or name != f"{record['station']}_{start:%Y%m%d%H%M}"
                or start != start.normalize() or end != start + pd.Timedelta(hours=23, minutes=59)):
            raise ValueError('Daily request window differs')
        file = out / 'observations' / (name + '.parquet')
        if sha(file) != record['sha256']:
            raise ValueError('Observation changed')
        parts = []
        for receipt in record['transport']:
            raw = (out / 'transport' / receipt['transport_cache_path']).resolve()
            if not raw.is_relative_to(out / 'transport') or sha(raw) != receipt['transport_response_sha256']:
                raise ValueError('Transport response changed')
            parts.append(reference_observations(raw.read_text(encoding='utf-8'), record['station'], start, end))
            raw_count += 1
        observed = pd.concat(parts).sort_values('time').reset_index(drop=True)
        saved = pd.read_parquet(file)
        pd.testing.assert_frame_equal(observed, saved[observed.columns].reset_index(drop=True), check_dtype=False)
        if len(saved) != record['rows']:
            raise ValueError('Observation row count differs')
        observations.append(observed)
    observed = pd.concat(observations, ignore_index=True)
    if observed.duplicated(['station', 'time']).any():
        raise ValueError('Duplicate observations')
    frame = q.merge(observed, on=['station', 'time'], how='left', validate='one_to_one', indicator=True)
    saved = pd.read_parquet(out / 'evaluation.parquet')
    pd.testing.assert_frame_equal(frame, saved[frame.columns], check_dtype=False)
    points = pd.read_csv(out / 'points.csv', dtype={'station': str}).set_index('station')
    coordinate_checks = []
    for station, part in observed.groupby('station'):
        lat, lon = points.loc[station, ['lat', 'lon']].astype(float)
        pairs = part[['lat', 'lon']].drop_duplicates()
        a, b = np.radians(pairs.lat.to_numpy()), np.radians(pairs.lon.to_numpy())
        h = np.sin((a - np.radians(lat))/2)**2 + np.cos(a)*np.cos(np.radians(lat))*np.sin((b - np.radians(lon))/2)**2
        distances = 6371008.8 * 2 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))
        delta = float((pairs - [lat, lon]).abs().max().max())
        coordinate_checks.append(dict(station=station, catalogue_lat=lat, catalogue_lon=lon,
            response_coordinates=pairs.to_dict('records'), maximum_distance_m=float(distances.max()),
            maximum_difference_degrees=delta, within_rounding_tolerance=delta <= .00011))
    coordinates_verified = len(coordinate_checks) == len(stations) and all(c['within_rounding_tolerance'] for c in coordinate_checks)
    intervals = []
    for run in sorted(out.glob('collection_run_*')):
        receipt = read(run / 'receipt.json'); path = run / 'request_start_intervals.json'
        if (receipt['status'] != 'complete' or receipt['prediction_seal_sha256'] != sha(out / 'prediction_seal.json')
                or sha(path) != receipt['request_start_intervals_sha256'] or sha(run / 'collector_source.py') != receipt['source_sha256']):
            raise ValueError('Collection receipt changed or incomplete')
        intervals += read(path)
    if not intervals or len(intervals) + 1 < 2 * raw_count - len(expected_requests) or min(intervals) < plan['minimum_request_interval_seconds']:
        raise ValueError('Global request interval not verified')
    with threadpool_limits(limits=2):
        for fit in read(out / 'fit_receipts.json'):
            excluded = {'12410', '33411', '23402', *stations, '12104', '12206', '12212', '12407', '23206', '23406', '33209', '33415', '12406', '23405', '33407', '33416'}
            if excluded & set(fit['training_stations']) or sha(out / (fit['name']+'.joblib')) != fit['model_sha256']:
                raise ValueError('Excluded target in training or model changed')
            model = joblib.load(out / (fit['name']+'.joblib'))
            for station, part in q.groupby('station'):
                inputs = pd.read_parquet(out / f'inputs_{station}.parquet')
                if {'road_temp', 'ice', 'state_raw'} & set(inputs):
                    raise ValueError('Outcome in inference inputs')
                pd.testing.assert_frame_equal(part[['station', 'time']].reset_index(drop=True), inputs[['station', 'time']], check_dtype=False)
                expected = np.where(inputs.asos_air_temp.notna(), model.predict(inputs[fit['features']]), np.nan)
                np.testing.assert_allclose(part[fit['name']], expected, rtol=0, atol=0, equal_nan=True)
        source = ROOT / 'outputs/private/releases/20261007/outputs/private/external_augmentation_nested_v1/baseline'
        ice_info = read(source / 'fit_manifest.json'); ice_model = joblib.load(source / 'model.joblib')
        for station, part in q.groupby('station'):
            inputs = pd.read_parquet(out / f'inputs_{station}.parquet')
            np.testing.assert_array_equal(np.isfinite(part.weather14), np.isfinite(part.weather12))
            np.testing.assert_allclose(part.equal_mean, .5*part.weather14 + .5*part.weather12, rtol=0, atol=0, equal_nan=True)
            probability = ice_model.predict_proba(inputs[ice_info['features']])[:, 1]
            np.testing.assert_allclose(part.original_ice_score, probability, rtol=0, atol=0)
            np.testing.assert_array_equal(part.original_ice, probability >= ice_info['threshold'])
            water = inputs[['aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']].to_numpy()
            for name in ['weather14', 'equal_mean']:
                t = part[name].to_numpy()
                fallback = ~np.isfinite(t) | np.isnan(water).all(axis=1)
                rule = ((t <= 0) & ((water[:, 0] >= t) | (water[:, 1] > 0) | (water[:, 2] > 0))).astype(int)
                rule[fallback] = part.original_ice.to_numpy()[fallback]
                np.testing.assert_array_equal(part['thermal_'+name], rule)
    for policy in plan['frozen_ice_policies']:
        compare(reference_ice(frame, policy), summary['ice_metrics'][policy])
    finite = np.isfinite(frame.road_temp) & np.isfinite(frame.weather14) & np.isfinite(frame.equal_mean)
    temperatures = {name: reference_temperature(frame, name) for name in plan['temperature_comparison']}
    near = {name: reference_temperature(frame.loc[finite & frame.road_temp.between(-2, 2)], name) for name in temperatures}
    for name in temperatures:
        compare(temperatures[name], summary['temperature'][name]); compare(near[name], summary['near_freezing'][name])
    gate = temperature_gate(temperatures['weather14'], temperatures['equal_mean'], near['weather14'], near['equal_mean'])
    if gate != summary['temperature_primary_gate_passed']:
        raise ValueError('Predeclared temperature gate differs')
    coverage = [dict(station=str(s), planned_rows=len(p), received_rows=int(p._merge.eq('both').sum()),
        valid_temperature=int((np.isfinite(p.road_temp) & np.isfinite(p.equal_mean)).sum()),
        defined_state_rows=int(p.ice.isin([0, 1]).sum()), ice_rows=int(p.ice.eq(1).sum())) for s, p in frame.groupby('station')]
    if coverage != summary['coverage']:
        raise ValueError('Coverage differs')
    if old_freezes() != (seal['original_frozen_files'], seal['reserved_frozen_files']):
        raise ValueError('Existing frozen files changed')
    for old in ['fresh_station_validation_20261009_v2', 'temperature_blind_20261010_v1']:
        path = ROOT / 'outputs/private' / old
        verify_seal(path)
    result = dict(status='independent_equal_mean_blind_audit_passed' if coordinates_verified else 'independent_metrics_passed_location_review_required',
        audited_at_utc=datetime.now(timezone.utc).isoformat(), chronology_utc=chronology,
        observations=len(observed), prediction_rows=len(q), checked_component_predictions=len(q)*2,
        checked_mean_predictions=len(q), planned_daily_requests=len(expected_requests), raw_transport_responses=raw_count,
        request_attempts=len(intervals)+1, minimum_request_interval_seconds=min(intervals),
        interval_below_plan_count=sum(x < plan['minimum_request_interval_seconds'] for x in intervals),
        coordinates_verified=coordinates_verified, coordinate_checks=coordinate_checks,
        temperature_primary_gate_passed=bool(gate), ice_gate=ice_gate(frame), candidate_promoted=False,
        no_retraining_or_reselection=True, protected_or_future_outcomes_used=False,
        summary_sha256=sha(out / 'summary.json'), auditor_sha256=sha(__file__),
        original_frozen_files=seal['original_frozen_files'], reserved_frozen_files=seal['reserved_frozen_files'])
    with target.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False); handle.write('\n')
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
