import unittest

import pandas as pd

from src.weather_features import prior_join


class PriorJoinTests(unittest.TestCase):
    def test_strict_past_boundary_and_age(self):
        target = pd.DataFrame({"time": pd.to_datetime([
            "2024-11-01 00:00", "2024-11-01 00:10", "2024-11-01 00:20",
            "2024-11-01 02:00"]), "target": [1, 2, 3, 4]})
        source = pd.DataFrame({"source_time": pd.to_datetime([
            "2024-11-01 00:00", "2024-11-01 00:10"]), "air_temp": [5, 6]})
        joined = prior_join(target, source, "aws", tolerance_minutes=60)
        self.assertTrue(pd.isna(joined.iloc[0]["aws_air_temp"]))
        self.assertEqual(joined.iloc[1]["aws_air_temp"], 5)
        self.assertEqual(joined.iloc[2]["aws_air_temp"], 6)
        self.assertTrue(pd.isna(joined.iloc[3]["aws_air_temp"]))
        self.assertEqual(joined.iloc[2]["aws_age_minutes"], 10)


if __name__ == "__main__":
    unittest.main()
