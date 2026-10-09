import copy
import unittest

import numpy as np
import pandas as pd

from src.external_temperature import join_training_temperatures, fit_weather_temperature, predict_temperature, paired_temperature_metrics, select_temperature_candidate


class ExternalTemperatureTests(unittest.TestCase):
    def test_temperature_labels_join_by_exact_key_without_future_or_external_rows(self):
        features = pd.DataFrame({'station': ['12103', '12103'], 'time': pd.to_datetime(['2024-11-01 00:00', '2024-11-01 00:10']),
                                 'asos_air_temp': [0., 1.]})
        source = pd.DataFrame({'station': ['12103', '12103'], 'time': pd.to_datetime(['2024-11-01 00:10', '2025-11-01 00:00']),
                               'road_temp': [-1., 99.]})
        joined = join_training_temperatures(features, source, ['12103'])
        self.assertTrue(pd.isna(joined.road_temp.iloc[0])); self.assertEqual(joined.road_temp.iloc[1], -1.)
        with self.assertRaises(ValueError): join_training_temperatures(joined, source, ['12103'])
        with self.assertRaises(ValueError): join_training_temperatures(features, source.assign(station='12207'), ['12103'])

    def test_prediction_domain_and_own_outcomes_cannot_change_estimates(self):
        frame = pd.DataFrame({'asos_air_temp': [0., 1., 2., np.nan], 'neighbor_road_temp': [-2., np.nan, 0., 99.],
                              'road_temp': [-1., 0., 1., 9.], 'ice': [1, 0, 0, 0]})
        model, train = fit_weather_temperature(frame, ['asos_air_temp'])
        self.assertEqual(len(train), 3)
        prediction = predict_temperature(model, frame, ['asos_air_temp'])
        changed = frame.copy(); changed['road_temp'] = 999.; changed['ice'] = 1
        np.testing.assert_allclose(prediction, predict_temperature(model, changed, ['asos_air_temp']), equal_nan=True)
        self.assertTrue(np.isnan(prediction[-1]))
        self.assertEqual(paired_temperature_metrics(frame, prediction, prediction)['shared_valid_rows'], 3)
        with self.assertRaises(ValueError): fit_weather_temperature(frame, ['road_temp'])

    def test_selection_excludes_own_group_and_requires_both_errors_improve(self):
        rows = [{'outer_held_group': 'A', 'validation_group': group, 'training_excluded_groups': ['A', group],
                 'shared_valid_rows': 10, 'baseline': {'n': 10, 'mae': 2., 'rmse': 3., 'bias': -.1},
                 'candidate': {'n': 10, 'mae': 1., 'rmse': 2., 'bias': -.5}} for group in ('B', 'C', 'D')]
        decision = select_temperature_candidate(rows, 'A')
        self.assertEqual(decision['selected_candidate'], 'augmented_weather_ridge')
        self.assertEqual(decision, select_temperature_candidate(rows + [{'outer_held_group': 'A', 'validation_group': 'A'}], 'A'))
        changed = copy.deepcopy(rows)
        for row in changed: row['candidate']['rmse'] = 4.
        self.assertEqual(select_temperature_candidate(changed, 'A')['selected_candidate'], 'baseline')
        changed[0]['training_excluded_groups'] = ['B']
        with self.assertRaises(ValueError): select_temperature_candidate(changed, 'A')


if __name__ == '__main__':
    unittest.main()
