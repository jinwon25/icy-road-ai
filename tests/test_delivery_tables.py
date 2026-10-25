import unittest
import numpy as np
import pandas as pd

from src.delivery_tables import daily_prediction_table, segment_correlations, classification_tables, temperature_table, two_winter_tables


class DeliveryTableTests(unittest.TestCase):
    def test_two_winter_runtime_missing_is_excluded_from_coverage(self):
        f=pd.concat([pd.DataFrame({'station':'12207','winter':year,
            'time':pd.date_range(f'{year}-11-01',periods=144,freq='10min'),
            'ice':1.,'road_temp':0.,'temperature_both':1.,'physical_both':1.,
            'physical_first':0.,'pred_asos':1.,'pred_selected':0.}) for year in [2024,2025]],ignore_index=True)
        f.loc[0,'physical_both']=np.nan
        days,stations,scores,temperatures=two_winter_tables(f)
        current=days.loc[days.method.eq('current')&days.min_valid_slots.eq(144)]
        first=current.loc[current.date_kst.eq('2024-11-01')].iloc[0]
        self.assertEqual(first.valid_slots,143)
        self.assertFalse(first.coverage_accepted)
        summary=scores.loc[scores.method.eq('current')&scores.min_valid_slots.eq(144)].iloc[0]
        self.assertEqual(summary.f1_fixed_population,1.)
        self.assertEqual(summary.missing_prediction_rows,1)
        self.assertEqual(summary.known_positive_rows_without_prediction,1)
        self.assertEqual(len(current),240)
        self.assertEqual(temperatures.iloc[0].mae_c,1.)

    def predictions(self, values):
        return pd.DataFrame({'time': pd.date_range('2024-11-01', periods=len(values), freq='10min'),
            'predicted_ice': values, 'estimated_road_temp_c': [np.nan]*len(values)})

    def test_missing_prediction_is_not_zero_exposure(self):
        missing = daily_prediction_table(self.predictions([np.nan, np.nan])).iloc[0]
        self.assertTrue(pd.isna(missing.cold_wet_hours))
        self.assertTrue(pd.isna(missing.cold_wet_fraction))
        self.assertEqual(missing.missing_ice_slots, 144)
        dry = daily_prediction_table(self.predictions([0, 0])).iloc[0]
        self.assertEqual(dry.cold_wet_hours, 0)
        self.assertEqual(dry.missing_ice_slots, 142)

    def test_partial_day_uses_valid_slot_denominator(self):
        row = daily_prediction_table(self.predictions([1, 0, np.nan])).iloc[0]
        self.assertEqual(row.cold_wet_fraction, .5)
        self.assertEqual(row.cold_wet_hours, 1/6)
        self.assertFalse(row.complete_day)

    def test_invalid_time_and_label_fail(self):
        for change in ('duplicate', 'offset', 'label', 'timezone'):
            f = self.predictions([0, 1])
            if change == 'duplicate': f.loc[1, 'time'] = f.loc[0, 'time']
            if change == 'offset': f['time'] += pd.Timedelta(seconds=1)
            if change == 'label': f.loc[0, 'predicted_ice'] = 2
            if change == 'timezone': f['time'] = f.time.dt.tz_localize('Asia/Seoul')
            with self.subTest(change=change), self.assertRaises(ValueError): daily_prediction_table(f)

    def test_daily_missed_day_metric_denominators_remain_distinct(self):
        f = pd.DataFrame({'station': ['12207']*3,
            'time': pd.to_datetime(['2024-11-01', '2024-11-02', '2024-11-03']),
            'ice': [1, 0, 0], 'current': [0, 1, 0]})
        days, stations, summary = classification_tables(f, ['current'], ['12207'], thresholds=(1,))
        st = stations.iloc[0]
        self.assertEqual(st.precision_days, 1)
        self.assertEqual(st.recall_days, 1)
        self.assertEqual(st.f1_days, 2)
        self.assertEqual(st.f1, 0)
        self.assertFalse(summary.iloc[0].official_competition_score)
        self.assertEqual(int(days.included_f1.sum()), 2)

    def test_protected_development_rejected(self):
        f = pd.DataFrame({'station': ['12410'], 'time': [pd.Timestamp('2024-11-01')],
            'road_temp': [0.], 'equal_nohistory_pair': [1.]})
        with self.assertRaises(ValueError): temperature_table(f)

    def test_temperature_error_sign_and_missing_pairs(self):
        f = pd.DataFrame({'station': ['12207']*3, 'time': pd.date_range('2024-11-01', periods=3, freq='10min'),
            'road_temp': [1., 1., 1.], 'equal_nohistory_pair': [3., 0., np.nan]})
        row = temperature_table(f).iloc[0]
        self.assertEqual(row.bias_c, .5)
        self.assertEqual(row.mae_c, 1.5)
        self.assertEqual(row.missing_pairs, 1)
        self.assertAlmostEqual(row.rmse_c, np.sqrt(2.5))

    def test_shared_weather_and_constant_correlations_are_explicit(self):
        f = pd.DataFrame({'scale_m': [500]*4, 'winter': [2024]*4, 'seg_id': list('abcd'),
            'prediction_group': ['one', 'one', 'two', 'two'],
            'bridge_code_fraction': [0., 1., 0., 1.], 'tunnel_code_fraction': [0.]*4,
            'point_lat': [35., 36., 37., 38.], 'point_lon': [127.]*4,
            'asos_distance_km': [1., 2., 3., 4.], 'aws_distance_km_max': [1.]*4,
            'cold_wet_fraction': [.1, .1, .2, .2], 'estimated_temp_mean_c': [1., 1., 2., 2.]})
        c = segment_correlations(f)
        self.assertTrue(c.unique_weather_groups.eq(2).all())
        self.assertFalse(c.independent_samples.any())
        self.assertTrue(c.loc[c.predictor.eq('tunnel_code_fraction'), 'correlation'].isna().all())
        with self.assertRaises(ValueError): segment_correlations(pd.concat([f, f.iloc[:1]]))


if __name__ == '__main__':
    unittest.main()
