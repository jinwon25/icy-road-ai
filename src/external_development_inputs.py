"""첫 겨울 외부 위치의 입력만 미리 계산하고 원천·소스 서명을 검증한다."""
import json
from pathlib import Path

import pandas as pd

from src.data_source import sha256_file
from src.point_inputs import PointInputBuilder
from src.validation import assert_training_stations

TARGET_COLUMNS = {'ice', 'state_raw', 'road_temp', 'spatial_group'}
CACHE_RELATIVE = 'outputs/private/external_development_inputs_v1'


def input_signature(root):
    root = Path(root)
    files = [
        'config/kma_external_validation_plan.json',
        'outputs/private/sensor_availability/metadata.csv',
        'outputs/private/external/kma_rwis_reference/station_catalog.csv',
        'src/external_development_inputs.py', 'src/point_inputs.py',
        'src/physical_features.py', 'src/moisture_memory.py',
        'src/weather_features.py', 'src/validation.py',
        'scripts/audit_ice_weather_history.py', 'scripts/baseline_ice_logistic.py',
        'scripts/precompute_external_development_inputs.py',
    ]
    files += [p.relative_to(root).as_posix() for p in
              sorted((root / 'outputs/private/point_sources').iterdir()) if p.is_file()]
    return {name: sha256_file(root / name) for name in files}


def development_context(root):
    root = Path(root)
    private = root / 'outputs/private'
    plan = json.loads((root / 'config/kma_external_validation_plan.json').read_text(encoding='utf-8'))
    external = set().union(*map(set, plan['station_groups'].values()))
    assert_training_stations(external)
    cutoff = pd.Timestamp(plan['development_end_kst']) + pd.Timedelta(days=1)
    times = pd.date_range(plan['development_start_kst'], cutoff, freq='10min', inclusive='left')
    coordinates = pd.read_csv(private / 'point_sources/weather_coordinates.csv', dtype={'station_id': str})
    metadata = pd.read_csv(private / 'sensor_availability/metadata.csv', dtype={'station': str})
    metadata = metadata.loc[metadata.kind.eq('RWIS'), ['station', 'route', 'lat', 'lon']]
    aws = pd.read_parquet(private / 'point_sources/aws.parquet')
    asos = pd.read_parquet(private / 'point_sources/asos.parquet')
    rwis = pd.read_parquet(private / 'point_sources/rwis.parquet')
    donors = set(rwis.station)
    assert_training_stations(donors)
    if len(donors) != 14 or donors & external or not donors <= set(metadata.station):
        raise ValueError('Only the fourteen competition development donors are permitted')
    builder = PointInputBuilder(aws.loc[aws.source_time.lt(cutoff)], asos.loc[asos.source_time.lt(cutoff)],
                                rwis.loc[rwis.time.lt(cutoff)], coordinates, metadata)
    catalog = pd.read_csv(private / 'external/kma_rwis_reference/station_catalog.csv', dtype={'station': str}).set_index('station')
    points = {}
    for station in sorted(external):
        row = catalog.loc[station]
        points[station] = {'station': station,
                           'route': '통영-대전중부선' if row.route == '통영-대전중부' else row.route,
                           'lat': float(row.lat), 'lon': float(row.lon), 'elevation_m': float(row.elevation_m)}
    return plan, times, points, builder, sorted(donors)


def validate_input_frame(frame, station, times):
    if TARGET_COLUMNS & set(frame):
        raise ValueError('Cached inputs contain external target observations or labels')
    if set(frame.station) != {station} or frame.duplicated(['station', 'time']).any():
        raise ValueError('Cached station or time keys are invalid')
    wanted = pd.DatetimeIndex(times)
    actual = pd.DatetimeIndex(frame.time)
    if actual.tz is not None or not actual.equals(wanted):
        raise ValueError('Cached inputs do not match the exact requested time grid')


def load_cached_inputs(root, station, times, signature=None):
    root = Path(root)
    cache = root / CACHE_RELATIVE
    manifest = json.loads((cache / 'manifest.json').read_text(encoding='utf-8'))
    signature = input_signature(root) if signature is None else signature
    if manifest['signature'] != signature or manifest['status'] != 'development_inputs_complete_without_target_observations':
        raise ValueError('Input cache is incomplete or its sources changed')
    if manifest['target_observations_used'] or manifest['reserved_outcomes_used']:
        raise ValueError('Input cache provenance does not permit development')
    plan = json.loads((root / 'config/kma_external_validation_plan.json').read_text(encoding='utf-8'))
    stations = set().union(*map(set, plan['station_groups'].values()))
    if set(manifest['records']) != stations or station not in stations:
        raise ValueError('Incomplete external station inventory')
    cutoff = pd.Timestamp(plan['development_end_kst']) + pd.Timedelta(days=1)
    full_grid = pd.date_range(plan['development_start_kst'], cutoff, freq='10min', inclusive='left')
    path = cache / f'{station}.parquet'
    record = manifest['records'][station]
    if sha256_file(path) != record['sha256']:
        raise ValueError('Cached input file changed')
    frame = pd.read_parquet(path)
    validate_input_frame(frame, station, full_grid)
    if len(frame) != record['rows'] or frame.columns.tolist() != record['columns']:
        raise ValueError('Cached input schema or row count changed')
    wanted = pd.DatetimeIndex(times).sort_values()
    if wanted.has_duplicates or not wanted.isin(full_grid).all():
        raise ValueError('Requested observations are outside the fixed input grid')
    result = frame.set_index('time', drop=False).loc[wanted].reset_index(drop=True)
    validate_input_frame(result, station, wanted)
    return result, record['references']
