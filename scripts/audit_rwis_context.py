"""Audit neighbor signal and fold-safe reference availability before fitting models."""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive, sha256_file
from src.observation_io import daily_members, read_columns
from src.rwis_context import add_source_history, select_reference, pair_context
from src.validation import PROTECTED_STATIONS, canonical_station_id, assert_training_stations, normalize_state, binary_metrics
from src.weather_features import _numeric_range


def main():
    private = ROOT / 'outputs/private'
    archive = competition_archive(ROOT)
    chunks = []
    with zipfile.ZipFile(archive) as zipped:
        for name in daily_members(zipped, 'RWIS'):
            part = read_columns(zipped, name,
                                ['관측시각 (KST)', '관측 지점번호', '고속도로', '노면상태', '노면온도 (광학)', '습도 (%)', '일 누적 강수량 (mm)'],
                                ['time', 'station', 'route', 'state_raw', 'road_temp', 'humidity', 'rain_cum'])
            part['station'] = part.station.map(canonical_station_id)
            part = part.loc[~part.station.isin(PROTECTED_STATIONS) & part.station.ne('<missing>')].copy()
            chunks.append(part)
    source = pd.concat(chunks, ignore_index=True)
    assert_training_stations(source.station.unique())
    source['time'] = pd.to_datetime(source.time, errors='raise')
    source['ice'] = source.state_raw.map(normalize_state)
    for col, lo, hi in [('road_temp', -60, 70), ('humidity', 0, 100), ('rain_cum', 0, 2000)]:
        _numeric_range(source, col, lo, hi)
    source = add_source_history(source)
    targets_path = private / 'ice_fallback_features/features.parquet'
    target = pd.read_parquet(targets_path, columns=['station', 'time', 'ice'])
    target['station'] = target.station.astype(str)
    assert_training_stations(target.station.unique())
    check = target.merge(source[['station', 'time', 'ice']], on=['station', 'time'],
                         how='outer', validate='one_to_one', indicator=True, suffixes=('_cache', '_raw'))
    if not check._merge.eq('both').all() or not check.ice_cache.equals(check.ice_raw):
        raise ValueError('Raw and cached development labels disagree')
    inventory = pd.read_csv(private / 'full/station_inventory.csv', dtype=str)
    inventory = inventory.loc[inventory.kind.eq('RWIS') & inventory.station_id.isin(target.station.unique())]
    meta = inventory.set_index('station_id')[['routes', 'latitudes', 'longitudes']].rename(
        columns={'routes': 'route', 'latitudes': 'lat', 'longitudes': 'lon'})
    meta[['lat', 'lon']] = meta[['lat', 'lon']].astype(float)
    available = source.groupby('station').agg(humidity=('humidity', 'count'), rain=('rain_10m', 'count'))
    meta['has_moisture'] = available.humidity.gt(0) | available.rain.gt(0)
    pair_cache = {}

    def get_pair(held, ref):
        key = (held, ref)
        if key not in pair_cache:
            left = target.loc[target.station.eq(held)].copy()
            right = source.loc[source.station.eq(ref)].copy()
            pair_cache[key] = pair_context(left, right, 'rwis')
        return pair_cache[key]

    outer_context, station_rows = [], []
    for held in sorted(target.station.unique()):
        ref, distance = select_reference(meta, held, {held})
        humidity_ref, humidity_distance = select_reference(meta, held, {held}, moisture=True)
        result = get_pair(held, ref).copy()
        result['source_station'] = ref
        result['source_distance_km'] = distance
        if humidity_ref:
            moisture = get_pair(held, humidity_ref).set_index('time')
            for col in ['humidity', 'rain_10m', 'source_time']:
                result['moisture_' + col] = result.time.map(moisture['rwis_' + col])
        else:
            result['moisture_humidity'] = np.nan
            result['moisture_rain_10m'] = np.nan
            result['moisture_source_time'] = pd.NaT
        result['moisture_station'] = humidity_ref
        result['moisture_distance_km'] = humidity_distance
        # Two fixed reference benchmarks, not model/threshold tuning.
        result['pred_neighbor_ice'] = result.rwis_ice.eq(1).astype(int)
        result['pred_neighbor_ice_60m'] = result.rwis_ice_seen_60m.eq(1).astype(int)
        positives = result.ice.eq(1)
        station_rows.append({'station': held, 'source_station': ref, 'distance_km': distance,
                             'moisture_station': humidity_ref, 'moisture_distance_km': humidity_distance,
                             'rows': len(result), 'ice_slots': int(positives.sum()),
                             'prior_state_available': int(result.rwis_ice.notna().sum()),
                             'ice_with_prior_state': int((positives & result.rwis_ice.notna()).sum()),
                             'prior_humidity_available': int(result.moisture_humidity.notna().sum()),
                             'ice_with_prior_humidity': int((positives & result.moisture_humidity.notna()).sum()),
                             'prior_rain_increment_available': int(result.moisture_rain_10m.notna().sum()),
                             'ice_with_prior_rain_increment': int((positives & result.moisture_rain_10m.notna()).sum()),
                             'prior_neighbor_ice_at_target_ice': int((positives & result.pred_neighbor_ice.eq(1)).sum()),
                             'prior_neighbor_ice60_at_target_ice': int((positives & result.pred_neighbor_ice_60m.eq(1)).sum())})
        outer_context.append(result)
    context = pd.concat(outer_context, ignore_index=True)
    valid = context.loc[context.ice.notna()]
    # Audit every training and validation target in every inner fold: all held sites excluded.
    splits = json.loads((private / 'validation/splits.json').read_text(encoding='utf-8'))
    reference_rows = []
    for outer in splits['outer_folds']:
        outer_held = outer['validation_station']
        for i, inner in enumerate(outer['inner_folds']):
            excluded = set(inner['stations']) | {outer_held}
            for held in outer['training_stations']:
                for kind in ['state', 'moisture']:
                    ref, distance = select_reference(meta, held, excluded, moisture=kind == 'moisture')
                    if ref and ref in excluded | {held}:
                        raise AssertionError('Excluded station selected as a reference')
                    joined = get_pair(held, ref) if ref else None
                    value = 'rwis_ice' if kind == 'state' else 'rwis_humidity'
                    reference_rows.append({'outer_held': outer_held, 'inner_fold': i,
                                           'target': held, 'target_role': 'validation' if held in excluded else 'training',
                                           'kind': kind, 'source_station': ref, 'distance_km': distance,
                                           'excluded_stations': ','.join(sorted(excluded)),
                                           'rows': int(target.station.eq(held).sum()),
                                           'available_rows': int(joined[value].notna().sum()) if ref else 0})
    refs = pd.DataFrame(reference_rows)
    strata = []
    for station, group in valid.groupby('station'):
        for field, flag in [('prior_ice', group.rwis_ice.eq(1)),
                            ('prior_ice60', group.rwis_ice_seen_60m.eq(1)),
                            ('humidity_ge90', group.moisture_humidity.ge(90)),
                            ('rain_increment_positive', group.moisture_rain_10m.gt(0))]:
            observed = {'prior_ice': group.rwis_ice.notna(), 'prior_ice60': group.rwis_ice_seen_60m.notna(),
                        'humidity_ge90': group.moisture_humidity.notna(), 'rain_increment_positive': group.moisture_rain_10m.notna()}[field]
            for label, mask in [('true', observed & flag), ('false', observed & ~flag), ('missing', ~observed)]:
                strata.append({'station': station, 'condition': field, 'stratum': label,
                               'rows': int(mask.sum()), 'ice_slots': int(group.loc[mask, 'ice'].sum())})
    source_config = json.loads((ROOT / 'config/data_source.json').read_text(encoding='utf-8'))
    summary = {'status': 'development_only_prior_neighbor_context_audit',
               'data_release': source_config['release'], 'archive_sha256': source_config['sha256'],
               'target_rows': len(context), 'valid_labels': len(valid), 'ice_slots': int(valid.ice.sum()),
               'source_metadata_policy': 'same route, nearest allowed station; moisture capability inferred from nonmissing sensor values without Ice labels',
               'prior_age_cap_minutes': 30, 'history_window': '60 minutes including source timestamp; source strictly before target',
               'fixed_latest_ice_benchmark': binary_metrics(valid.ice.astype(int), valid.pred_neighbor_ice),
               'fixed_past60_ice_benchmark': binary_metrics(valid.ice.astype(int), valid.pred_neighbor_ice_60m),
               'outer_station_totals': {k: int(pd.DataFrame(station_rows)[k].sum()) for k in
                                        ['prior_state_available', 'ice_with_prior_state', 'prior_humidity_available',
                                         'ice_with_prior_humidity', 'prior_rain_increment_available', 'ice_with_prior_rain_increment']},
               'inner_reference_checks': len(refs),
               'inner_missing_reference_cases': refs.loc[refs.source_station.isna()].groupby('kind').size().to_dict(),
               'cached_pairs': len(pair_cache), 'feature_source_sha256': sha256_file(targets_path),
               'limitations': ['Descriptive signal audit, not learned model or final performance.',
                               'Missing reference is retained as missing; fixed benchmarks use no-alarm fallback.',
                               'Exclusion can leave no same-route moisture station; no cross-route substitution.',
                               'Prior source timestamps do not establish operational publication latency.',
                               'No target self-history or protected station is used. Old data requires rerun.']}
    out = private / 'rwis_context'
    out.mkdir(parents=True, exist_ok=True)
    context.to_parquet(out / 'outer_context.parquet', index=False, compression='zstd')
    pd.DataFrame(station_rows).to_csv(out / 'station_coverage.csv', index=False, encoding='utf-8-sig')
    refs.to_csv(out / 'inner_reference_audit.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(strata).to_csv(out / 'condition_exposure.csv', index=False, encoding='utf-8-sig')
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
