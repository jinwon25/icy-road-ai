import unittest
import numpy as np
import pandas as pd
from src.method_blending import COMPONENTS, convex_predict, fit_weights, validate_meta_origin, domain, combine_binary, temperature_gate, ice_guard


class MethodBlendingTests(unittest.TestCase):
    def frame(self):
        f = pd.DataFrame({'station': ['12207']*3+['12408']*3, 'time': list(pd.date_range('2024-11-01', periods=3, freq='10min'))*2,
                          'road_temp': [-1., 0., 1.]*2})
        for i, c in enumerate(COMPONENTS):
            f[c] = f.road_temp + (i-4)*.3
        return f

    def test_validation_labels_cannot_enter_meta_base(self):
        validate_meta_origin(['K'], ['G', 'H', 'K'], 'G', 'H')
        for forbidden in [['G', 'K'], ['H', 'K'], ['G', 'H']]:
            with self.assertRaises(ValueError): validate_meta_origin(['K'], forbidden, 'G', 'H')
        with self.assertRaises(ValueError): validate_meta_origin(['H'], ['G', 'H'], 'G', 'H')

    def test_convex_domain_and_missingness(self):
        np.testing.assert_allclose(convex_predict([[2., 4.], [np.nan, np.nan]], [.25, .75]), [3.5, np.nan])
        for p, w in [([[2., np.nan]], [.5, .5]), ([[1., 2.]], [-.1, 1.1]), ([[1., 2.]], [.2, .2])]:
            with self.assertRaises(ValueError): convex_predict(p, w)

    def test_optimization_station_weights_and_constraint(self):
        f = self.frame(); w, r = fit_weights(f, .1)
        self.assertTrue((w >= 0).all()); self.assertAlmostEqual(w.sum(), 1.)
        np.testing.assert_allclose(f[list(COMPONENTS)].to_numpy() @ w, f.road_temp, atol=1e-7)
        # 한 지점 행을 늘려도 지점별 동일 비중 목적함수는 변하지 않는다.
        duplicated = f.loc[f.station.eq('12207')].copy(); duplicated.time += pd.Timedelta(days=1)
        v, _ = fit_weights(pd.concat([f, duplicated], ignore_index=True), .1)
        np.testing.assert_allclose(w, v, atol=1e-7); self.assertEqual(r['valid_rows'], 6)

    def test_all_assessment_and_future_rows_rejected(self):
        for station in ['12410', '12104', '12406', '23102', '23407']:
            f = self.frame(); f.loc[0, 'station'] = station
            with self.assertRaises(ValueError): domain(f)
        f = self.frame(); f.time += pd.Timedelta(days=400)
        with self.assertRaises(ValueError): domain(f)

    def test_rule_tradeoff_cannot_be_concealed(self):
        a = np.array([0, 1, 0, 1]); b = np.array([1, 0, 0, 1]); y = np.array([0, 1, 1, 0])
        conjunction = combine_binary(a, b, 'and'); union = combine_binary(a, b, 'or')
        self.assertLessEqual(((conjunction == 1) & (y == 0)).sum(), ((a == 1) & (y == 0)).sum())
        self.assertGreaterEqual(((conjunction == 0) & (y == 1)).sum(), ((a == 0) & (y == 1)).sum())
        self.assertGreaterEqual(((union == 1) & (y == 0)).sum(), ((a == 1) & (y == 0)).sum())
        self.assertLessEqual(((union == 0) & (y == 1)).sum(), ((a == 0) & (y == 1)).sum())

    def test_empty_near_freezing_does_not_pass(self):
        base = {'stations': {'a': {'n': 3, 'mae': 2.}}, 'pooled': {'n': 3}, 'near_freezing': {'n': 0, 'mae': None}, 'station_macro': {'mae': 2., 'rmse': 3.}}
        candidate = base | {'station_macro': {'mae': 1., 'rmse': 2.}}
        self.assertFalse(temperature_gate(candidate, base))

    def test_single_positive_station_is_guarded(self):
        base = dict(n=4, complete_days=0, fixed_ice_days=0, fixed_ice_day_stations=0, events=2, single_slot_events=2,
                    tp=1, fp=2, fn=1, detected_events=1, detected_single_slot_events=1,
                    f1=.4, fixed_station_f1_zero_undefined=.4, fixed_ice_day_f1=.4, provisional_daily_station_f1=.4)
        stations = pd.DataFrame({'station': ['12207', '12408'], 'n': [2, 2], 'tp': [1, 0], 'fn': [0, 1]})
        candidate = base | {'fp': 1, 'f1': .5}
        changed = stations.copy(); changed.tp = [0, 1]; changed.fn = [1, 0]
        eligible, checks = ice_guard(candidate, base, changed, stations)
        self.assertFalse(eligible); self.assertFalse(checks['every_positive_station_tp'])

    def test_undefined_daily_metric_cannot_pass(self):
        base = dict(n=2, complete_days=0, fixed_ice_days=0, fixed_ice_day_stations=0, events=1, single_slot_events=1,
                    tp=1, fp=1, fn=0, detected_events=1, detected_single_slot_events=1,
                    f1=.5, fixed_station_f1_zero_undefined=.5, fixed_ice_day_f1=None, provisional_daily_station_f1=None)
        stations = pd.DataFrame({'station': ['12207'], 'n': [2], 'tp': [1], 'fn': [0]})
        eligible, checks = ice_guard(base | {'fp': 0, 'f1': 1.}, base, stations, stations)
        self.assertFalse(eligible); self.assertFalse(checks['supported_metrics'])
