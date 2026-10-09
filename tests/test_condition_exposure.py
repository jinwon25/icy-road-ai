import unittest
import numpy as np
from src.condition_exposure import cold_moisture_condition


class ConditionExposureTests(unittest.TestCase):
    def test_unknown_not_dry_and_known_wet_suffices(self):
        got=cold_moisture_condition([-1,-1,-1,1,np.nan,1],[-2,np.nan,np.nan,2,0,np.nan],[np.nan,1,0,1,1,np.nan])
        np.testing.assert_allclose(got,[np.nan,1,np.nan,0,np.nan,0],equal_nan=True)

    def test_temperature_sensitivity_is_monotone(self):
        temperature=np.linspace(-5,5,100)
        low=cold_moisture_condition(temperature+2,np.full(100,-1.),np.zeros(100))
        center=cold_moisture_condition(temperature,np.full(100,-1.),np.zeros(100))
        high=cold_moisture_condition(temperature-2,np.full(100,-1.),np.zeros(100))
        self.assertTrue((low<=center).all());self.assertTrue((center<=high).all())


if __name__=='__main__':unittest.main()
