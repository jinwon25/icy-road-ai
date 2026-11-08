import math
import unittest
import numpy as np
import pandas as pd

from src.weather_thermodynamics import saturation_pressure, frost_point, vapor_pressure, thermodynamic_features, transformed_target, inverse_target
from tests.test_weather_history_stable import longer as source


class ThermodynamicTests(unittest.TestCase):
    def test_ifs_equation_and_inverse(self):
        for t in [-40., -10., 0., 20., 40.]:
            for phase, a, b in [('water', 17.502, 32.19), ('ice', 22.587, -.7)]:
                expected = 611.21*math.exp(a*(t+273.15-273.16)/(t+273.15-b))
                self.assertAlmostEqual(float(saturation_pressure(t, phase)), expected, places=10)
            self.assertAlmostEqual(float(frost_point(saturation_pressure(t, 'ice'))), t, places=10)
        self.assertLess(float(saturation_pressure(-10, 'ice')), float(saturation_pressure(-10)))
        self.assertTrue(np.isnan(saturation_pressure(-100)))
        self.assertTrue(np.isnan(frost_point(0)))
        self.assertEqual(float(vapor_pressure(0, 0)), 0)
        self.assertTrue(np.isnan(vapor_pressure(0, 101)))

    def test_transform_round_trip_and_bounds(self):
        values=np.array([0., .5, 20., 70., 99.5, 100.])
        baseline=np.full(len(values),60.)
        for kind in ['thermo_residual','thermo_logit']:
            target,weight=transformed_target(values,baseline,kind)
            expected=values if kind=='thermo_residual' else np.clip(values,.5,99.5)
            np.testing.assert_allclose(inverse_target(target,baseline,kind),expected,atol=1e-12)
            self.assertTrue(np.all(weight>0))
            self.assertTrue(np.all((inverse_target(np.full(6,1e8),baseline,kind)>=0)&(inverse_target(np.full(6,1e8),baseline,kind)<=100)))

    def test_causal_prefix_and_target_invariance(self):
        frame=source()
        full=thermodynamic_features(frame)
        start=frame.time.min()+pd.Timedelta(days=1)
        small=frame.loc[frame.time.ge(start)].reset_index(drop=True)
        actual=thermodynamic_features(small)
        keep=small.time.ge(start+pd.Timedelta(days=1))
        pd.testing.assert_frame_equal(actual.loc[keep].reset_index(drop=True),full.loc[frame.time.isin(small.loc[keep,'time'])].reset_index(drop=True),check_exact=True)
        changed=frame.copy();changed['relative_humidity']=999;changed['ice']=1;changed['road_temp']=-50
        pd.testing.assert_frame_equal(thermodynamic_features(changed),full,check_exact=True)
        changed=frame.copy();changed.loc[changed.time.gt(start),'aws_humidity']=1.
        pd.testing.assert_frame_equal(thermodynamic_features(changed).loc[frame.time.le(start)],full.loc[frame.time.le(start)],check_exact=True)

    def test_source_age_and_missing_clock(self):
        frame=source().iloc[:200].copy()
        frame['aws_age_minutes']=20.
        physical=thermodynamic_features(frame)
        self.assertTrue(physical.aws_vapor_pressure_pa.isna().all())
        frame=frame.drop(index=[160]).reset_index(drop=True)
        result=thermodynamic_features(frame)
        self.assertAlmostEqual(result.iloc[-1].asos_vapor_pressure_pa_coverage_3h,1.)
        near=result.loc[frame.time.eq(source().iloc[161].time)].iloc[0]
        self.assertAlmostEqual(near.asos_vapor_pressure_pa_coverage_3h,17/18)


if __name__=='__main__': unittest.main()
