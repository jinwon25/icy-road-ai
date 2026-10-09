"""온도 후보의 지점 악화·분모·입력 누수 방지 조건을 합성 검증한다."""
import copy
import unittest
import numpy as np
import pandas as pd
from scripts import reproduce_weather_fallback as m


class WeatherFallbackTests(unittest.TestCase):
    def reports(self):
        base = {'pooled': {'n': 200}, 'station_macro': {'mae': 2., 'rmse': 3., 'bias': 0.},
                'stations': {'a': {'n': 100, 'mae': 1.}, 'b': {'n': 100, 'mae': 3.}}}
        return {c: copy.deepcopy(base) for c in ['baseline', *m.PLAN['candidates']]}

    def test_local_harm_rejected_even_with_macro_gain(self):
        r = self.reports()
        r['augmented_hgb']['station_macro'].update(mae=1.8, rmse=2.8)
        r['augmented_hgb']['stations']['a']['mae'] = 1.06
        self.assertEqual(m.choose(r), 'baseline')

    def test_safe_gain_and_different_denominator(self):
        r = self.reports()
        r['augmented_hgb']['station_macro'].update(mae=1.8, rmse=2.8)
        self.assertEqual(m.choose(r), 'augmented_hgb')
        r['augmented_hgb']['stations']['a']['n'] = 99
        with self.assertRaises(ValueError):
            m.choose(r)

    def test_target_feature_rejected(self):
        with self.assertRaises(ValueError):
            m.validate_features([*m.FEATURES, 'road_temp'])

    def test_training_domain_and_group_exclusion(self):
        f = pd.DataFrame({'station': ['a', 'b', 'c', 'd'], 'road_temp': [0., 1., np.nan, 2.],
                          'asos_air_temp': [1., 2., 3., np.nan]})
        self.assertEqual(m.training_mask(f, {'b'}).tolist(), [True, False, False, False])


if __name__ == '__main__':
    unittest.main()
