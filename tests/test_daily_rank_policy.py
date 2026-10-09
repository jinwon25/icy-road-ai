import unittest
import numpy as np
import pandas as pd
from src.daily_rank_policy import capped_daily_scores


class DailyRankTests(unittest.TestCase):
    def test_caps_by_station_day_without_labels(self):
        frame = pd.DataFrame({"station": ["A", "A", "A", "B"], "time": pd.to_datetime(["2025-01-01 10:00", "2025-01-01 11:00", "2025-01-02 10:00", "2025-01-01 11:00"]), "ice": [1, 0, 1, 0]})
        got = capped_daily_scores(frame, [.2, .8, .1, .3], 1)
        np.testing.assert_array_equal(got, [-1, .8, .1, .3])
        frame["ice"] = 1-frame.ice
        np.testing.assert_array_equal(got, capped_daily_scores(frame, [.2, .8, .1, .3], 1))

    def test_ties_time_order_and_input_order(self):
        frame = pd.DataFrame({"station": ["A", "A"], "time": pd.to_datetime(["2025-01-01 11:00", "2025-01-01 10:00"])})
        np.testing.assert_array_equal(capped_daily_scores(frame, [.5, .5], 1), [-1, .5])


if __name__ == "__main__":
    unittest.main()
