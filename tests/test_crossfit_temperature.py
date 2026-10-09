import unittest
import numpy as np
import pandas as pd
from src.crossfit_temperature import WEATHER_FEATURES, crossfit_weather, fit_weather, predict_weather, estimated_inputs


class CrossfitTemperatureTests(unittest.TestCase):
    def data(self):
        rng = np.random.default_rng(17)
        frame = pd.DataFrame([{ 'station': str(sid), 'time': pd.Timestamp('2025-01-01') + pd.Timedelta(minutes=10*t),
                              **dict(zip(WEATHER_FEATURES, rng.normal(size=14)))} for sid in range(100, 106) for t in range(20)])
        frame['road_temp'] = 2 * frame.aws_air_temp + frame.station.astype(int) / 20
        return frame

    def test_own_group_temperature_mutation_cannot_change_oof(self):
        data = self.data(); a, _, refs = crossfit_weather(data, {'999'}, '2025-03-01')
        own_group = refs[0]['prediction_stations']; changed = data.copy()
        changed.loc[changed.station.isin(own_group), 'road_temp'] += 1000
        b, _, _ = crossfit_weather(changed, {'999'}, '2025-03-01')
        np.testing.assert_array_equal(a[data.station.isin(own_group)], b[data.station.isin(own_group)])
        self.assertTrue(all(not set(r['training_stations']) & set(r['prediction_stations']) for r in refs))
        with self.assertRaises(ValueError): fit_weather(data, {'100'}, '2025-03-01')
        protected = data.copy(); protected.loc[0, 'station'] = '12410'
        with self.assertRaises(ValueError): crossfit_weather(protected, set(), '2025-03-01')
        with self.assertRaises(ValueError): fit_weather(data, set(), '2025-01-01')

    def test_prediction_ignores_target_and_preserves_missing_domain(self):
        data = self.data(); model, _ = fit_weather(data.loc[data.station.ne('100')], {'100'}, '2025-03-01')
        target = data.loc[data.station.eq('100')].copy(); a = predict_weather(model, target)
        target.road_temp += 999; np.testing.assert_array_equal(a, predict_weather(model, target))
        target.loc[target.index[0], 'asos_air_temp'] = np.nan
        weather = predict_weather(model, target); self.assertTrue(pd.isna(weather.iloc[0]))
        thermal = pd.DataFrame({'near_road_temp': -2.}, index=target.index)
        thermal.loc[target.index[1], 'near_road_temp'] = np.nan
        inputs = estimated_inputs(target, thermal, weather)
        self.assertTrue(inputs.iloc[0].isna().all())
        self.assertEqual(inputs.iloc[1].estimated_blend_temp, weather.iloc[1])
        self.assertAlmostEqual(inputs.iloc[2].estimated_blend_temp, .5*weather.iloc[2]-1.)


if __name__ == '__main__': unittest.main()
