"""거리 제거가 입력·결측 분모·학습 제외 그룹을 바꾸지 않는지 검사한다."""
import unittest
import numpy as np
import pandas as pd

from src.temperature_transfer import WEATHER_FEATURES
from src.weather_distance_ablation import DISTANCE_FREE_FEATURES, training_values, predict
from scripts.audit_weather_distance import verify_query_scope


def sample():
    data = pd.DataFrame({c: [1., 2.] for c in WEATHER_FEATURES})
    data['station'] = ['12103', '12209']
    data['time'] = pd.to_datetime(['2024-11-01 00:10', '2024-11-01 00:20'])
    data['road_temp'] = [3., 4.]
    return data


class FixedModel:
    def predict(self, x):
        if list(x) != list(DISTANCE_FREE_FEATURES):
            raise ValueError('Wrong input contract')
        return np.full(len(x), 5.)


class DistanceAblationTests(unittest.TestCase):
    def test_only_two_distances_removed(self):
        self.assertEqual(len(DISTANCE_FREE_FEATURES), 12)
        self.assertEqual(set(WEATHER_FEATURES) - set(DISTANCE_FREE_FEATURES), {'aws_distance_km', 'asos_distance_km'})
        data = sample(); x, y = training_values(data)
        np.testing.assert_array_equal(y, [3., 4.])
        self.assertEqual(len(x), len(data))

    def test_model_ignores_distance_and_target_measurement_values(self):
        data = sample(); base = predict(FixedModel(), data)
        data['aws_distance_km'] = 1000.; data['asos_distance_km'] = np.nan; data['road_temp'] = -999.
        np.testing.assert_array_equal(base, predict(FixedModel(), data))

    def test_missing_asos_keeps_paired_prediction_domain(self):
        data = sample(); data.loc[1, 'asos_air_temp'] = np.nan
        prediction = predict(FixedModel(), data)
        self.assertEqual(prediction[0], 5.)
        self.assertTrue(np.isnan(prediction[1]))
        with self.assertRaises(ValueError):
            training_values(data)

    def test_held_out_protected_and_next_winter_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Held-out'):
            training_values(sample(), ['12103'])
        data = sample(); data.loc[0, 'station'] = ' 12410.0 '
        with self.assertRaises(ValueError):
            training_values(data)
        data = sample(); data['time'] += pd.DateOffset(years=1)
        with self.assertRaises(ValueError):
            predict(FixedModel(), data)

    def test_infinite_retained_feature_rejected(self):
        data = sample(); data.loc[0, 'aws_air_temp'] = np.inf
        with self.assertRaises(ValueError):
            predict(FixedModel(), data)
        with self.assertRaises(ValueError):
            training_values(data)

    def test_auditor_allows_held_out_query_and_rejects_fit_station(self):
        query = pd.DataFrame({'station': ['12207']})
        verify_query_scope(query, {'12207', '12408'}, {'12207', '12408', '23205'})
        with self.assertRaises(ValueError):
            verify_query_scope(query, {'23205'}, {'12207', '12408', '23205'})


if __name__ == '__main__':
    unittest.main()
