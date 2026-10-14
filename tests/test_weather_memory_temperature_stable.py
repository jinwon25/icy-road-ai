"""전체 겨울·최소 준비 입력의 정확한 동일성과 고정소수점 시간 경계를 검사한다."""
import unittest
import numpy as np
import pandas as pd

from src.weather_memory_temperature_stable import HISTORY_COLUMNS, weather_history


def data(n=1500):
    f = pd.DataFrame({'station': '12207', 'time': pd.date_range('2024-11-01', periods=n, freq='10min')})
    random = np.random.default_rng(13)
    for c in HISTORY_COLUMNS: f[c] = random.normal(10, 3, n)
    return f


class StableHistoryTests(unittest.TestCase):
    def test_warmup_and_full_history_are_bit_identical(self):
        f = data(); full = weather_history(f)
        short = weather_history(f.loc[928:1143])
        pd.testing.assert_frame_equal(full.loc[1000:1143], short.loc[1000:1143], check_exact=True)

    def test_missing_values_and_gaps_do_not_change_batch_invariance(self):
        f = data(); f.loc[970:978, 'aws_dewpoint'] = np.nan; f = f.drop(index=[931, 934, 991])
        full = weather_history(f); short = weather_history(f.loc[928:1143])
        pd.testing.assert_frame_equal(full.loc[1000:1143], short.loc[1000:1143], check_exact=True)

    def test_time_endpoints_and_expected_slot_coverage(self):
        f = data(30)
        for c in HISTORY_COLUMNS: f[c] = np.arange(30, dtype=float)
        f.loc[24, 'aws_air_temp'] = np.nan
        h = weather_history(f)
        self.assertEqual(h.loc[29, 'aws_air_temp_past_mean_60m'], np.mean([23, 25, 26, 27, 28]))
        self.assertEqual(h.loc[29, 'aws_air_temp_change_60m'], 6.)
        f.loc[25, 'aws_air_temp'] = np.nan
        self.assertTrue(np.isnan(weather_history(f).loc[29, 'aws_air_temp_past_mean_60m']))

    def test_future_and_target_do_not_enter_history(self):
        f = data(); a = weather_history(f)
        f['road_temp'] = 999; f.loc[1100:, list(HISTORY_COLUMNS)] = 999
        b = weather_history(f)
        pd.testing.assert_frame_equal(a.loc[:1099], b.loc[:1099], check_exact=True)
        pd.testing.assert_series_equal(a.loc[1100].filter(like='past_mean'), b.loc[1100].filter(like='past_mean'), check_exact=True)


if __name__ == '__main__': unittest.main()
