import numpy as np
import pandas as pd
from src.combined_thermal_history import thermal_memory,MEMORY_COLUMNS
from src.advanced_thermal_runtime import advanced_predictors
from src.thermal_runtime import EXTRA
from src.submission_runtime import FEATURES


def test_memory_matches_past_only_window_and_is_invariant_to_future():
    f=pd.DataFrame({'station':['x']*150,'time':pd.date_range('2025-01-01',periods=150,freq='10min')})
    for column in MEMORY_COLUMNS:f[column]=np.arange(len(f))/10
    f.loc[7,'asos_ground_temp']=np.nan
    actual=thermal_memory(f)
    for column in MEMORY_COLUMNS:
        for minutes in [60,180,720]:
            expected=f.set_index('time')[column].rolling(f'{minutes}min',closed='left',min_periods=int(np.ceil(.8*minutes/10))).mean().round(6)
            np.testing.assert_allclose(actual[f'{column}_prior_mean_{minutes}m'],expected,rtol=0,atol=1e-12,equal_nan=True)
    changed=f.copy();changed.loc[100:,list(MEMORY_COLUMNS)]=999.
    pd.testing.assert_frame_equal(actual.iloc[:101],thermal_memory(changed).iloc[:101],check_exact=True)


def test_independent_runtime_thermal_means_agree_and_accept_unseen_locations():
    f=pd.DataFrame({'station':['12410']*160,'time':pd.date_range('2025-01-01',periods=160,freq='10min')})
    for c in [*FEATURES,*EXTRA]:f[c]=1.
    f['aws_age_minutes']=10.;f['asos_age_minutes']=10.
    f['asos_ground_temp']=np.round(np.sin(np.arange(len(f)))*3,6)
    f.loc[7,'asos_ground_temp']=np.nan
    expected=thermal_memory(f);actual,_,_=advanced_predictors(f,'combined_thermal_history')
    pd.testing.assert_frame_equal(actual[expected.columns],expected,check_exact=True)
