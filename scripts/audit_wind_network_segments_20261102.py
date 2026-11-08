"""843구간의 새 풍속 집계·다른 성분 보존·19구간의 공용 API 재추론을 검산한다."""
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_objective_icing import read, write, now, verify_preserved
from scripts.project_wind_network_segments_20261102 import inputs, OUTPUT, PREVIOUS, SUPPLEMENT
from src.data_source import sha256_file as sha
from src.wind_network_runtime import predict_wind_network, network_features
from src.offline_runtime import deny_network


def main():
    out = ROOT/OUTPUT; old = ROOT/PREVIOUS; supplement = ROOT/SUPPLEMENT
    if (out/'independent_verification.json').exists(): raise FileExistsError('Preserve completed projection audit')
    summary = read(out/'summary.json'); plan = read(out/'plan.json'); settings = plan['settings']
    for path, digest in plan['signatures'].items(): assert sha(ROOT/path) == digest, path
    for path, digest in summary['files'].items(): assert sha(out/path) == digest, path
    options = dict(dtype={'seg_id': str}, float_precision='round_trip')
    table = pd.read_csv(out/'weather_segments_500m.csv', **options).set_index(['seg_id', 'winter'])
    daily = pd.read_parquet(out/'weather_segment_daily.parquet').set_index(['seg_id', 'date'])
    daily_csv = pd.read_csv(out/'weather_segment_daily.csv.gz', dtype={'seg_id': str},
        float_precision='round_trip', parse_dates=['date']).set_index(['seg_id', 'date'])
    pd.testing.assert_frame_equal(daily, daily_csv, check_exact=True)
    before_daily = pd.read_parquet(old/'weather_segment_daily.parquet').set_index(['seg_id', 'date'])
    cols = [c for c in before_daily if c not in ['wind_speed_mean', 'wind_speed_valid_slots']]
    pd.testing.assert_frame_equal(daily[cols], before_daily[cols], check_exact=True)
    assert len(table) == 1686 and len(daily) == 202320 and table.index.is_unique and daily.index.is_unique
    old_table = pd.read_csv(old/'weather_segments_500m.csv', **options).set_index(['seg_id', 'winter'])
    cols = [c for c in old_table if 'wind_speed' not in c]
    pd.testing.assert_frame_equal(table[cols], old_table[cols], check_exact=True)
    checks = 0; preserved = 0; changed = 0; total = 0; delta_sum = 0.; maximum = 0.
    for number, record in enumerate(summary['point_records'], 1):
        segment = record['seg_id']; path = out/'points'/(segment+'.parquet'); previous = old/'points'/path.name
        assert sha(path) == record['prediction_sha256'] and sha(previous) == record['previous_prediction_sha256']
        f = pd.read_parquet(path); before = pd.read_parquet(previous)
        columns = [c for c in before if c != 'estimated_wind_speed_ms']
        pd.testing.assert_frame_equal(f[columns], before[columns], check_exact=True); preserved += len(f)*len(columns)
        values = f.estimated_wind_speed_ms.to_numpy(); b = before.estimated_wind_speed_ms.to_numpy()
        good = np.isfinite(values); np.testing.assert_array_equal(good, np.isfinite(b))
        assert (values[good] >= 0).all()
        delta = np.abs(values[good]-b[good]); changed += int((delta != 0).sum()); total += len(delta)
        delta_sum += float(delta.sum()); maximum = max(maximum, float(delta.max()))
        day = daily.loc[segment]
        np.testing.assert_array_equal(day.index.to_numpy(), f.time.iloc[::144].dt.normalize())
        for target, column in [('air_temperature', 'estimated_air_temperature_c'),
                              ('relative_humidity', 'estimated_humidity_pct'), ('wind_speed', 'estimated_wind_speed_ms')]:
            a = f[column].to_numpy().reshape(240, 144); count = np.isfinite(a).sum(axis=1)
            mean = np.divide(np.nansum(a, axis=1), count, out=np.full(240, np.nan), where=count > 0)
            np.testing.assert_array_equal(count, day[target+'_valid_slots'])
            np.testing.assert_allclose(mean, day[target+'_mean'], atol=1e-10, rtol=0, equal_nan=True); checks += 480
            for year, part in zip([2024, 2025], np.split(f[column].to_numpy(), 2)):
                a = part[np.isfinite(part)]; row = table.loc[segment, year]
                assert int(row[target+'_valid_slots']) == len(a); checks += 1
                for name, value in [('mean', a.mean()), ('p10', np.quantile(a, .1)), ('p50', np.median(a)), ('p90', np.quantile(a, .9))]:
                    np.testing.assert_allclose(row[target+'_'+name], value, atol=1e-10, rtol=0); checks += 1
        np.testing.assert_array_equal(day.wind_network_outside_slots,
            f.wind_network_outside_training_range.to_numpy().reshape(240, 144).sum(axis=1)); checks += 240
        np.testing.assert_array_equal(day.wind_network_mean_station_count,
            f.network_wind_speed_count.to_numpy().reshape(240, 144).mean(axis=1)); checks += 240
        for year, ix in zip([2024, 2025], np.split(np.arange(len(f)), 2)):
            q = f.iloc[ix]; row = table.loc[segment, year]
            for column, expected in [('wind_network_outside_fraction', q.wind_network_outside_training_range.mean()),
                    ('wind_network_mean_station_count', q.network_wind_speed_count.mean()),
                    ('wind_network_mean_effective_n', q.network_wind_speed_effective_n.mean())]:
                np.testing.assert_allclose(row[column], expected, rtol=0, atol=1e-12, equal_nan=True); checks += 1
            for left, right in [('air_temperature', 'relative_humidity'), ('air_temperature', 'wind_speed'), ('relative_humidity', 'wind_speed')]:
                columns = {'air_temperature': 'estimated_air_temperature_c', 'relative_humidity': 'estimated_humidity_pct', 'wind_speed': 'estimated_wind_speed_ms'}
                x = q[columns[left]].to_numpy(); y = q[columns[right]].to_numpy(); valid = np.isfinite(x) & np.isfinite(y)
                key = left+'__'+right; assert int(row[key+'_paired_slots']) == int(valid.sum()); checks += 1
                if valid.sum() > 1 and np.ptp(x[valid]) > 0 and np.ptp(y[valid]) > 0:
                    np.testing.assert_allclose(row[key+'_correlation'], np.corrcoef(x[valid], y[valid])[0, 1], atol=1e-10, rtol=0)
                else: assert pd.isna(row[key+'_correlation'])
                checks += 1
        if number % 100 == 0: print('AGGREGATE AUDIT', number, '/843', flush=True)
    a = pd.read_csv(old/'weather_and_preserved_road_estimates.csv', **options).set_index(['seg_id', 'winter'])
    b = pd.read_csv(out/'weather_and_preserved_road_estimates.csv', **options).set_index(['seg_id', 'winter'])
    columns = ['prediction_group', 'estimated_temp_mean_c', 'cold_wet_fraction']
    pd.testing.assert_frame_equal(a[columns], b[columns], check_exact=True)
    geometry = gpd.read_file(ROOT/settings['geometry'], columns=['seg_id', 'geometry']).set_index('seg_id')
    for year in [2024, 2025]:
        layer = gpd.read_file(out/'weather_segments.gpkg', layer=f'winter_{year}').set_index('seg_id')
        assert layer.crs == geometry.crs and layer.geometry.sort_index().equals(geometry.geometry.sort_index())
        for column in b:
            if column == 'asos_station':
                np.testing.assert_array_equal(layer[column].sort_index().astype(str),
                    b.xs(year, level='winter')[column].sort_index().astype(str)); checks += len(layer)
            elif pd.api.types.is_numeric_dtype(b[column]):
                np.testing.assert_allclose(layer[column].sort_index(), b.xs(year, level='winter')[column].sort_index(),
                    rtol=0, atol=1e-10, equal_nan=True); checks += len(layer)
    points = pd.read_csv(ROOT/settings['point_geometry'], dtype={'seg_id': str})
    selected = set(points.iloc[np.linspace(0, len(points)-1, 17, dtype=int)].seg_id)
    selected.add(table.wind_network_outside_fraction.idxmax()[0])
    selected.add(next(r['seg_id'] for r in summary['point_records'] if r['new_asos_source_domain']))
    for segment in points.seg_id:
        if len(selected) >= 19: break
        selected.add(segment)
    selected = sorted(selected)[:19]
    builder, _, _, aws, coordinates = inputs(settings, supplement)
    meta = read(supplement/'model/metadata.json')
    ranges = pd.read_csv(out/'wind_feature_training_range.csv', float_precision='round_trip').set_index('feature')
    training = pd.read_parquet(supplement/'data/training.parquet', columns=meta['features'])
    np.testing.assert_array_equal(training.min(), ranges.minimum); np.testing.assert_array_equal(training.max(), ranges.maximum)
    replayed = 0
    for segment in selected:
        point = points.loc[points.seg_id.eq(segment)].iloc[0]
        with deny_network() as attempts, threadpool_limits(limits=2):
            frame, _ = builder.build(point.point_lat, point.point_lon); frame = frame.assign(station=segment)
            location = pd.DataFrame({'station': [segment], 'lat': [point.point_lat], 'lon': [point.point_lon]})
            actual = predict_wind_network(frame, location, aws, coordinates, supplement/'model')
            _, x, _ = network_features(frame, location, aws, coordinates, meta['network'])
        assert not attempts
        expected = pd.read_parquet(out/'points'/(segment+'.parquet'))
        for column in ['estimated_wind_speed_ms', 'network_wind_speed_count', 'network_wind_speed_effective_n',
                       'network_wind_speed_range', 'network_wind_speed_distance_km']:
            np.testing.assert_array_equal(actual[column], expected[column]); replayed += len(actual)
        outside = (x.lt(ranges.minimum) | x.gt(ranges.maximum)).any(axis=1)
        np.testing.assert_array_equal(outside, expected.wind_network_outside_training_range); replayed += len(actual)
        print('WIND API REPLAY', segment, flush=True)
    assert verify_preserved() == summary['preservation'] == plan['preservation']
    write(out/'independent_verification.json', dict(status='passed', at_utc=now(), summary_sha256=sha(out/'summary.json'),
        audit_source_sha256=sha(Path(__file__)), aggregate_checks=checks, preserved_point_values=preserved,
        replayed_values_exact=replayed, replayed_segments=selected, valid_wind_rows=total, changed_estimate_rows=changed,
        mean_absolute_estimate_change=delta_sum/total, maximum_absolute_estimate_change=maximum,
        interpretation='Estimate change, not measured segment error or new independent validation',
        air_humidity_road_icing_preserved=True, protected_outcomes_read=False))
    print('WIND MAP AUDIT PASSED', checks, 'checks,', replayed, 'API values', flush=True)


if __name__ == '__main__':
    main()
