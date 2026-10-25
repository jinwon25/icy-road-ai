import numpy as np
import pandas as pd
import pytest
from src.icing_transition import previous_training_state, transition_weights, forward_state_scores


def keys(n=6):
    return pd.DataFrame({'station': ['s'] * n, 'time': pd.date_range('2025-01-01', periods=n, freq='10min')})


def test_forward_matches_exhaustive_latent_path_marginalization():
    # 2^5개 잠재 경로를 직접 열거해 순방향 재귀와 비교한다.
    from itertools import product
    f = keys(5); p0 = np.array([.1, .2, .3, .1, .4]); p1 = np.array([.9, .7, .8, .6, .95]); prior = .23
    expected = []
    for length in range(1, 6):
        positive = 0.
        for path in product([0, 1], repeat=length + 1):
            mass = prior if path[0] else 1-prior
            for t in range(length):
                chance = p1[t] if path[t] else p0[t]
                mass *= chance if path[t+1] else 1-chance
            positive += mass * path[-1]
        expected.append(positive)
    np.testing.assert_allclose(forward_state_scores(f, p0, p1, np.ones(5, bool), prior), expected, atol=1e-14)


def test_missing_gap_station_and_season_reset():
    f = keys(); f.loc[4:, 'time'] += pd.Timedelta(days=300)
    valid = np.array([1, 1, 0, 1, 1, 1], bool)
    actual = forward_state_scores(f, np.zeros(6), np.ones(6), valid, .2)
    np.testing.assert_allclose(actual, [.2, .2, np.nan, .2, .2, .2], equal_nan=True)
    g = pd.concat([keys(3), keys(3).assign(station='other')], ignore_index=True)
    p0 = np.array([.8]*3 + [.1]*3); p1 = np.ones(6)*.9
    a = forward_state_scores(g, p0, p1, np.ones(6, bool), .2)
    np.testing.assert_allclose(a[3:], forward_state_scores(keys(3), p0[3:], p1[3:], np.ones(3, bool), .2))


def test_future_invariance_permutation_and_zero_memory_ablation():
    f = keys(); p0 = np.linspace(.1, .6, 6); p1 = np.linspace(.5, 1., 6); valid = np.ones(6, bool)
    a = forward_state_scores(f, p0, p1, valid, .2, .5)
    changed = p1.copy(); changed[4:] = 0
    np.testing.assert_array_equal(a[:4], forward_state_scores(f, p0, changed, valid, .2, .5)[:4])
    order = [5, 2, 0, 1, 4, 3]
    b = forward_state_scores(f.iloc[order], p0[order], p1[order], valid[order], .2, .5)
    np.testing.assert_allclose(b[np.argsort(order)], a)
    np.testing.assert_allclose(forward_state_scores(f, p0, p1, valid, .2, 0), .8*p0+.2*p1)


def test_training_previous_is_only_contiguous_valid_same_station():
    f = keys(); f['ice'] = [0, 1, np.nan, 0, 1, 0]; f['winter'] = 2024
    np.testing.assert_allclose(previous_training_state(f, np.ones(6, bool)), [np.nan, 0, np.nan, np.nan, 0, 1], equal_nan=True)
    f.loc[4:, 'station'] = 'other'
    np.testing.assert_allclose(previous_training_state(f, np.array([1, 1, 1, 1, 1, 0], bool)), [np.nan, 0, np.nan, np.nan, np.nan, np.nan], equal_nan=True)


def test_transition_weights_balance_strata_without_using_evaluation_rows():
    f = keys(5).assign(winter=2024, ice=[0, 0, 1, 1, 1]); previous = [0, 0, 0, 1, 1]
    w = transition_weights(f, previous, 'station_transition')
    np.testing.assert_allclose([w[:2].sum(), w[2], w[3:].sum()], [5/3]*3)
    assert w.mean() == pytest.approx(1)


def test_inference_rejects_outcomes_bad_keys_and_probabilities():
    f = keys(); args = (np.zeros(6), np.ones(6), np.ones(6, bool), .1)
    with pytest.raises(ValueError): forward_state_scores(f.assign(ice=0), *args)
    with pytest.raises(ValueError): forward_state_scores(pd.concat([f.iloc[:1]]*6), *args)
    with pytest.raises(ValueError): forward_state_scores(f, np.ones(6)*2, *args[1:])
    with pytest.raises(ValueError): forward_state_scores(f, *args, memory_strength=.1)
