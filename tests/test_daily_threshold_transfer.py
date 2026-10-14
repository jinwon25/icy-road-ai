import unittest
import pandas as pd
from scripts.evaluate_daily_threshold_transfer import report, select_inner_threshold


class DailyThresholdTransferTests(unittest.TestCase):
    def test_outer_station_cannot_select_itself(self):
        data = pd.DataFrame({'station': ['A'], 'time': pd.to_datetime(['2024-11-01']),
                             'ice': [1], 'baseline_score': [.5], 'baseline_prediction': [1]})
        with self.assertRaises(ValueError): select_inner_threshold(data, {'A'})

    def test_complete_day_false_alarm_and_undefined_station_denominators(self):
        times = pd.date_range('2024-11-01', periods=144, freq='10min')
        data = pd.DataFrame({'station': ['A'] * 144 + ['B'] * 144,
                             'time': list(times) * 2, 'ice': [1] + [0] * 287})
        result = report(data, [1] + [0] * 287)
        self.assertEqual(result['daily']['f1'], 1.)
        self.assertEqual(result['daily']['defined_f1_stations'], 1)
        self.assertEqual(result['fixed_station_daily_f1_undefined_zero'], .5)
        self.assertEqual(result['actual_ice_days'], 1)
        self.assertEqual(result['events']['singleton_detected'], 1)

    def test_singleton_gap_and_unknown_boundaries(self):
        data = pd.DataFrame({'station': ['A'] * 4,
                             'time': pd.to_datetime(['2024-11-01 00:00', '2024-11-01 00:10',
                                                     '2024-11-01 00:20', '2024-11-01 00:40']),
                             'ice': [1, None, 1, 1]})
        result = report(data, [1, 0, 0, 1])
        self.assertEqual(result['events']['singleton_events'], 3)
        self.assertEqual(result['events']['singleton_detected'], 2)
        self.assertEqual(result['slot']['n'], 3)


if __name__ == '__main__': unittest.main()
