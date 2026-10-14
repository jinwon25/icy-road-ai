import unittest
import numpy as np
from src.thermal_consensus import predict_consensus


class ConsensusTests(unittest.TestCase):
    def test_disagreement_and_moisture(self):
        water = np.array([[2., 0., 0.], [np.nan, 0., 0.]])
        mean, _ = predict_consensus([-1, -1], [.2, -1], water, [0, 1])
        warm, _ = predict_consensus([-1, -1], [.2, -1], water, [0, 1], 'warmest')
        np.testing.assert_array_equal(mean, [1, 0])
        np.testing.assert_array_equal(warm, [0, 0])

    def test_missing_is_fallback_and_observed_dry_is_not(self):
        result, missing = predict_consensus([np.nan, -2, -2], [-2, -2, -2],
            [[1, 0, 0], [np.nan, np.nan, np.nan], [-3, 0, 0]], [1, 1, 1])
        np.testing.assert_array_equal(result, [1, 1, 0])
        np.testing.assert_array_equal(missing, [True, True, False])

    def test_dewpoint_margin_and_boundary(self):
        p, _ = predict_consensus([0, 0], [0, 0], [[0, 0, 0], [1, 0, 0]], [0, 0], dewpoint_margin=1)
        np.testing.assert_array_equal(p, [0, 1])

    def test_reject_invalid(self):
        for old, water in [([np.nan], [[0, 0, 0]]), ([0], [[np.inf, 0, 0]])]:
            with self.assertRaises(ValueError): predict_consensus([-1], [-1], water, old)


if __name__ == '__main__': unittest.main()
