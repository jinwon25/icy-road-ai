import unittest
import numpy as np
import pandas as pd

from src.ice_daily_selection import choose_daily_threshold
from src.validation import daily_scores, macro_scores


class DailySelectionTests(unittest.TestCase):
    def test_matches_reference_daily_metric_and_denominators(self):
        data = pd.DataFrame({"station": ["A"] * 4 + ["B"] * 2,
                             "time": pd.to_datetime(["2024-11-01 00:00", "2024-11-01 00:10",
                                                      "2024-11-02 00:00", "2024-11-02 00:10",
                                                      "2024-11-01 00:00", "2024-11-01 00:10"]),
                             "ice": [1, 0, 0, 0, 0, 0]})
        scores = np.array([.8, .3, .6, .1, .1, .1])
        threshold, score, trace = choose_daily_threshold(data, scores, [.2, .5, .7, .9], expected_slots=2)
        self.assertEqual(threshold, .7)
        self.assertEqual(score, 1.)
        for row in trace.itertuples():
            records = [(r.station, r.time, r.ice, int(p >= row.threshold))
                       for r, p in zip(data.itertuples(), scores)]
            reference = macro_scores(daily_scores(records, expected_slots=2))
            self.assertAlmostEqual(row.station_daily_f1, reference['f1'])
            self.assertEqual(row.defined_days, reference['defined_f1_days'])
            self.assertEqual(row.defined_stations, reference['defined_f1_stations'])

    def test_incomplete_positive_days_rejected(self):
        data = pd.DataFrame({'station': ['A'], 'time': pd.to_datetime(['2024-11-01']), 'ice': [1]})
        with self.assertRaises(ValueError):
            choose_daily_threshold(data, [.5])
        with self.assertRaises(ValueError):
            choose_daily_threshold(pd.concat([data, data]), [.5, .5], expected_slots=2)


if __name__ == '__main__':
    unittest.main()
