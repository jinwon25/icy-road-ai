import unittest
import numpy as np
import pandas as pd
from src.moisture_memory import moisture_memory, MEMORY_FEATURES


class MoistureMemoryTests(unittest.TestCase):
    def source(self):
        return pd.DataFrame({"station": ["A"]*4, "source_time": pd.to_datetime(["2025-01-01 00:00", "2025-01-01 00:10", "2025-01-01 00:20", "2025-02-01 00:00"]),
                             "air_temp": [1., -1., -2., np.nan], "humidity": [50., 90., 95., np.nan], "dewpoint": [0., -2., -2., np.nan], "rain_15m": [1., 0., 0., np.nan]})

    def test_future_changes_do_not_change_past(self):
        data = self.source()
        before = moisture_memory(data)
        data.loc[2:, ["air_temp", "rain_15m", "humidity", "dewpoint"]] = 5.
        after = moisture_memory(data)
        pd.testing.assert_frame_equal(before.iloc[:2], after.iloc[:2])

    def test_gap_is_unknown_not_dry(self):
        out = moisture_memory(self.source())
        self.assertTrue(np.isnan(out.rain15_max_72h.iloc[-1]))
        self.assertTrue(np.isnan(out.wet_fraction_72h.iloc[-1]))
        self.assertTrue(np.isnan(out.last_wet_age_72h.iloc[-1]))
        self.assertEqual(out.rain_coverage_72h.iloc[-1], 0.)
        self.assertAlmostEqual(out.last_wet_age_72h.iloc[2], 1/3)
        self.assertAlmostEqual(out.freezing_fraction_24h.iloc[2], 2/3)

    def test_station_isolation(self):
        a = self.source(); b = a.copy(); b["station"] = "B"; b["rain_15m"] = 0.
        out = moisture_memory(pd.concat([a,b],ignore_index=True))
        self.assertTrue(out.loc[out.station.eq("B"), "last_wet_age_72h"].isna().all())


if __name__ == "__main__":
    unittest.main()
