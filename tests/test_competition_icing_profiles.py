import numpy as np
import pandas as pd
import pytest
from src.competition_icing_profiles import apply_icing_profile
from tests.test_weather_temporal import history_sample


def fixture():
    frame=history_sample().iloc[:4].copy().reset_index(drop=True)
    frame['rain15_max_3h']=0.;frame['asos_snow_cm']=0.
    frame['asos_air_temp']=[-1.,1.,0.,-2.]
    result=frame[['station','time']].copy();result['predicted_ice']=pd.array([0,1,None,1],dtype='Int64')
    result['condition_evidence']=['criterion_not_met','cold_wet_consensus','insufficient_input','cold_wet_consensus']
    result['icing_reference_temperature_c']=[2.,-1.,np.nan,-2.]
    result['icing_reference_component_spread_c']=[1.,.1,np.nan,0.]
    result['icing_policy']='v2_weather12_temperature_moisture';result['estimated_road_temp_c']=[1.,-2.,np.nan,-1.]
    return frame,result


def test_explicit_profile_preserves_temperature_null_mask_and_prior_policy():
    frame,result=fixture();out=apply_icing_profile(frame,result,'score_priority_asos_zero')
    pd.testing.assert_series_equal(out.estimated_road_temp_c,result.estimated_road_temp_c)
    pd.testing.assert_series_equal(out.predicted_ice,pd.Series(pd.array([1,0,None,1],dtype='Int64'),name='predicted_ice'))
    np.testing.assert_array_equal(out.icing_reference_temperature_c,[-1.,1.,np.nan,-2.])
    pd.testing.assert_series_equal(out.preserved_v2_predicted_ice,result.predicted_ice,check_names=False)
    assert out.icing_policy.eq('score_priority_asos_zero_v1').all()


def test_preserved_profile_is_exact_and_targets_are_rejected():
    frame,result=fixture();pd.testing.assert_frame_equal(apply_icing_profile(frame,result,'preserved_v2'),result,check_exact=True)
    for column in ['ice','road_temp']:
        altered=frame.copy();altered[column]=0
        with pytest.raises(ValueError):apply_icing_profile(altered,result,'score_priority_asos_zero')
    with pytest.raises(ValueError):apply_icing_profile(frame,result,'guessed')
