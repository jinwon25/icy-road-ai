import unittest

import pandas as pd

from src.neighbor_validation import delayed_neighbor_join, winter_station_split


class NeighborValidationTests(unittest.TestCase):
    def test_no_same_time_or_future_and_delay_boundary(self):
        target = pd.DataFrame({"time": pd.to_datetime(["2026-01-01 01:00"])})
        source = pd.DataFrame({"time": pd.to_datetime(["2026-01-01 00:30", "2026-01-01 00:50", "2026-01-01 01:00"]),
                               "road_temp": [3., 5., 99.]})
        self.assertEqual(delayed_neighbor_join(target, source, 0).neighbor_road_temp.iloc[0], 5.)
        self.assertEqual(delayed_neighbor_join(target, source, 10).neighbor_road_temp.iloc[0], 5.)
        self.assertEqual(delayed_neighbor_join(target, source, 30).neighbor_road_temp.iloc[0], 3.)
        self.assertTrue(pd.isna(delayed_neighbor_join(target, source, 60).neighbor_road_temp.iloc[0]))
        self.assertTrue(pd.isna(delayed_neighbor_join(target, source.iloc[:1], 0, 20).neighbor_road_temp.iloc[0]))

    def test_held_station_and_future_winter_excluded(self):
        data = pd.DataFrame({"station": ["A", "B", "A", "B"],
                             "time": pd.to_datetime(["2024-12-01", "2024-12-01", "2025-12-01", "2025-12-01"])})
        train, valid = winter_station_split(data, "A", ["2024-11-01", "2025-02-28"], ["2025-11-01", "2026-02-28"])
        self.assertEqual(train.index.tolist(), [1])
        self.assertEqual(valid.index.tolist(), [2])
        data.loc[1, "station"] = "12410.0"
        with self.assertRaises(ValueError):
            winter_station_split(data, "A", ["2024-11-01", "2025-02-28"], ["2025-11-01", "2026-02-28"])

    def test_duplicate_reference_rejected(self):
        source = pd.DataFrame({"time": pd.to_datetime(["2026-01-01"] * 2), "road_temp": [1., 2.]})
        with self.assertRaises(ValueError):
            delayed_neighbor_join(source[["time"]].iloc[:1], source, 0)


if __name__ == "__main__":
    unittest.main()
