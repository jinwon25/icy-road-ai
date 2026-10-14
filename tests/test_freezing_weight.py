import unittest
import numpy as np
from src.freezing_weight import freezing_weights, fixed_blends


class FreezingWeightTests(unittest.TestCase):
    def test_symmetric_priority_and_l2_scale(self):
        w = freezing_weights([-10, -2, 0, 2, 10])
        self.assertAlmostEqual(w.mean(), 1.)
        np.testing.assert_array_equal(w, w[::-1])
        self.assertGreater(w[2], w[1])
        self.assertGreater(w[1], w[0])

    def test_invalid_training_targets(self):
        for x in ([], [np.nan], [np.inf], [[0, 1]]):
            with self.assertRaises(ValueError):
                freezing_weights(x)
        with self.assertRaises(ValueError):
            freezing_weights([0], sigma_celsius=0)

    def test_uniform_ablation_and_extreme_finite(self):
        np.testing.assert_array_equal(freezing_weights([-5, 3], amplitude=0), [1., 1.])
        self.assertTrue(np.isfinite(freezing_weights([0, 1e308])).all())

    def test_blend_preserves_missing_contract(self):
        p = fixed_blends([0, np.nan], [-2, np.nan], [2, np.nan])
        self.assertEqual(p['blend_half'][0], 0.)
        self.assertTrue(np.isnan(p['blend_half'][1]))
        with self.assertRaises(ValueError):
            fixed_blends([0, np.nan], [0, 1], [0, np.nan])


if __name__ == '__main__':
    unittest.main()
