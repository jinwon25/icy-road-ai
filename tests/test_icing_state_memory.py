import numpy as np
import pandas as pd
import pytest
from src.icing_state_memory import causal_ice_state


def frame(n):
    return pd.DataFrame({'station': ['x'] * n, 'time': pd.date_range('2025-01-01', periods=n, freq='10min')})


def test_baseline_identity_and_causal_confirmation():
    f = frame(10)
    p = np.array([0, 1, 0, 1, 1, 1, 0, 0, 1, 1.])
    np.testing.assert_array_equal(causal_ice_state(f, p, np.zeros(10)), p)
    np.testing.assert_array_equal(causal_ice_state(f, p, np.zeros(10), confirmation=2),
                                  [0, 0, 0, 0, 1, 1, 0, 0, 0, 1])
    altered = p.copy(); altered[6:] = 1
    np.testing.assert_array_equal(causal_ice_state(f, altered, np.zeros(10), confirmation=2)[:6],
                                  causal_ice_state(f, p, np.zeros(10), confirmation=2)[:6])


def test_hold_has_fixed_expiry_and_warm_release():
    f = frame(7); p = [1, 0, 0, 0, 0, 0, 0.]
    np.testing.assert_array_equal(causal_ice_state(f, p, np.zeros(7), hold_minutes=30),
                                  [1, 1, 1, 1, 0, 0, 0])
    np.testing.assert_array_equal(causal_ice_state(f, p, [-1, .5, 1.1, -1, -1, -1, -1],
                                  hold_minutes=90, release_c=1), [1, 1, 0, 0, 0, 0, 0])


def test_missing_gap_and_station_boundaries_reset_state():
    f = frame(6)
    p = [1, 0, np.nan, 0, 0, 0]
    np.testing.assert_allclose(causal_ice_state(f, p, np.zeros(6), hold_minutes=90),
                               [1, 1, np.nan, 0, 0, 0], equal_nan=True)
    f.loc[2:, 'time'] += pd.Timedelta(minutes=10)
    np.testing.assert_array_equal(causal_ice_state(f, [1, 0, 0, 0, 0, 0], np.zeros(6), hold_minutes=90),
                                  [1, 1, 0, 0, 0, 0])
    f = frame(6); f.loc[2:, 'station'] = 'other'
    np.testing.assert_array_equal(causal_ice_state(f, [1, 0, 0, 0, 0, 0], np.zeros(6), hold_minutes=90),
                                  [1, 1, 0, 0, 0, 0])


def test_permutation_invariance_and_invalid_input():
    f = frame(6); f['p'] = [0., 1., 1., 0., 0., 0.]
    expected = causal_ice_state(f, f.p, np.zeros(6), confirmation=2, hold_minutes=30)
    s = f.sample(frac=1, random_state=4)
    out = pd.Series(causal_ice_state(s, s.p, np.zeros(6), confirmation=2, hold_minutes=30), index=s.index)
    np.testing.assert_array_equal(out.sort_index(), expected)
    with pytest.raises(ValueError):
        causal_ice_state(f, np.ones(6) * .5, np.zeros(6))
    with pytest.raises(ValueError):
        causal_ice_state(f, f.p, np.zeros(6), confirmation=4)
