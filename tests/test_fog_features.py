import unittest

import pandas as pd

from src.fog_features import attach_fog


class FogFeatureTests(unittest.TestCase):
    def fixtures(self):
        targets = pd.DataFrame({"station": ["12103"] * 4 + ["23201"],
                                "route": [" 서해안"] * 4 + ["호남선"],
                                "time": pd.to_datetime(["2024-11-01 00:10", "2024-11-01 00:20",
                                                        "2024-11-01 00:40", "2024-11-01 01:00",
                                                        "2024-11-01 00:20"]),
                                "ice": [0, 1, 0, 0, 1]})
        meta = pd.DataFrame({"station": ["12103", "23201"], "route": ["서해안", " 호남선"],
                             "lat": [35.5, 35.9], "lon": [126.7, 127.]})
        fog = pd.DataFrame({"station": ["12306"] * 3, "route": [" 서해안"] * 3,
                            "lat": [35.5] * 3, "lon": [126.7] * 3,
                            "source_time": pd.to_datetime(["2024-11-01 00:00", "2024-11-01 00:10",
                                                            "2024-11-01 00:20"]),
                            "visibility_m": [500., 200., float("nan")]})
        return targets, meta, fog

    def test_prior_gap_no_cross_route_and_same_denominator(self):
        target, meta, fog = self.fixtures()
        result = attach_fog(target, meta, fog)
        self.assertEqual(len(result), len(target))
        self.assertEqual(result.ice.tolist(), target.ice.tolist())
        self.assertEqual(result.fog_visibility_m.iloc[:3].tolist(), [500., 200., 200.])
        self.assertTrue(result.fog_visibility_m.iloc[3:].isna().all())
        self.assertTrue(pd.isna(result.fog_station.iloc[4]))
        self.assertEqual(result.fog_age_minutes.iloc[:3].tolist(), [10., 10., 30.])

    def test_delay_and_protected_station_guard(self):
        target, meta, fog = self.fixtures()
        result = attach_fog(target, meta, fog, delay_minutes=20)
        self.assertTrue(pd.isna(result.fog_visibility_m.iloc[0]))
        self.assertEqual(result.fog_visibility_m.iloc[1], 500.)
        target.loc[0, "station"] = "12410"
        with self.assertRaises((AssertionError, ValueError)):
            attach_fog(target, meta, fog)


if __name__ == "__main__":
    unittest.main()
