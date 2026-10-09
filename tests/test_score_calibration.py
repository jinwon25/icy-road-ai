"""가중치·양성 비율 보정과 보정기 자체의 평가 정답 유입을 검증한다."""
import unittest
import numpy as np
import pandas as pd
from scipy.special import expit, logit

from src.score_calibration import adjusted_logit, apply_sigmoid, fit_sigmoid, validate_calibration_origins


class ScoreCalibrationTests(unittest.TestCase):
    def test_known_weighted_prior_transforms_to_common_likelihood_score(self):
        likelihood = np.array([-2., 0., 2.])
        for prior in [.001, .2]:
            p = expit(likelihood + logit(prior) + np.log(20))
            np.testing.assert_allclose(adjusted_logit(p, prior, prior_adjusted=True), likelihood, atol=1e-12)
        with self.assertRaises(ValueError): adjusted_logit([.5], 0)
        with self.assertRaises(ValueError): adjusted_logit([np.nan], .1)

    def test_extreme_scores_are_finite_and_order_preserving(self):
        values = adjusted_logit([0., .001, .5, 1.], .01, prior_adjusted=True)
        self.assertTrue(np.isfinite(values).all()); self.assertTrue((np.diff(values) > 0).all())

    def test_monotone_calibration_does_not_invert_anti_predictive_order(self):
        x = np.arange(20, dtype=float); y = np.r_[np.ones(10), np.zeros(10)]
        calibration = fit_sigmoid(x, y)
        self.assertGreaterEqual(calibration['slope'], 0)
        self.assertTrue((np.diff(apply_sigmoid(calibration, x)) >= 0).all())
        with self.assertRaises(ValueError): fit_sigmoid([1, 2], [0, 1])

    def test_three_level_exclusion_checks_every_source_row(self):
        rows = pd.DataFrame({'station': ['a', 'a'], 'time': pd.date_range('2024-11-01', periods=2, freq='10min'),
                             'group': ['K', 'K'], 'source_forbidden_groups': [['G', 'H', 'K'], ['G', 'H', 'K']]})
        validate_calibration_origins(rows, {'G', 'H'})
        bad = rows.copy(); bad.at[1, 'source_forbidden_groups'] = ['G', 'K']
        with self.assertRaisesRegex(ValueError, 'source model'): validate_calibration_origins(bad, {'G', 'H'})
        with self.assertRaisesRegex(ValueError, 'outcomes'): validate_calibration_origins(rows.assign(group='H'), {'G', 'H'})
        with self.assertRaisesRegex(ValueError, 'Duplicate'): validate_calibration_origins(pd.concat([rows, rows]), {'G', 'H'})


if __name__ == '__main__': unittest.main()
