import unittest

import numpy as np

from scripts.baseline_ice_logistic import choose_threshold
from scripts.audit_ice_events import canonical_code, neighbor
import pandas as pd


class IceThresholdTests(unittest.TestCase):
    def test_threshold_uses_inner_scores_and_detects_positive(self):
        labels = np.array([1, 0, 0, 0])
        scores = np.array([0.8, 0.7, 0.2, -0.5])
        threshold, f1 = choose_threshold(labels, scores)
        self.assertAlmostEqual(threshold, 0.8)
        self.assertAlmostEqual(f1, 1.0)

    def test_threshold_cannot_be_set_without_positive(self):
        with self.assertRaises(ValueError):
            choose_threshold(np.array([0, 0]), np.array([0.2, 0.1]))

    def test_event_neighbor_requires_exact_ten_minutes(self):
        current = pd.Timestamp("2024-11-01 01:00:00")
        previous = pd.Series({"time": current - pd.Timedelta(minutes=10),
                              "state_raw": "12.0", "ice": 0})
        gap = pd.Series({"time": current - pd.Timedelta(minutes=20),
                         "state_raw": "12.0", "ice": 0})
        self.assertEqual(canonical_code("12.0"), "12")
        self.assertEqual(neighbor(previous, current, -1), ("12.0", 0))
        self.assertEqual(neighbor(gap, current, -1), (None, None))


if __name__ == "__main__":
    unittest.main()
