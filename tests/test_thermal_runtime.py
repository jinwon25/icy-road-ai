import numpy as np
import pandas as pd
import pytest
from src.thermal_runtime import thermal_predictors,EXTRA
from src.submission_runtime import FEATURES
from src.thermal_extended import feature_table


def frame():
    n=160;f=pd.DataFrame({'station':['12207']*n,'time':list(pd.date_range('2024-11-01',periods=80,freq='10min'))+list(pd.date_range('2025-11-01',periods=80,freq='10min')),'winter':[2024]*80+[2025]*80})
    for c in [*FEATURES,*EXTRA]:f[c]=1.
    f['aws_age_minutes']=10.;f['asos_age_minutes']=10.;f['air_dewpoint_gap']=0.;f['ground_air_gap']=0.
    return f


def test_runtime_matches_research_history_without_station_or_year_spoofing():
    f=frame();expected=feature_table(f,'thermal_history');actual,_,_=thermal_predictors(f,'thermal_history')
    pd.testing.assert_frame_equal(actual,expected,check_exact=True)
    f.station='12410';target,_,_=thermal_predictors(f,'thermal_history')
    pd.testing.assert_frame_equal(actual,target,check_exact=True)
    f['road_temp']=0.
    with pytest.raises(ValueError):thermal_predictors(f)


def test_stale_thermal_history_and_derived_input_are_cleared():
    f=frame().iloc[:2].copy();f.loc[0,'aws_age_minutes']=70.;f.loc[1,'asos_age_minutes']=70.
    f['ground_air_gap']=999.
    x,valid,stale=thermal_predictors(f)
    assert stale.iloc[0] and np.isnan(x.loc[0,'air_min_3h']) and np.isnan(x.loc[0,'ground_air_gap'])
    assert not valid.iloc[1] and np.isnan(x.loc[1,'asos_ground_temp'])
