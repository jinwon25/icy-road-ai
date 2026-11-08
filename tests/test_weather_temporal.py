import numpy as np
import pandas as pd
import pytest

from src.weather_temporal import temporal_features, split_masks
from tests.test_road_weather_transfer import sample


def history_sample():
    f = pd.concat([sample().iloc[[0]]]*160, ignore_index=True)
    f['station'] = 'a'; f['winter'] = 2024
    f['time'] = pd.date_range('2024-11-01', periods=len(f), freq='10min')
    f['asos_air_temp'] = np.arange(len(f), dtype=float)
    return f


def test_history_is_causal_and_target_invariant():
    f = history_sample(); _, a = temporal_features(f)
    changed = f.copy(); changed.loc[80:, 'asos_air_temp'] = -1000
    changed['air_temperature'] = 999; changed['road_temp'] = -999; changed['ice'] = 1
    _, b = temporal_features(changed)
    pd.testing.assert_frame_equal(a.iloc[:80], b.iloc[:80])
    assert a.loc[4, 'asos_air_temp_mean_3h'] != a.loc[4, 'asos_air_temp_mean_3h']
    assert a.loc[17, 'asos_air_temp_mean_3h'] == 8.5
    assert a.loc[18, 'asos_air_temp_mean_3h'] == 9.5
    assert a.loc[143, 'asos_air_temp_coverage_24h'] == 1


def test_history_separates_sites_winters_and_gaps():
    f = history_sample(); f.loc[80:, 'station'] = 'b'
    f.loc[120:, 'winter'] = 2025
    _, x = temporal_features(f)
    assert x.loc[80, 'asos_air_temp_coverage_3h'] == 1/18
    assert np.isnan(x.loc[120, 'asos_air_temp_mean_3h'])
    f = history_sample(); f.loc[80:, 'time'] += pd.Timedelta(days=2)
    _, x = temporal_features(f)
    assert np.isnan(x.loc[80, 'asos_air_temp_mean_24h'])
    f.loc[80, 'time'] = f.loc[79, 'time']
    with pytest.raises(ValueError, match='Unique'):
        temporal_features(f)


def test_shuffled_rows_and_stale_source_preserve_time_contract():
    f = history_sample()
    f.loc[80:, 'aws_age_minutes'] = 16
    _, expected = temporal_features(f)
    shuffled = f.sample(frac=1, random_state=7).reset_index(drop=True)
    _, actual = temporal_features(shuffled)
    order = shuffled.sort_values('time').index
    pd.testing.assert_frame_equal(actual.loc[order].reset_index(drop=True), expected)
    assert expected.loc[97, 'aws_air_temp_coverage_3h'] == 0
    assert np.isnan(expected.loc[97, 'aws_air_temp_mean_3h'])
    assert expected.loc[97, 'asos_air_temp_coverage_3h'] == 1


def test_split_excludes_whole_region_and_winter():
    f = pd.DataFrame(dict(station=['a','a','b','b','c','c'],
        group=['x','x','y','y','z','z'], winter=[2024,2025]*3))
    train, query = split_masks(f, np.ones(6, bool), 'x', 2025)
    assert np.flatnonzero(train).tolist() == [2,4]
    assert np.flatnonzero(query).tolist() == [1]
    f.loc[2,'station'] = 'a'
    with pytest.raises(ValueError, match='Station leakage'):
        split_masks(f, np.ones(6, bool), 'x', 2025)
