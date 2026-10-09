import unittest
import numpy as np
import pandas as pd

from src.antecedent_dose import integrate_dose, frost_point, AntecedentContext, DOSE_FEATURES
from src.physical_features import source_history


class AntecedentDoseTests(unittest.TestCase):
    def test_exact_integral_and_future_invariance(self):
        time = pd.date_range("2025-01-01", periods=20, freq="10min")
        road = np.full(20, -2.)
        out = integrate_dose(time, road, np.full(20, -1.), 20)
        self.assertAlmostEqual(out[-1, 0], 40 * (1-np.exp(-190/20)))
        self.assertAlmostEqual(out[-1, 1], 20 * (1-np.exp(-190/20)))
        changed = road.copy();changed[12:] = -20
        np.testing.assert_allclose(out[:12], integrate_dose(time, changed, np.full(20, -1.), 20)[:12], equal_nan=True)

    def test_missing_gap_and_zero_do_not_invent_crossings(self):
        time = pd.date_range("2025-01-01", periods=30, freq="10min")
        road = np.full(30, -1.);road[15:18] = [0, 0, 1]
        out = integrate_dose(time, road, road, 20)
        self.assertEqual(out[17, 2], 1.)
        road[16] = np.nan
        road[17:] = 1.
        out = integrate_dose(time, road, road, 20)
        self.assertTrue(np.isnan(out[17, 2]))
        self.assertEqual(out[-1, 2], 0.)
        self.assertLess(out[16, 3], out[15, 3])
        broken = time.delete(16)
        out = integrate_dose(broken, np.delete(road, 16), np.delete(road, 16), 20)
        self.assertTrue(np.isnan(out[16, 0]))
        self.assertLess(out[16, 3], .8)

    def test_frost_point_and_excluded_source_invariance(self):
        self.assertAlmostEqual(frost_point([0.], [100.])[0], 0.)
        self.assertTrue(np.isnan(frost_point([0.], [0.])[0]))
        time = pd.date_range("2025-01-01", periods=30, freq="10min")
        target = pd.DataFrame([{"station": s, "time": t, "aws_dewpoint": -2., "aws_air_temp": -1.}
                               for s in ["12103", "12209", "12210"] for t in time])
        source = source_history(pd.DataFrame([{"station": s, "time": t, "road_temp": -1., "humidity": 90., "rain_cum": 0.}
                                             for s in ["12103", "12209", "12210"] for t in time]))
        metadata = pd.DataFrame({"station": ["12103", "12209", "12210"], "route": ["x"]*3,
                                 "lat": [35., 35.001, 35.02], "lon": [127.]*3})
        weather = pd.DataFrame([{"station": s, "time": t, "aws_air_temp": -1., "aws_humidity": 90.}
                                for s in ["12103", "12209", "12210"] for t in time])
        query = target[target.station.eq("12103")]
        before, refs = AntecedentContext(target, source, metadata, weather).features(query, {"12209"})
        changed = source.copy();changed.loc[changed.station.isin(["12103", "12209"]), "road_temp"] = -30.
        after, _ = AntecedentContext(target, changed, metadata, weather).features(query, {"12209"})
        pd.testing.assert_frame_equal(before, after)
        self.assertTrue(all(r["source"] == "12210" for r in refs))
        self.assertEqual(len(DOSE_FEATURES), 10)
        self.assertTrue(before["near_cold_dose_20m"].notna().any())


if __name__ == "__main__":
    unittest.main()
