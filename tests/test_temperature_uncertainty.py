"""경험적 범위의 공간·분모·온도 경계 해석을 검증한다."""
import unittest
import numpy as np
import pandas as pd
from src.temperature_uncertainty import residual_radius, empirical_interval, interval_report


class TemperatureUncertaintyTests(unittest.TestCase):
    def test_equal_station_weight_prevents_large_station_dominance(self):
        f = pd.DataFrame({'station': ['12207']*9+['12408'], 'time': list(pd.date_range('2024-11-01', periods=9, freq='10min'))+[pd.Timestamp('2024-11-01')], 'road_temp': [0.]*9+[10.]})
        radius, receipt = residual_radius(f, np.zeros(10), .9)
        self.assertEqual(radius, 10.); self.assertFalse(receipt['guaranteed_coverage'])

    def test_nan_boundaries_and_denominators(self):
        f = pd.DataFrame({'station': ['12207']*4, 'time': pd.date_range('2024-11-01', periods=4, freq='10min'), 'road_temp': [-1., 1., 2., 0.]})
        p = np.array([-2., 2., 0., np.nan]); lo, hi = empirical_interval(p, 1.)
        r = interval_report(f, p, lo, hi)
        self.assertEqual(r['n'], 3); self.assertEqual(r['pooled_coverage'], 2/3)
        self.assertEqual(r['temperature_boundary']['ambiguous_rows'], 1)
        self.assertEqual(r['temperature_boundary']['cold_decisive_rows'], 1)
        self.assertFalse(r['official_ice_probability'])

    def test_calibration_rejects_future_and_protected(self):
        f = pd.DataFrame({'station': ['12410'], 'time': [pd.Timestamp('2024-11-01')], 'road_temp': [0.]})
        with self.assertRaises(ValueError):
            residual_radius(f, [0.])
        with self.assertRaises(ValueError):
            empirical_interval([np.inf], 1.)


if __name__ == '__main__':
    unittest.main()
