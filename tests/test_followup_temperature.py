import numpy as np
import pandas as pd
import pytest

from src.followup_temperature import LONG_MEMORY_COLUMNS, long_memory, training_weights


def weather(n=650):
    f = pd.DataFrame({'station': ['synthetic'] * n,
                      'time': pd.date_range('2025-01-01', periods=n, freq='10min')})
    for c in LONG_MEMORY_COLUMNS:
        f[c] = np.round(4 * np.sin(np.arange(n) / 31) + np.arange(n) / 1000, 6)
    f.loc[20:25, 'asos_ground_temp'] = np.nan
    return f


def test_long_memory_matches_independent_time_rolling_with_missing_rows():
    f = weather().drop(index=[80, 142, 299])
    actual = long_memory(f)
    for c in LONG_MEMORY_COLUMNS:
        for w in (1440, 2880):
            expected = f.set_index('time')[c].rolling(f'{w}min', closed='left',
                min_periods=int(np.ceil(.8 * w / 10))).mean().round(6)
            np.testing.assert_allclose(actual[f'{c}_prior_mean_{w}m'], expected,
                                       rtol=0, atol=1e-12, equal_nan=True)


def test_current_future_labels_and_other_locations_cannot_change_history():
    f = weather()
    a = long_memory(f)
    altered = f.copy()
    altered.loc[400:, list(LONG_MEMORY_COLUMNS)] = 999
    altered['road_temp'] = np.arange(len(f)) * -100
    pd.testing.assert_frame_equal(a.iloc[:401], long_memory(altered).iloc[:401], check_exact=True)
    other = f.copy()
    other.station = 'another'
    other[list(LONG_MEMORY_COLUMNS)] = 999
    both = pd.concat([f, other], ignore_index=True).sample(frac=1, random_state=3)
    pd.testing.assert_frame_equal(a, long_memory(both).loc[f.index], check_exact=True)


def test_exact_batch_context_and_gap_reset():
    f = weather()
    a = long_memory(f)
    shortened = f.loc[200:]
    pd.testing.assert_frame_equal(a.loc[488:], long_memory(shortened).loc[488:], check_exact=True)
    shifted = f.copy()
    shifted.loc[400:, 'time'] += pd.Timedelta(days=100)
    assert long_memory(shifted).loc[400].isna().all()


def test_invalid_grids_infinity_and_duplicate_rows_rejected():
    f = weather()
    with pytest.raises(ValueError):
        long_memory(pd.concat([f, f.iloc[:1]], ignore_index=True))
    f.loc[0, 'time'] += pd.Timedelta(minutes=1)
    with pytest.raises(ValueError):
        long_memory(f)
    f = weather()
    f.loc[5, 'asos_air_temp'] = np.inf
    with pytest.raises(ValueError):
        long_memory(f)


def test_weighting_is_fixed_symmetric_positive_and_training_only():
    f = pd.DataFrame({'road_temp': [-30., -3., 0., 3., 30.]})
    w = training_weights(f, {'cold_weight': 'exp_sigma3_floor01'})
    np.testing.assert_allclose(w, [.1, np.exp(-1), 1, np.exp(-1), .1])
    assert training_weights(pd.DataFrame(), {}) is None
    with pytest.raises(ValueError):
        training_weights(pd.DataFrame({'road_temp': [np.nan]}), {'cold_weight': 'exp_sigma3_floor01'})
