import unittest
import numpy as np
import pandas as pd
from src.solar_terrain import solar_position, horizon_angles, join_power_history


class SolarTerrainTests(unittest.TestCase):
    def test_equinox_noon_and_night(self):
        altitude, _ = solar_position(pd.to_datetime(["2024-03-20 12:00", "2024-03-20 00:00"]), 0, 135)
        self.assertGreater(altitude[0], 87)
        self.assertLess(altitude[1], -87)

    def test_horizon_obstacle_and_unknown(self):
        got = horizon_angles(100, [[100, 200], [np.nan, 100], [90, 90]], [50, 100])
        self.assertAlmostEqual(got[0], 45)
        self.assertTrue(np.isnan(got[1]))
        self.assertEqual(got[2], 0)

    def test_unfinished_hour_and_cross_grid_excluded(self):
        target = pd.DataFrame({"time": pd.to_datetime(["2024-01-01 10:50", "2024-01-01 11:00", "2024-01-01 11:00"]), "grid_id": ["A", "A", "B"]})
        source = pd.DataFrame({"source_interval_end": pd.to_datetime(["2024-01-01 11:00"]), "grid_id": ["A"], "radiation": [7.]})
        out = join_power_history(target, source)
        self.assertTrue(np.isnan(out.radiation.iloc[0]))
        self.assertEqual(out.radiation.iloc[1], 7)
        self.assertTrue(np.isnan(out.radiation.iloc[2]))


if __name__ == "__main__":
    unittest.main()
