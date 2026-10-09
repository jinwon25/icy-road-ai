import unittest
import numpy as np
import pandas as pd
from src.physical_features import source_history
from src.surface_state_context_v2 import state_history, SurfaceStateContextV2


class SurfaceStateContextV2Tests(unittest.TestCase):
    def test_unknown_coverage_and_official_code_definition(self):
        time = pd.date_range("2025-01-01", periods=30, freq="10min")
        raw = ["1"]*30;raw[6:12] = ["2", "4", "13", "15", "0", "-999"]
        data = pd.DataFrame({"station": "12103", "time": time, "state_raw": raw})
        out = state_history(data)
        self.assertEqual(out.loc[8, "code_13"], 1.)
        self.assertEqual(out.loc[9, "code_04"], 0.)
        self.assertEqual(out.loc[9, "code_15"], 1.)
        self.assertTrue(np.isnan(out.loc[10, "code_01"]))
        self.assertTrue(np.isnan(out.loc[11, "water_fraction_60m"]))
        self.assertEqual(out.loc[11, "coverage_60m"], 4/6)
        changed = data.copy();changed.loc[15:, "state_raw"] = "4"
        pd.testing.assert_frame_equal(out.iloc[:15], state_history(changed).iloc[:15])

    def test_chemical_and_critical_wet_are_separate(self):
        time = pd.date_range("2025-01-01", periods=18, freq="10min")
        raw = ["12"] * 6 + ["13"] * 6 + ["04"] * 6
        data = pd.DataFrame({"station": "12103", "time": time, "state_raw": raw})
        out = state_history(data)
        self.assertEqual(out.loc[5, "chemical_wet_fraction_60m"], 1.)
        self.assertEqual(out.loc[5, "critical_wet_fraction_60m"], 0.)
        self.assertEqual(out.loc[11, "chemical_wet_fraction_60m"], 0.)
        self.assertEqual(out.loc[11, "critical_wet_fraction_60m"], 1.)
        self.assertEqual(out.loc[11, "ice_fraction_60m"], 0.)
        self.assertEqual(out.loc[17, "ice_fraction_60m"], 1.)

    def test_same_time_and_forbidden_sources_are_excluded(self):
        time = pd.date_range("2025-01-01", periods=30, freq="10min")
        ids = ["12103", "12209", "12210"]
        targets = pd.DataFrame([{"station": sid, "time": t, "aws_air_temp": -1., "aws_dewpoint": -2.} for sid in ids for t in time])
        thermal = source_history(pd.DataFrame([{"station": sid, "time": t, "road_temp": -1., "humidity": 90., "rain_cum": 0.} for sid in ids for t in time]))
        metadata = pd.DataFrame({"station": ids, "route": ["x"]*3, "lat": [35., 35.001, 35.02], "lon": [127.]*3})
        states = pd.DataFrame([{"station": sid, "time": t, "state_raw": "4" if sid == "12210" and t == time[15] else "1"} for sid in ids for t in time])
        query = targets[targets.station.eq("12103")]
        before, refs = SurfaceStateContextV2(targets, thermal, metadata, states).features(query, {"12209"})
        self.assertEqual(before.loc[15, "near_state_code_04"], 0.)
        self.assertEqual(before.loc[16, "near_state_code_04"], 1.)
        changed = states.copy();changed.loc[changed.station.isin(["12103", "12209"]), "state_raw"] = "4"
        after, _ = SurfaceStateContextV2(targets, thermal, metadata, changed).features(query, {"12209"})
        pd.testing.assert_frame_equal(before, after)
        self.assertTrue(all(r["source"] == "12210" for r in refs))
        states.loc[states.station.eq("12103"), "station"] = "12410"
        with self.assertRaises(ValueError):
            SurfaceStateContextV2(targets, thermal, metadata, states)


if __name__ == "__main__":
    unittest.main()
