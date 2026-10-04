import unittest
from datetime import datetime, timezone

from src.validation import (assert_training_stations, binary_metrics, canonical_station_id, daily_scores,
                            macro_scores, normalize_state, regression_metrics,
                            route_macro_scores)


class ValidationTests(unittest.TestCase):
    def test_state_codes(self):
        self.assertIsNone(normalize_state("0"))
        self.assertIsNone(normalize_state("-999"))
        self.assertEqual(normalize_state("4"), 1)
        self.assertEqual(normalize_state("4.0"), 1)
        self.assertEqual(normalize_state("13"), 0)
        self.assertEqual(normalize_state("15"), 0)
        self.assertIsNone(normalize_state("99"))
        self.assertIsNone(normalize_state("13.1"))
        self.assertIsNone(normalize_state(""))

    def test_regression_bias_sign_and_missing(self):
        self.assertEqual(regression_metrics([0, 2, None], [1, 3, 9]),
                         {"n": 2, "bias": 1.0, "mae": 1.0, "rmse": 1.0})

    def test_binary_undefined_and_zero(self):
        none_day = binary_metrics([0, 0], [0, 0])
        self.assertIsNone(none_day["f1"])
        self.assertIsNone(none_day["precision"])
        self.assertIsNone(none_day["recall"])
        missed = binary_metrics([1, 0], [0, 0])
        self.assertEqual(missed["f1"], 0)
        self.assertEqual(missed["recall"], 0)
        self.assertIsNone(missed["precision"])

    def test_kst_boundary_and_missing_slot(self):
        records = [("A", datetime(2024, 11, 1, 15, 0, tzinfo=timezone.utc), 1, 1),
                   ("A", "2024-11-02 00:10:00", None, 0)]
        scores = daily_scores(records, expected_slots=2, minimum_coverage=0.5)
        self.assertEqual(len(scores), 1)
        self.assertEqual(scores[0]["date_kst"], "2024-11-02")
        self.assertEqual(scores[0]["valid_slots"], 1)
        self.assertEqual(scores[0]["f1"], 1)
        self.assertFalse(daily_scores(records, expected_slots=2, minimum_coverage=1)[0]["accepted"])

    def test_any_ice_daily_candidate(self):
        records = [("A", "2024-11-01 00:00:00", 1, 0),
                   ("A", "2024-11-01 00:10:00", 0, 0)]
        result = daily_scores(records, unit="any_ice_per_day", expected_slots=2)
        self.assertEqual(result[0]["n"], 1)
        self.assertEqual(result[0]["f1"], 0)
        self.assertEqual(result[0]["recall"], 0)

    def test_macro_station_weighting(self):
        records = [("A", "2024-11-01 00:00:00", 1, 1),
                   ("A", "2024-11-02 00:00:00", 1, 1),
                   ("B", "2024-11-01 00:00:00", 1, 0)]
        scores = daily_scores(records, expected_slots=1)
        self.assertEqual(macro_scores(scores, station_first=True)["f1"], 0.5)
        self.assertAlmostEqual(macro_scores(scores, station_first=False)["f1"], 2 / 3)

    def test_official_no_ice_days_excluded_but_false_alarm_days_retained(self):
        records = [("A", "2024-11-01 00:00:00", 1, 1),
                   ("A", "2024-11-02 00:00:00", 0, 0),
                   ("A", "2024-11-03 00:00:00", 0, 1)]
        result = macro_scores(daily_scores(records, expected_slots=1))
        self.assertEqual(result["defined_f1_days"], 2)
        self.assertEqual(result["f1"], 0.5)

    def test_route_macro_candidate(self):
        records = [("A", "2024-11-01 00:00:00", 1, 1),
                   ("B", "2024-11-01 00:00:00", 1, 1),
                   ("C", "2024-11-01 00:00:00", 1, 0)]
        scores = daily_scores(records, expected_slots=1)
        self.assertAlmostEqual(macro_scores(scores)["f1"], 2 / 3)
        routed = route_macro_scores(scores, {"A": "west", "B": "west", "C": "east"})
        self.assertEqual(routed["f1"], 0.5)

    def test_protected_station_guard(self):
        with self.assertRaises(ValueError):
            assert_training_stations(["12103", "12410.0"])
        self.assertEqual(canonical_station_id("NaN"), "<missing>")


if __name__ == "__main__":
    unittest.main()
