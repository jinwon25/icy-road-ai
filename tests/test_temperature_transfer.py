import unittest
import numpy as np
import pandas as pd
from src.temperature_transfer import (CANDIDATES, WEATHER_FEATURES, training_arrays,
                                      predict_temperature, regression_report, select_temperature)


class ConstantModel:
    def predict(self, x):
        return np.full(len(x), 2.)


class TemperatureTransferTests(unittest.TestCase):
    def frame(self):
        data = pd.DataFrame({name: [0., 0.] for name in WEATHER_FEATURES})
        data['station'] = ['A', 'B']
        data['time'] = pd.to_datetime(['2024-11-01', '2024-11-01'])
        data['asos_air_temp'] = [-2., 5.]
        data['road_temp'] = [0., 8.]
        return data

    def test_residual_training_and_inference(self):
        data = self.frame()
        x, y = training_arrays(data, 'residual_weather14')
        np.testing.assert_array_equal(y, [2., 3.])
        self.assertEqual(list(x), WEATHER_FEATURES)
        np.testing.assert_array_equal(predict_temperature(ConstantModel(), data, 'residual_weather14'), [0., 7.])

    def test_excluded_station_and_future_outcomes_rejected(self):
        data = self.frame()
        with self.assertRaises(ValueError):
            training_arrays(data, 'residual_weather14', forbidden=['A'])
        data.loc[0, 'station'] = '12410'
        with self.assertRaises(ValueError):
            training_arrays(data, 'residual_weather14')
        data = self.frame(); data.loc[0, 'time'] = pd.Timestamp('2025-11-01')
        with self.assertRaises(ValueError):
            training_arrays(data, 'residual_weather14')

    def test_missing_anchor_retains_unknown_output(self):
        data = self.frame(); data.loc[1, 'asos_air_temp'] = np.nan
        pred = predict_temperature(ConstantModel(), data, 'residual_weather14')
        self.assertEqual(pred[0], 0.)
        self.assertTrue(np.isnan(pred[1]))
        with self.assertRaises(ValueError):
            training_arrays(data, 'residual_weather14')

    def test_selection_rejects_station_harm_and_different_denominators(self):
        data = self.frame()
        base = regression_report(data, [1., 10.])
        safe = regression_report(data, [.5, 9.])
        harmful = regression_report(data, [1.1, 8.])
        reports = {'direct_weather14': base, 'residual_weather14': safe,
                   'direct_thermal24': harmful, 'residual_thermal24': harmful}
        self.assertEqual(select_temperature(reports), 'residual_weather14')
        reports['residual_weather14'] = regression_report(data, [.5, np.nan])
        with self.assertRaises(ValueError):
            select_temperature(reports)

    def test_predictors_exclude_target_measurements_and_station_id(self):
        for names, _ in CANDIDATES.values():
            self.assertFalse(set(names) & {'road_temp', 'ice', 'state_raw', 'station', 'near_road_temp'})


if __name__ == '__main__':
    unittest.main()
