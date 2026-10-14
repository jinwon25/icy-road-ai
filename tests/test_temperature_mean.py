"""동일 분모의 단순 평균과 개봉 개발 오차 진단을 검증한다."""
import unittest
import numpy as np
import pandas as pd
from src.temperature_mean import equal_mean, component_error_diagnostics


class TemperatureMeanTests(unittest.TestCase):
    def test_equal_mean_preserves_shared_missing_rows(self):
        result = equal_mean([-2., np.nan, 2.], [0., np.nan, 4.])
        np.testing.assert_allclose(result, [-1., np.nan, 3.], equal_nan=True)

    def test_one_missing_component_cannot_change_denominator(self):
        with self.assertRaisesRegex(ValueError, 'denominator'):
            equal_mean([1., np.nan], [1., 2.])

    def test_shape_and_infinity_rejected(self):
        for a, b in [([1.], [1., 2.]), ([[1.]], [[1.]]), ([np.inf], [np.inf])]:
            with self.assertRaises(ValueError):
                equal_mean(a, b)

    def test_large_finite_predictions_do_not_overflow(self):
        self.assertEqual(equal_mean([1e308], [1e308])[0], 1e308)

    def test_opposing_errors_cancel_with_exact_mse_identity(self):
        frame = pd.DataFrame({'road_temp': [0., 0., np.nan]})
        report = component_error_diagnostics(frame, [1., -1., 2.], [-1., 1., 2.])
        self.assertEqual(report['n'], 2)
        self.assertEqual(report['mixture_mse'], 0.)
        self.assertEqual(report['mse_identity'], 0.)
        self.assertAlmostEqual(report['error_correlation'], -1.)

    def test_no_valid_truth_is_reported_without_fabricated_error(self):
        report = component_error_diagnostics(pd.DataFrame({'road_temp': [np.nan]}), [1.], [2.])
        self.assertEqual(report['n'], 0)
        self.assertIsNone(report['mixture_mse'])


if __name__ == '__main__':
    unittest.main()
