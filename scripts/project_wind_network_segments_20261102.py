"""채택된 69특성 풍속을 843구간에 전파하고 기존 기온·습도·노면 결과를 보존한다."""
from pathlib import Path
import sys
import time

import geopandas as gpd
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_objective_icing import read, write, now, verify_preserved
from scripts.project_weather_segments import statistics
from src.data_source import sha256_file as sha
from src.segment_exposure import WeatherOnlySources
from src.road_weather_points import RoadWeatherPoints
from src.weather_history_runtime import prepare_history_input
from src.road_weather_transfer import features, baselines
from src.weather_network import WeatherNetwork, FIELDS
from src.offline_runtime import deny_network

OUTPUT = 'outputs/private/wind_network_segment_projection_20261102_v1'
PREVIOUS = 'outputs/private/weather_history_segment_projection_20261101_v1'
SUPPLEMENT = 'outputs/private/wind_network_supplement_20261101_v2'


def inputs(settings, supplement):
    source = ROOT/settings['weather_sources']
    aws = pd.read_parquet(source/'aws.parquet')
    coordinates = pd.read_csv(supplement/'data/aws_coordinates.csv', dtype={'station': str})
    weather = WeatherOnlySources(aws, pd.read_parquet(source/'asos.parquet'),
        pd.read_csv(source/'weather_coordinates.csv', dtype={'station_id': str}))
    times = pd.DatetimeIndex(np.concatenate([pd.date_range(a, b, freq='10min', inclusive='left').values
        for a, b in settings['winters']]))
    builder = RoadWeatherPoints(weather,
        pd.read_parquet(ROOT/settings['input_preparation']/'asos_supplementary.parquet'), times)
    meta = read(supplement/'model/metadata.json')
    network = WeatherNetwork(aws[['station', 'source_time', *FIELDS]],
        coordinates.set_index('station')[['lat', 'lon']], **meta['network'])
    for station in coordinates.station:
        if station not in network.sources:
            network.sources[station] = (np.empty(0, dtype='datetime64[ns]'), np.empty((0, len(FIELDS))))
    return builder, network, times, aws, coordinates


