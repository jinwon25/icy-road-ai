"""Boundary checks for exploratory spatial and prior-weather features."""
from __future__ import annotations

import unittest

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, box

from scripts.audit_ice_weather_history import source_history
from scripts.build_static_station_features import _distance


class FollowupFeatureTests(unittest.TestCase):
    def test_history_uses_only_three_hours_up_to_source_time(self):
        frame = pd.DataFrame({
            "station": ["A"] * 4,
            "source_time": pd.to_datetime(["2025-01-01 00:00", "2025-01-01 01:00",
                                           "2025-01-01 03:00", "2025-01-01 04:10"]),
            "air_temp": [1.0, -2.0, 0.0, 3.0],
            "humidity": [70.0, 90.0, 80.0, 60.0],
            "dewpoint": [-1.0, -3.0, -2.0, 0.0],
            "rain_15m": [0.5, 0.0, np.nan, 0.0],
        })
        result = source_history(frame)
        self.assertEqual(result.air_min_3h.tolist(), [1.0, -2.0, -2.0, 0.0])
        self.assertEqual(result.wet_observations_3h.tolist(), [1.0, 1.0, 1.0, 0.0])
        self.assertEqual(result.rain15_max_3h.iloc[3], 0.0)
        self.assertEqual(result.air_observations_3h.tolist(), [1.0, 2.0, 3.0, 2.0])

    def test_facility_distance_is_geometry_distance(self):
        polygons = gpd.GeoDataFrame(geometry=[box(0, 0, 10, 10), box(100, 0, 110, 10)],
                                    crs="EPSG:5179")
        self.assertEqual(_distance(Point(5, 5), polygons), 0.0)
        self.assertAlmostEqual(_distance(Point(20, 5), polygons), 10.0)


if __name__ == "__main__":
    unittest.main()
