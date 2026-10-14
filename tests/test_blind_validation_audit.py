import unittest
import numpy as np
import pandas as pd

from scripts.audit_temperature_blind_validation import reference_observations, reference_ice


class BlindAuditTests(unittest.TestCase):
    def test_raw_unknown_states_not_converted_to_negatives(self):
        header = '\n'.join(f'# {i}. {c}: description' for i, c in enumerate(['TM', 'STN_ID', 'SFS', 'TR1', 'LAT', 'LON'], 1))
        body = header + '\n' + '\n'.join(
            f'2024110100{i * 10:02d},12406,{state},{temp},36.9426,126.7921'
            for i, (state, temp) in enumerate([('04', '1.2'), ('13', '-99.9'), ('05', '0.5'), ('-999', '0.1')]))
        result = reference_observations(body, '12406', pd.Timestamp('2024-11-01'), pd.Timestamp('2024-11-01 23:59'))
        np.testing.assert_allclose(result.ice, [1, 0, np.nan, np.nan], equal_nan=True)
        self.assertTrue(np.isnan(result.road_temp.iloc[1]))
        with self.assertRaises(ValueError):
            reference_observations(body, '23405', pd.Timestamp('2024-11-01'), pd.Timestamp('2024-11-01 23:59'))

    def test_partial_day_unknown_break_and_singleton_events(self):
        frame = pd.DataFrame({'station': ['A'] * 6,
                              'time': pd.date_range('2024-11-01', periods=6, freq='10min'),
                              'ice': [1, 1, np.nan, 1, 0, 1], 'prediction': [1, 0, 1, 0, 1, 1]})
        result = reference_ice(frame, 'prediction')
        self.assertEqual((result['n'], result['tp'], result['fp'], result['fn']), (5, 2, 1, 2))
        self.assertEqual((result['events'], result['detected_events'], result['single_slot_events'], result['detected_single_slot_events']), (3, 2, 2, 1))
        self.assertEqual(result['complete_days'], 0)
        self.assertIsNone(result['provisional_daily_station_f1'])

    def test_official_day_population_differs_from_actual_ice_days(self):
        frame = pd.DataFrame({'station': ['A'] * 288,
                              'time': pd.date_range('2024-11-01', periods=288, freq='10min'),
                              'ice': np.zeros(288), 'prediction': np.zeros(288, dtype=int)})
        frame.loc[0, ['ice', 'prediction']] = 1
        frame.loc[144, 'prediction'] = 1
        result = reference_ice(frame, 'prediction')
        self.assertEqual(result['complete_days'], 2)
        self.assertEqual(result['fixed_ice_days'], 1)
        self.assertEqual(result['false_alarm_nonice_days'], 1)
        self.assertEqual(result['provisional_daily_station_f1'], .5)
        self.assertEqual(result['fixed_ice_day_f1'], 1.)


if __name__ == '__main__':
    unittest.main()
