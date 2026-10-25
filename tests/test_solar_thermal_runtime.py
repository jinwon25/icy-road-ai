import numpy as np
import pandas as pd
import pytest
from src.solar_thermal_runtime import temperature_predictors
from src.thermal_runtime import EXTRA
from src.submission_runtime import FEATURES
from src.solar_memory_search import feature_table


def test_asos_and_target_geometry_remain_distinct_and_validate_units():
    f=pd.DataFrame({'station':['12207']*100,'time':pd.date_range('2025-01-01',periods=100,freq='10min'),'winter':2024})
    for c in [*FEATURES,*EXTRA]:f[c]=1.
    f['aws_age_minutes']=10.;f['asos_age_minutes']=10.;f['air_dewpoint_gap']=0.;f['ground_air_gap']=0.
    f['asos_solar_altitude_deg']=30.;f['asos_solar_sine_positive']=.5
    f['solar_altitude_deg']=45.;f['solar_sine_positive']=np.sqrt(.5)
    for kind in ['history_asos_solar','combined_asos_solar','combined_target_solar']:
        expected=feature_table(f,kind);actual,_,_=temperature_predictors(f,kind)
        pd.testing.assert_frame_equal(actual,expected,check_exact=True)
    f['asos_solar_sine_positive']=30.
    with pytest.raises(ValueError):temperature_predictors(f,'combined_asos_solar')
