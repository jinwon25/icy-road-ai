import unittest

import numpy as np
from shapely.geometry import LineString

from src.terrain_features import curvature_proxy


class TerrainFeatureTests(unittest.TestCase):
    def test_straight_and_known_circle_geometry(self):
        self.assertEqual(curvature_proxy(LineString([(0, 0), (1000, 0)]))["curvature_p90_inv_m"], 0.)
        angles = np.linspace(0, np.pi / 2, 2001)
        line = LineString(np.c_[500 * np.cos(angles), 500 * np.sin(angles)])
        self.assertAlmostEqual(curvature_proxy(line)["curvature_p90_inv_m"], 1 / 500, places=6)

    def test_short_segments_are_not_given_invented_curvature(self):
        result = curvature_proxy(LineString([(0, 0), (20, 0)]))
        self.assertTrue(np.isnan(result["curvature_p90_inv_m"]))
        self.assertEqual(result["curvature_samples"], 0)


if __name__ == "__main__":
    unittest.main()
