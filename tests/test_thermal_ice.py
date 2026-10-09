"""정답·시각·분모와 희소 단일 사건을 보존하는 고정 물리 진단을 검증한다."""
import unittest
import numpy as np
import pandas as pd

from src.thermal_ice import (confusion, diagnostic_report, evaluate_fixed_policies,
                             fixed_thermal_rule, validate_development)


class ThermalIceTests(unittest.TestCase):
    def test_unknown_moisture_and_temperature_return_to_baseline(self):
        f = pd.DataFrame({'aws_dewpoint': [np.nan, -2., np.nan, -2., -2.],
                          'rain15_max_3h': [np.nan, np.nan, 1., 0., 0.],
                          'asos_snow_cm': [np.nan, 0., np.nan, 0., 0.]})
        p, fallback, _ = fixed_thermal_rule([-1., -1., -1., np.nan, 1.], f, [1, 1, 0, 1, 1], True)
        self.assertEqual(p.tolist(), [1, 0, 1, 1, 0])
        self.assertEqual(fallback.tolist(), [True, False, False, True, False])
        f['ice'] = 1
        f['road_temp'] = -1000.
        self.assertEqual(fixed_thermal_rule([-1.] * 5, f, [1] * 5, True)[0].tolist(), [1, 0, 1, 0, 0])

    def test_freezing_boundary_and_snow_evidence(self):
        f = pd.DataFrame({'aws_dewpoint': [-1., -1., np.nan],
                          'rain15_max_3h': [0., 0., np.nan], 'asos_snow_cm': [1., 1., 1.]})
        p, _, _ = fixed_thermal_rule([0., .01, -2.], f, [0, 0, 0], True)
        self.assertEqual(p.tolist(), [1, 0, 1])

    def test_protected_future_duplicates_and_off_grid_fail(self):
        f = pd.DataFrame({'station': ['12207'], 'time': pd.to_datetime(['2024-11-01'])})
        for changed in [f.assign(station='12410.0'), f.assign(time=pd.Timestamp('2025-11-01')),
                        f.assign(time=pd.NaT), f.assign(time=pd.Timestamp('2024-11-01 00:05')),
                        pd.concat([f, f.assign(station='12207.0')])]:
            with self.assertRaises(ValueError):
                validate_development(changed)
        utc = f.assign(time=pd.Timestamp('2024-10-31 15:00', tz='UTC'))
        self.assertEqual(validate_development(utc).time.iloc[0], f.time.iloc[0])

    def test_fixed_days_unknown_labels_and_single_slot_events(self):
        f = pd.DataFrame({'station': '12207', 'time': pd.date_range('2024-11-01', periods=432, freq='10min'), 'ice': 0.})
        f.loc[[0, 2, 144, 145], 'ice'] = 1.
        f.loc[300, 'ice'] = np.nan
        p = np.zeros(len(f), dtype=int)
        p[[0, 144]] = 1
        result, _, daily, _ = diagnostic_report(f, p)
        self.assertEqual((result['n'], result['tp'], result['fn']), (431, 2, 2))
        self.assertEqual((result['complete_days'], result['fixed_ice_days']), (2, 2))
        self.assertEqual((result['events'], result['detected_events']), (3, 2))
        self.assertEqual((result['single_slot_events'], result['detected_single_slot_events']), (2, 1))
        self.assertAlmostEqual(result['fixed_ice_day_f1'], 2 / 3)
        self.assertEqual(len(daily), 2)
        self.assertIsNone(confusion([0, np.nan], [0, 1])['f1'])
        self.assertIsNone(confusion([1], [0])['precision'])

    def test_official_codes_and_same_population_for_all_policies(self):
        f = pd.DataFrame({'station': '12207', 'time': pd.date_range('2024-11-01', periods=5, freq='10min'),
                          'state_raw': ['04', '13', '15', '00', '-999'], 'ice': [1., 0., 0., np.nan, np.nan],
                          'baseline_ice': [0, 1, 1, 1, 1], 'baseline_weather': -1., 'selected_weather': -1.,
                          'aws_dewpoint': -1., 'rain15_max_3h': 0., 'asos_snow_cm': 0.})
        result, _, _, _, _ = evaluate_fixed_policies(f)
        self.assertEqual({v['n'] for v in result.values()}, {3})
        self.assertEqual(result['hgb_cold_moisture']['fp'], 2)
        with self.assertRaisesRegex(ValueError, 'official 04'):
            evaluate_fixed_policies(f.assign(ice=[1, 1, 0, np.nan, np.nan]))


if __name__ == '__main__':
    unittest.main()
