import unittest

import numpy as np
import pandas as pd

from src.physical_features import ThermalContext, source_history


class PhysicalFeatureTests(unittest.TestCase):
    def fixtures(self):
        ids = ["12103", "12209", "12210"]
        source = pd.DataFrame([{"station": sid, "time": pd.Timestamp("2024-11-01 00:00"),
                                "route": "route", "road_temp": float(index), "humidity": 80., "rain_cum": 0.}
                               for index, sid in enumerate(ids)])
        target = pd.DataFrame({"station": ids, "time": pd.to_datetime(["2024-11-01 00:10"] * 3),
                               "aws_dewpoint": [-3.] * 3, "aws_air_temp": [0.] * 3})
        meta = pd.DataFrame({"station": ids, "route": ["route"] * 3,
                             "lat": [35., 35.01, 35.02], "lon": [127.] * 3})
        return target, source, meta

    def test_mutating_excluded_source_does_not_change_any_fold_feature(self):
        target, source, meta = self.fixtures()
        before, refs = ThermalContext(target, source_history(source), meta).features(target, {"12209"})
        source.loc[source.station.eq("12209"), ["road_temp", "humidity"]] = [65., 1.]
        after, _ = ThermalContext(target, source_history(source), meta).features(target, {"12209"})
        pd.testing.assert_frame_equal(before, after)
        self.assertTrue(all(r["source"] not in {r["target"], "12209"} for r in refs))

    def test_no_reference_missing_and_same_time_cannot_enter(self):
        target, source, meta = self.fixtures()
        ctx = ThermalContext(target, source_history(source), meta)
        features, _ = ctx.features(target, {"12103", "12209", "12210"})
        self.assertTrue(features.isna().all().all())
        target["time"] = pd.Timestamp("2024-11-01 00:00")
        features, _ = ThermalContext(target, source_history(source), meta).features(target, set())
        self.assertTrue(features.near_road_temp.isna().all())

    def test_temperature_trend_and_rain_do_not_bridge_missing_slots(self):
        _, source, _ = self.fixtures()
        source = source.iloc[[0]].copy()
        source = pd.concat([source] * 4, ignore_index=True)
        source["time"] = pd.to_datetime(["2024-11-01 23:50", "2024-11-02 00:00", "2024-11-02 00:20", "2024-11-02 00:50"])
        source["road_temp"] = [1., 0., -1., -2.]
        source["rain_cum"] = [2., 0., 1., 2.]
        out = source_history(source)
        self.assertTrue(out.rain10.isna().all())
        self.assertTrue(np.isnan(out.temp_trend60.iloc[2]))
        self.assertEqual(out.temp_trend60.iloc[3], -3.)


if __name__ == "__main__":
    unittest.main()
