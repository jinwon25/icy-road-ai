import unittest
import numpy as np
from src.development_resampling import circular_day_indices, paired_macro_resamples


class DevelopmentResamplingTests(unittest.TestCase):
    def test_blocks_preserve_adjacency_and_seed(self):
        ids = circular_day_indices(12, 3, 8, 7)
        np.testing.assert_array_equal(ids, circular_day_indices(12, 3, 8, 7))
        self.assertTrue(np.all(np.diff(ids.reshape(8, 4, 3), axis=-1) % 12 == 1))

    def test_station_equal_weight_not_pooled(self):
        a = np.array([[[10., 10.], [100., 100.]], [[5., 5.], [100., 100.]]])
        b = np.array([[[10., 10.], [1., 1.]], [[10., 10.], [1., 1.]]])
        v, n = paired_macro_resamples(a, b, [[0, 1]])
        np.testing.assert_allclose(v[:, 0], [50.5, 50.25])
        np.testing.assert_array_equal(n[:, 0], [2, 2])

    def test_no_supported_station_is_undefined(self):
        v, n = paired_macro_resamples(np.zeros((2, 1, 2)), np.zeros((2, 1, 2)), [[1, 1]])
        self.assertTrue(np.isnan(v).all())
        self.assertTrue((n == 0).all())


if __name__ == '__main__':
    unittest.main()