def main():
    config = ROOT/'config/weather_segment_projection_20261031.json'; settings = read(config)
    old = ROOT/PREVIOUS; supplement = ROOT/SUPPLEMENT; out = ROOT/OUTPUT
    prior = read(old/'summary.json'); audit = read(old/'independent_verification.json')
    assert audit['status'] == 'passed' and audit['summary_sha256'] == sha(old/'summary.json')
    for name, digest in prior['files'].items(): assert sha(old/name) == digest, name
    proof = ROOT/'outputs/private/wind_network_supplement_validation_20261101_v1/receipt.json'
    checked = read(proof); assert checked['status'] == 'wind_network_supplement_verified'
    assert checked['source_receipt_sha256'] == sha(supplement/'receipt.json')
    for name, digest in read(supplement/'receipt.json')['files'].items(): assert sha(supplement/name) == digest, name
    prep = ROOT/settings['input_preparation']; receipt = read(prep/'receipt.json')
    for path, digest in receipt['source_signatures'].items(): assert sha(ROOT/path) == digest, path
    assert sha(prep/'asos_supplementary.parquet') == receipt['supplementary_sha256']
    meta = read(supplement/'model/metadata.json'); model_path = supplement/'model'/meta['file']
    assert sha(model_path) == meta['sha256']
    paths = [config, Path(__file__), old/'summary.json', old/'independent_verification.json', proof,
        supplement/'receipt.json', supplement/'model/metadata.json', model_path,
        supplement/'data/training.parquet', supplement/'data/aws_coordinates.csv', prep/'receipt.json',
        prep/'asos_supplementary.parquet', ROOT/settings['point_geometry'], ROOT/settings['geometry'],
        ROOT/'src/weather_network.py', ROOT/'src/weather_history_runtime.py',
        ROOT/'src/road_weather_transfer.py', ROOT/'src/road_weather_points.py']
    signatures = {p.relative_to(ROOT).as_posix(): sha(p) for p in paths}
    frozen = verify_preserved()
    if out.exists():
        assert read(out/'plan.json')['signatures'] == signatures
        if (out/'summary.json').exists(): raise FileExistsError('Preserve completed wind projection')
    else:
        out.mkdir(); (out/'points').mkdir()
        write(out/'plan.json', dict(at_utc=now(), settings=settings, previous=PREVIOUS, supplement=SUPPLEMENT,
            signatures=signatures, preservation=frozen, model_features=69,
            interpretation='New estimates with accepted model; no new measured segment accuracy'))
    points = pd.read_csv(ROOT/settings['point_geometry'], dtype={'seg_id': str})
    assert len(points) == 843 and points.seg_id.is_unique
    builder, network, times, _, _ = inputs(settings, supplement)
    model = joblib.load(model_path)
    training = pd.read_parquet(supplement/'data/training.parquet', columns=meta['features'])
    low = training.min(); high = training.max(); del training
    write_range = out/'wind_feature_training_range.csv'
    ranges = pd.DataFrame({'feature': low.index, 'minimum': low.values, 'maximum': high.values})
    if write_range.exists():
        pd.testing.assert_frame_equal(pd.read_csv(write_range, float_precision='round_trip'), ranges, check_exact=True)
    else: ranges.to_csv(write_range, index=False, encoding='utf-8-sig')
    old_daily = pd.read_parquet(old/'weather_segment_daily.parquet').set_index('seg_id')
    original = {r['seg_id']: r for r in prior['point_records']}
    records = []; summaries = []; days = []; start = time.perf_counter()
    for number, point in enumerate(points.itertuples(), 1):
        path = out/'points'/(point.seg_id+'.parquet'); metadata = path.with_suffix('.json')
        old_path = old/'points'/path.name
        assert sha(old_path) == original[point.seg_id]['prediction_sha256']
        if metadata.exists():
            record = read(metadata); assert sha(path) == record['prediction_sha256']; prediction = pd.read_parquet(path)
        else:
            if path.exists(): raise FileExistsError('Unrecorded point prediction')
            with deny_network() as attempts, threadpool_limits(limits=2):
                frame, mapping = builder.build(point.point_lat, point.point_lon)
                assert mapping == original[point.seg_id]['mapping']
                f = prepare_history_input(frame.assign(station=point.seg_id))
                spatial, network_mapping = network.build(f.time, point.point_lat, point.point_lon, f)
                x = pd.concat([features(f), spatial], axis=1)
                assert list(x) == meta['features'] == list(model.feature_names_in_)
                a, b = baselines(f, 'wind_speed'); available = np.isfinite(a) & np.isfinite(b)
                values = np.full(len(f), np.nan)
                values[available] = np.maximum(model.predict(x.loc[available])+b[available], 0)
            assert not attempts
            prediction = pd.read_parquet(old_path)
            assert pd.DatetimeIndex(prediction.time).equals(times) and len(prediction) == len(f)
            np.testing.assert_array_equal(np.isfinite(values), np.isfinite(prediction.estimated_wind_speed_ms))
            prediction['estimated_wind_speed_ms'] = values
            for column in ['network_wind_speed_count', 'network_wind_speed_effective_n',
                           'network_wind_speed_range', 'network_wind_speed_distance_km']:
                prediction[column] = spatial[column].to_numpy()
            prediction['wind_network_outside_training_range'] = (x.lt(low) | x.gt(high)).any(axis=1).to_numpy()
            prediction.to_parquet(path, index=False, compression='zstd')
            record = dict(original[point.seg_id], prediction_sha256=sha(path),
                previous_prediction_sha256=sha(old_path), network_mapping=network_mapping)
            write(metadata, record)
        records.append(record)
        for year, q in prediction.groupby(np.where(prediction.time.dt.month >= 11, prediction.time.dt.year, prediction.time.dt.year-1)):
            summaries.append(dict(seg_id=point.seg_id, winter=int(year), route_nm=point.route_nm, flow_lbl=point.flow_lbl,
                len_m=point.len_m, point_lat=point.point_lat, point_lon=point.point_lon,
                asos_station=record['mapping']['asos_station'], new_asos_source_domain=record['new_asos_source_domain'],
                humidity_history_partial_fraction=float(q.humidity_history_status.ne('complete_24h').mean()),
                humidity_history_outside_fraction=float(q.humidity_history_outside_training_range.mean()),
                wind_network_outside_fraction=float(q.wind_network_outside_training_range.mean()),
                wind_network_mean_station_count=float(q.network_wind_speed_count.mean()),
                wind_network_mean_effective_n=float(q.network_wind_speed_effective_n.mean()),
                **statistics(q)))
        day = old_daily.loc[[point.seg_id]].reset_index().copy()
        assert pd.DatetimeIndex(day.date).equals(pd.DatetimeIndex(prediction.time.iloc[::144]).normalize())
        values = prediction.estimated_wind_speed_ms.to_numpy().reshape(240, 144)
        count = np.isfinite(values).sum(axis=1)
        day['wind_speed_mean'] = np.divide(np.nansum(values, axis=1), count,
            out=np.full(240, np.nan), where=count > 0)
        day['wind_speed_valid_slots'] = count
        day['wind_network_outside_slots'] = prediction.wind_network_outside_training_range.to_numpy().reshape(240, 144).sum(axis=1)
        day['wind_network_mean_station_count'] = prediction.network_wind_speed_count.to_numpy().reshape(240, 144).mean(axis=1)
        days.append(day)
        if number % 20 == 0 or number == 843:
            print('WIND PROJECT', number, '/843', round(time.perf_counter()-start, 1), 'seconds', flush=True)
    table = pd.DataFrame(summaries); table.to_csv(out/'weather_segments_500m.csv', index=False, encoding='utf-8-sig')
    daily = pd.concat(days, ignore_index=True)
    daily.to_parquet(out/'weather_segment_daily.parquet', index=False, compression='zstd')
    daily.to_csv(out/'weather_segment_daily.csv.gz', index=False, encoding='utf8', compression='gzip')
    previous = pd.read_csv(old/'weather_and_preserved_road_estimates.csv', dtype={'seg_id': str}, float_precision='round_trip')
    preserved = ['seg_id', 'winter', 'prediction_group', 'estimated_temp_mean_c', 'cold_wet_fraction']
    combined = table.merge(previous[preserved], on=['seg_id', 'winter'], validate='one_to_one')
    combined.to_csv(out/'weather_and_preserved_road_estimates.csv', index=False, encoding='utf-8-sig')
    geometry = gpd.read_file(ROOT/settings['geometry'], columns=['seg_id', 'geometry'])
    for year, q in combined.groupby('winter'):
        geometry.merge(q, on='seg_id', validate='one_to_one').to_file(out/'weather_segments.gpkg', layer=f'winter_{year}', driver='GPKG')
    assert verify_preserved() == frozen
    write(out/'summary.json', dict(status='wind_network_segment_projection_complete', at_utc=now(),
        segment_count=843, winters=2, ten_minute_rows=sum(r['rows'] for r in records), daily_rows=len(daily),
        summary_rows=len(table), point_records=records, preservation=frozen, seconds=time.perf_counter()-start,
        applied_wind_model_sha256=meta['sha256'], model_retrained=False, road_temperature_changed=False,
        air_temperature_changed=False, humidity_changed=False, icing_changed=False,
        new_independent_assessment=False, protected_outcomes_read=False,
        files={p.relative_to(out).as_posix(): sha(p) for p in out.iterdir() if p.is_file()}))
    print('WIND PROJECTION COMPLETE', len(table), len(daily), flush=True)


if __name__ == '__main__':
    main()
