"""기상 이력의 시간·지점 경계, 결측과 조건별 범위의 누출을 검증한다."""
import unittest
import numpy as np
import pandas as pd

from src.weather_memory_temperature import HISTORY_COLUMNS, weather_history, condition_bins, calibrate_ranges, apply_ranges


def sample(n=90, station='12207'):
    f = pd.DataFrame({'station': station, 'time': pd.date_range('2024-11-01', periods=n, freq='10min'), 'road_temp': 0.})
    for c in HISTORY_COLUMNS:
        f[c] = np.arange(n, dtype=float)
    return f


class WeatherMemoryTests(unittest.TestCase):
    def test_current_and_future_cannot_change_prior_means(self):
        f = sample(); first = weather_history(f)
        changed = f.copy(); changed.loc[30:, list(HISTORY_COLUMNS)] = 9999
        second = weather_history(changed)
        pd.testing.assert_series_equal(first.loc[30].filter(like='past_mean'), second.loc[30].filter(like='past_mean'))
        self.assertEqual(first.loc[30, 'aws_air_temp_past_mean_60m'], np.mean(np.arange(24, 30)))
        self.assertEqual(first.loc[30, 'aws_air_temp_change_60m'], 6.)

    def test_missing_slots_do_not_shorten_expected_coverage(self):
        f = sample().drop(index=[26, 27]); h = weather_history(f)
        self.assertTrue(np.isnan(h.loc[30, 'aws_air_temp_past_mean_60m']))
        # 예정72슬롯의80%에 닿을 때까지12시간 평균을 만들지 않는다.
        self.assertTrue(np.isnan(h.loc[57, 'aws_air_temp_past_mean_720m']))
        self.assertTrue(np.isnan(h.loc[58, 'aws_air_temp_past_mean_720m']))
        self.assertTrue(np.isfinite(h.loc[60, 'aws_air_temp_past_mean_720m']))

    def test_station_isolation_order_and_target_independence(self):
        a, b = sample(), sample(station='12408'); b[list(HISTORY_COLUMNS)] += 1000
        f = pd.concat([a, b], ignore_index=True).sample(frac=1, random_state=2)
        first = weather_history(f)
        f['road_temp'] = 999; f['state_raw'] = '04'
        pd.testing.assert_frame_equal(first, weather_history(f))
        self.assertEqual(first.loc[30, 'aws_air_temp_past_mean_60m'], 26.5)
        self.assertEqual(first.loc[120, 'aws_air_temp_past_mean_60m'], 1026.5)

    def test_exact_lag_is_not_previous_available_row(self):
        f = sample().drop(index=24); h = weather_history(f)
        self.assertTrue(np.isnan(h.loc[30, 'aws_air_temp_change_60m']))

    def test_forbidden_time_station_and_infinite_weather_rejected(self):
        for station in ['12410', '23102']:
            with self.assertRaises(ValueError): weather_history(sample(station=station))
        f = sample(); f['time'] += pd.DateOffset(years=1)
        with self.assertRaises(ValueError): weather_history(f)
        f = sample(); f.loc[0, 'aws_air_temp'] = np.inf
        with self.assertRaises(ValueError): weather_history(f)

    def test_condition_boundaries_use_prediction_and_clock_only(self):
        f = sample(6); f['time'] = pd.to_datetime(['2024-11-01 05:50', '2024-11-01 06:00', '2024-11-01 17:50', '2024-11-01 18:00', '2024-11-01 18:10', '2024-11-01 18:20'])
        p = [-2.1, -2., 2., 2.1, 0., np.nan]
        self.assertEqual(condition_bins(f, p).tolist(), ['cold_night', 'transition_day', 'transition_day', 'warm_night', 'transition_night', None])
        f.road_temp = 100
        self.assertEqual(condition_bins(f, p).tolist()[0], 'cold_night')

    def test_sparse_regime_uses_global_station_balanced_radius(self):
        f = pd.concat([sample(10), sample(10, station='12408')], ignore_index=True)
        f.road_temp = np.r_[np.ones(10), np.repeat(3., 10)]; p = np.zeros(20)
        cal = calibrate_ranges(f, p, True)
        self.assertEqual(cal['global']['radius'], 3.)
        self.assertTrue(all(x['fallback_to_global'] for x in cal['conditions'].values()))
        query = sample(1); query.road_temp = 1e9
        lo, hi = apply_ranges(query, [0], cal)
        np.testing.assert_array_equal(lo, [-3]); np.testing.assert_array_equal(hi, [3])

    def test_supported_conditions_keep_distinct_residual_scales(self):
        f = pd.concat([sample(1500), sample(1500, station='12408')], ignore_index=True)
        day = f.time.dt.hour.between(6, 17).to_numpy()
        f.road_temp = np.where(day, 4., 1.)
        cal = calibrate_ranges(f, np.zeros(len(f)), True)
        self.assertFalse(cal['conditions']['transition_day']['fallback_to_global'])
        self.assertEqual(cal['conditions']['transition_day']['radius'], 4.)
        self.assertEqual(cal['conditions']['transition_night']['radius'], 1.)


if __name__ == '__main__':
    unittest.main()
