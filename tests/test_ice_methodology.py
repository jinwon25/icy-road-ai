"""새 입력의 누출·공백·클래스 정의 경계를 검증한다."""
import unittest
import numpy as np
import pandas as pd
from src.ice_methodology import causal_history, candidate_features, training_weights, hurdle_labels, HISTORY_COLUMNS
from src.joint_surface import FEATURES


class IceMethodologyTests(unittest.TestCase):
    def sample(self):
        frame = pd.DataFrame({'station': '12207', 'time': pd.date_range('2024-11-01', periods=30, freq='10min')})
        for c in FEATURES:
            frame[c] = np.arange(len(frame), dtype=float)
        return frame

    def test_prior_window_excludes_current_and_future(self):
        a = self.sample(); b = a.copy()
        b.loc[12:, list(HISTORY_COLUMNS)] = 10000.
        first, changed = causal_history(a), causal_history(b)
        means = [c for c in first if '_prior_mean_' in c]
        pd.testing.assert_frame_equal(first.loc[:12, means], changed.loc[:12, means])
        self.assertEqual(first.loc[12, 'aws_air_temp_prior_mean_60m'], 8.5)
        self.assertEqual(first.loc[12, 'aws_air_temp_change_60m'], 6.)

    def test_low_coverage_and_exact_gap(self):
        a = self.sample().drop(index=[6, 7])
        h = causal_history(a)
        self.assertTrue(np.isnan(h.loc[12, 'aws_air_temp_prior_mean_60m']))
        self.assertTrue(np.isnan(h.loc[12, 'aws_air_temp_change_60m']))

    def test_station_isolation(self):
        a = self.sample(); b = a.copy(); b.station = '12408'; b[list(HISTORY_COLUMNS)] = 1000.
        together = pd.concat([a, b], ignore_index=True)
        h = causal_history(together)
        self.assertEqual(h.loc[12, 'aws_air_temp_prior_mean_60m'], 8.5)
        self.assertEqual(h.loc[42, 'aws_air_temp_prior_mean_60m'], 1000.)

    def test_target_columns_unused(self):
        a = self.sample(); b = a.assign(road_temp=999., ice=1, state_raw='04')
        pd.testing.assert_frame_equal(causal_history(a), causal_history(b))
        pd.testing.assert_frame_equal(candidate_features(a, 'hgb_history', causal_history(a)), candidate_features(b, 'hgb_history', causal_history(b)))

    def test_balanced_classes_have_equal_total_weight(self):
        y = np.array([0, 0, 0, 1]); w = training_weights(y, balanced=True)
        self.assertAlmostEqual(w[y == 0].sum(), w[y == 1].sum())
        np.testing.assert_array_equal(training_weights(y), [1, 1, 1, 20])
        with self.assertRaises(ValueError):
            training_weights([0, 0])

    def test_hurdle_keeps_only_04_positive(self):
        non_dry, ice = hurdle_labels(['01', '02', '04', '13', '15', '10'])
        np.testing.assert_array_equal(non_dry, [0, 1, 1, 1, 1, 1])
        np.testing.assert_array_equal(ice, [0, 0, 1, 0, 0, 0])
        with self.assertRaises(ValueError):
            hurdle_labels(['04', '99'])

    def test_distance_removal_and_domain(self):
        a = self.sample(); x = candidate_features(a, 'hgb_no_distance')
        self.assertEqual(x.shape[1], 18)
        self.assertNotIn('aws_distance_km', x)
        with self.assertRaises(ValueError):
            causal_history(a.assign(station='12410'))
        with self.assertRaises(ValueError):
            causal_history(a.assign(time=pd.date_range('2025-11-01', periods=30, freq='10min')))


if __name__ == '__main__':
    unittest.main()
