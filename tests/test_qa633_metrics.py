import unittest
import numpy as np
import pandas as pd
from src.qa633_metrics import daily_table, aggregate


def day(station='12207', date='2024-11-01', y=None, p=None):
    f = pd.DataFrame({'station': station, 'time': pd.date_range(date, periods=144, freq='10min'), 'ice': np.zeros(144)})
    f['p'] = np.zeros(144)
    for ids, value in (y or []): f.loc[ids, 'ice'] = value
    for ids, value in (p or []): f.loc[ids, 'p'] = value
    return f


def score(f, pop=('12207',), threshold=144, end='2024-11-03'):
    d = daily_table(f, f.p, pop, threshold, '2024-11-01', end)
    return d, *aggregate(d, pop)


class Qa633Tests(unittest.TestCase):
    def test_nanosecond_off_grid_observation_rejected(self):
        f=day(); f.loc[0,'time']+=pd.Timedelta(nanoseconds=1)
        with self.assertRaises(ValueError): score(f)

    def test_missed_day_excludes_precision_but_keeps_zero_recall_f1(self):
        f = pd.concat([day(), day(date='2024-11-02', y=[([0], 1)])], ignore_index=True)
        d, s, st = score(f)
        self.assertEqual(d.valid_slots.tolist(), [144, 144])
        self.assertTrue(d.precision.isna().all()); self.assertTrue(np.isnan(d.iloc[0].f1))
        self.assertEqual(d.iloc[1].recall, 0); self.assertEqual(d.iloc[1].f1, 0)
        self.assertEqual(s['precision_days'], 0); self.assertEqual(s['f1_days'], 1)
        self.assertEqual(s['f1_all_population_station_mean'], 0.)

    def test_false_alarm_day_retains_zero_precision_f1_and_null_recall(self):
        d, s, _ = score(day(p=[([0], 1)]), end='2024-11-02')
        self.assertEqual(d.iloc[0].precision, 0.); self.assertEqual(d.iloc[0].f1, 0.)
        self.assertTrue(np.isnan(d.iloc[0].recall)); self.assertFalse(s['false_alarm_only_recall_explicitly_answered'])

    def test_station_mean_is_not_pooled_day_mean_or_harmonic_mean_of_means(self):
        f = pd.concat([day(y=[([0], 1)], p=[([0], 1)]), day('12408', y=[([0], 1)], p=[([0], 1)]), day('12408', date='2024-11-02', y=[([0], 1)])], ignore_index=True)
        d, s, _ = score(f, ('12207', '12408'))
        self.assertEqual(s['f1_all_population_station_mean'], .75)
        self.assertNotAlmostEqual(d.f1.mean(), .75)
        p, r = s['precision_available_station_mean'], s['recall_available_station_mean']
        self.assertNotAlmostEqual(2*p*r/(p+r), s['f1_available_station_mean'])

    def test_tn_is_retained_for_coverage_but_not_metric_denominators(self):
        d, _, _ = score(day(y=[([0, 1], 1)], p=[([0, 2, 3], 1)]), end='2024-11-02')
        row = d.iloc[0]; self.assertEqual(row.valid_slots, 144); self.assertEqual(row.metric_active_slots, 4)
        self.assertAlmostEqual(row.f1, .4); self.assertEqual(row.tn, 140)

    def test_partial_or_missing_day_is_never_silently_dropped_or_filled(self):
        f = day(y=[([0], 1)]).iloc[:143].copy(); d, s, _ = score(f)
        self.assertEqual(d.valid_slots.tolist(), [143, 0]); self.assertEqual(s['planned_days'], 2)
        self.assertEqual(s['coverage_days'], 0); self.assertEqual(s['excluded_ice_days'], 1)
        _, partial, _ = score(f, threshold=1); self.assertEqual(partial['f1_days'], 1)

    def test_missing_label_is_not_non_ice(self):
        f = day(); f.loc[0, 'ice'] = np.nan
        d, _, _ = score(f, end='2024-11-02'); self.assertEqual(d.iloc[0].valid_slots, 143)
        self.assertFalse(d.iloc[0].coverage_accepted)

    def test_all_population_mean_stays_null_if_any_station_is_undefined(self):
        _, s, st = score(day(y=[([0], 1)], p=[([0], 1)]), ('12207', '12408'))
        self.assertEqual(s['f1_available_station_mean'], 1.)
        self.assertIsNone(s['f1_all_population_station_mean']); self.assertEqual(s['f1_stations'], 1)

    def test_forbidden_station_future_duplicates_and_missing_predictions_rejected(self):
        for station in ['12410.0', '33411', '23402', '23102']:
            with self.assertRaises(ValueError): score(day(station=station), (station,))
        with self.assertRaises(ValueError): score(day(date='2025-11-01'))
        f = day()
        with self.assertRaises(ValueError): score(pd.concat([f, f]))
        f.loc[0, 'p'] = np.nan
        with self.assertRaises(ValueError): score(f)


if __name__ == '__main__': unittest.main()
