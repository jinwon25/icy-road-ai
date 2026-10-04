import unittest
from datetime import date

import pandas as pd

from src.weather_inputs import filter_aws_nominal_day


class AwsInputTests(unittest.TestCase):
    def test_nominal_day_preserves_values_and_kst(self):
        columns = ["time", "station"] + [f"value_{i}" for i in range(19)]
        rows = [
            ["2024-11-01 00:00:00", "123.0", "0.0"] + [""] * 18,
            ["2024-11-01 00:10:00", "", ""] + [""] * 18,
            ["2024-11-02 00:00:00", "123", "0"] + [""] * 18,
        ]
        cleaned, counts = filter_aws_nominal_day(pd.DataFrame(rows, columns=columns), date(2024, 11, 1))
        self.assertEqual(counts["retained_rows"], 1)
        self.assertEqual(counts["missing_station_rows"], 1)
        self.assertEqual(counts["valid_station_outside_nominal_day"], 1)
        self.assertEqual(cleaned.iloc[0]["station_id"], "123")
        self.assertEqual(cleaned.iloc[0]["value_0"], "0.0")
        self.assertEqual(str(cleaned.iloc[0]["source_time_kst"].tz), "Asia/Seoul")

    def test_invalid_time_is_accounted_without_imputation(self):
        columns = ["time", "station"] + [f"value_{i}" for i in range(19)]
        frame = pd.DataFrame([["invalid", "123"] + [""] * 19], columns=columns)
        cleaned, counts = filter_aws_nominal_day(frame, date(2024, 11, 1))
        self.assertEqual(len(cleaned), 0)
        self.assertEqual(counts["valid_station_invalid_timestamp"], 1)
        self.assertEqual(counts["retained_rows"], 0)
    def test_duplicate_station_time_raises(self):
        columns = ["time", "station"] + [f"value_{i}" for i in range(19)]
        rows = [["2024-11-01 00:00:00", station] + [""] * 19 for station in ("123", "123.0")]
        with self.assertRaisesRegex(ValueError, "Duplicate AWS station/time"):
            filter_aws_nominal_day(pd.DataFrame(rows, columns=columns), date(2024, 11, 1))


if __name__ == "__main__":
    unittest.main()
