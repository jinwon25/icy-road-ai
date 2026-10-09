"""상태 정의·중첩 학습 제외·고정 분모·미탐 악화 방지를 검증한다."""
import unittest
from types import SimpleNamespace

import numpy as np
import pandas as pd

from src.joint_surface import (FEATURES, WEATHER, eligibility, excluded_stations, ice_probability,
                              select_threshold, state_classes, thermal_features, threshold_prediction,
                              threshold_table, unit_blocks)
from src.thermal_ice import diagnostic_report


class JointSurfaceTests(unittest.TestCase):
    def test_auxiliary_excludes_own_unit_and_both_evaluation_groups(self):
        f = pd.DataFrame({'station': ['12103', '12209', '12207', '12408', '23205', '23404', '33205'],
                          'group': ['competition', 'competition', 'a', 'a', 'b', 'b', 'c'],
                          'time': pd.Timestamp('2024-11-01'), 'ice': 0.})
        blocks = unit_blocks(f)
        self.assertEqual(blocks['12207'], blocks['12408'])
        changed = f.assign(ice=1., road_temp=-100)
        self.assertEqual(unit_blocks(changed), blocks)
        for station, block in blocks.items():
            excluded = excluded_stations(f, ['a', 'b'], blocks, block)
            self.assertIn(station, excluded)
            self.assertTrue({'12207', '12408', '23205', '23404'} <= excluded)
        with self.assertRaises(ValueError):
            excluded_stations(f, ['unknown'])
        with self.assertRaises(ValueError):
            unit_blocks(f.assign(station=['12103'] * len(f)))

    def test_official_positive_and_unknown_states_are_preserved(self):
        classes = state_classes(['4', '04', 4., '12', '13', '15', '11', '14', '0', '-999', None])
        self.assertEqual(classes[:8].tolist(), [6, 6, 6, 3, 4, 5, 1, 1])
        self.assertTrue(np.isnan(classes[8:]).all())

    def test_target_values_are_never_feature_inputs(self):
        x = pd.DataFrame({k: [0., 1.] for k in WEATHER + ['rain15_max_3h', 'asos_snow_cm']})
        a = thermal_features(x, [-2., np.nan])
        b = thermal_features(x.assign(road_temp=999., ice=1, state_raw='04', station='12410', near_road_temp=-999), [-2., np.nan])
        pd.testing.assert_frame_equal(a, b)
        self.assertEqual(a.columns.tolist(), FEATURES)
        self.assertTrue(np.isnan(a.moisture_evidence.iloc[1]))

    def test_ice_column_order_and_missing_training_ice_fail_closed(self):
        model = SimpleNamespace(classes_=np.array([5, 6, 0]), predict_proba=lambda x: np.array([[.2, .3, .5]]))
        self.assertEqual(ice_probability(model, pd.DataFrame({'x': [1]}), True).tolist(), [.3])
        model.classes_ = np.array([0, 1, 2])
        with self.assertRaisesRegex(ValueError, 'contain Ice'):
            ice_probability(model, pd.DataFrame({'x': [1]}), True)

    def test_threshold_grid_matches_full_diagnostic_with_unknowns_and_fallback(self):
        f = pd.DataFrame({'station': '12207', 'time': pd.date_range('2024-11-01', periods=288, freq='10min'), 'ice': 0.})
        f.loc[[0, 2, 144, 145], 'ice'] = 1.
        f.loc[250, 'ice'] = np.nan
        score = np.linspace(0, 1, len(f)); fallback = np.zeros(len(f), bool); fallback[0] = True
        baseline = np.zeros(len(f), int); baseline[0] = 1
        table = threshold_table(f, score, fallback, baseline)
        for row in table.iloc[[0, 120, -1]].itertuples(index=False):
            p = threshold_prediction(score, row.threshold, fallback, baseline)
            r, _, _, _ = diagnostic_report(f, p)
            for key in ['tp', 'fp', 'fn', 'f1', 'fixed_ice_day_f1', 'fixed_station_f1_zero_undefined']:
                self.assertAlmostEqual(getattr(row, key), r[key] or 0)
        t = select_threshold(table, 0)
        self.assertEqual(int(threshold_prediction(score, t, fallback, baseline)[f.ice.eq(0)].sum()), 0)

    def test_single_event_and_station_recall_block_aggregate_only_improvement(self):
        f = pd.DataFrame({'station': '12207', 'time': pd.date_range('2024-11-01', periods=144, freq='10min'), 'ice': 0.})
        f.loc[[0, 2, 4, 6, 8], 'ice'] = 1.
        b = np.zeros(144, int); b[[0, 2, 4, 6, 8, 10, 11, 12, 13, 14]] = 1
        p = np.zeros(144, int); p[[0, 2, 4, 6]] = 1
        br, bs, _, _ = diagnostic_report(f, b); cr, cs, _, _ = diagnostic_report(f, p)
        self.assertGreater(cr['f1'], br['f1'])
        accepted, checks = eligibility(cr, br, cs, bs)
        self.assertFalse(accepted)
        self.assertFalse(checks['single_slot_guard']); self.assertFalse(checks['station_recall_guard'])
        with self.assertRaisesRegex(ValueError, 'populations'):
            eligibility(dict(cr, n=143), br, cs, bs)


if __name__ == '__main__':
    unittest.main()
