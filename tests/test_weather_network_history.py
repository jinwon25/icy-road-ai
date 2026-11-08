import numpy as np
import pandas as pd
import pytest

from src.weather_network import FIELDS
from src.weather_network_history import network_history_features
from tests.test_weather_history_stable import longer


def sample():
    f = longer()
    rng = np.random.default_rng(20261102)
    x = pd.DataFrame({f'network_{field}_{kind}': rng.normal(size=len(f))
        for field in FIELDS for kind in ('idw', 'sd', 'range', 'contrast', 'count', 'distance_km', 'effective_n')})
    return f, x


def test_definition_calendar_gaps_and_minimum_coverage():
    f, x = sample()
    keep = np.ones(len(f), dtype=bool); keep[[100, 110, 500, 601]] = False
    f = f.loc[keep].reset_index(drop=True); x = x.loc[keep].reset_index(drop=True)
    actual = network_history_features(f, x)
    assert actual.shape == (len(f), 147)
    for hours, minimum in [(3, 6), (24, 48)]:
        col = 'network_wind_speed_idw'
        series = pd.Series(x[col].to_numpy(), index=f.time)
        dense = series.reindex(pd.date_range(f.time.min(), f.time.max(), freq='10min'))
        expected = dense.rolling(hours*6, min_periods=minimum).mean().reindex(f.time).to_numpy()
        np.testing.assert_allclose(actual[f'{col}_mean_{hours}h'], expected, atol=1e-14, rtol=1e-14)
    assert np.isnan(actual.loc[4, 'network_wind_speed_idw_mean_3h'])
    assert actual.loc[5, 'network_wind_speed_idw_coverage_3h'] == 6/18


def test_prefix_is_exact_and_future_cannot_change_the_past():
    f, x = sample(); full = network_history_features(f, x)
    limited = network_history_features(f.iloc[432:].reset_index(drop=True), x.iloc[432:].reset_index(drop=True))
    pd.testing.assert_frame_equal(full.iloc[576:].reset_index(drop=True), limited.iloc[144:].reset_index(drop=True), check_exact=True)
    changed = x.copy(); changed.loc[600:, :] = 999.
    altered = network_history_features(f, changed)
    pd.testing.assert_frame_equal(full.iloc[:600], altered.iloc[:600], check_exact=True)


def test_station_winter_isolation_and_no_target_features():
    f, x = sample(); full = network_history_features(f, x)
    second = f.copy(); second['station'] = 'other'
    later = f.copy(); later['winter'] = 2025; later['time'] = later.time+pd.DateOffset(years=1)
    many = pd.concat([f, second, later], ignore_index=True).assign(road_temp=999., ice=1, wind_speed=75.)
    combined = network_history_features(many, pd.concat([x, x*5, x*10], ignore_index=True))
    pd.testing.assert_frame_equal(combined.iloc[:len(f)], full, check_exact=True)
    assert not {'road_temp', 'ice', 'wind_speed', 'winter', 'station'} & set(combined)
    assert np.isnan(combined.loc[len(f), 'network_wind_speed_idw_mean_3h'])
    assert np.isnan(combined.loc[len(f)*2, 'network_wind_speed_idw_mean_3h'])


def test_missing_network_remains_missing_and_reject_bad_alignment():
    f, x = sample(); x.loc[:, :] = np.nan
    actual = network_history_features(f, x)
    assert actual.filter(regex='network_.*_mean_').isna().all().all()
    assert actual.filter(regex='network_.*_coverage_').eq(0).all().all()
    with pytest.raises(ValueError, match='indices'):
        network_history_features(f, x.set_index(pd.Index(np.arange(len(x))+1)))
    with pytest.raises(ValueError, match='schema'):
        network_history_features(f, x.assign(road_temp=0))
