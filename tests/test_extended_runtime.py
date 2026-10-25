import numpy as np
import pandas as pd
import pytest
from src.extended_runtime import infer
from src.submission_runtime import FEATURES, infer as old_infer
from src.thermal_runtime import EXTRA, thermal_predictors
from src.advanced_thermal_runtime import advanced_predictors


class ConstantModel:
    def __init__(self,columns,value):self.feature_names_in_=list(columns);self.value=value
    def predict(self,frame):return np.full(len(frame),self.value)


def weather():
    f=pd.DataFrame({'station':['12410']*3,'time':pd.date_range('2025-01-01',periods=3,freq='10min')})
    for c in [*FEATURES,*EXTRA]:f[c]=1.
    f['aws_age_minutes']=10.;f['asos_age_minutes']=10.
    return f


def test_temperature_improvement_keeps_icing_reference_visible_and_exact():
    f=weather();x,_,_=thermal_predictors(f,'thermal_history')
    icing=[ConstantModel(FEATURES,-1.),ConstantModel(FEATURES,-2.)]
    expected=old_infer(f,icing)
    result=infer(f,[ConstantModel(x.columns,3.)],icing,'thermal_history')
    assert (result.estimated_road_temp_c==3.).all()
    assert (result.icing_reference_temperature_c==-1.5).all()
    pd.testing.assert_series_equal(result.predicted_ice,expected.predicted_ice)
    assert (result.weather_history_status=='partial_or_unavailable').all()
    assert (result.temperature_model_count==1).all()
    f.loc[0,'asos_age_minutes']=70.
    missing=infer(f,[ConstantModel(x.columns,3.)],icing,'thermal_history')
    assert np.isnan(missing.loc[0,'estimated_road_temp_c']) and pd.isna(missing.loc[0,'predicted_ice'])
    f['road_temp']=0.
    with pytest.raises(ValueError):infer(f,[ConstantModel(x.columns,3.)],icing,'thermal_history')


def test_temperature_weights_and_feature_order_fail_closed():
    f=weather();x,_,_=thermal_predictors(f,'thermal')
    icing=[ConstantModel(FEATURES,-1.)]*2
    model=ConstantModel(x.columns,1.)
    with pytest.raises(ValueError):infer(f,[model],icing,'thermal',weights=[.5])
    with pytest.raises(ValueError):infer(f,[ConstantModel(reversed(x.columns),1.)],icing,'thermal')


def test_mixed_thermal_history_models_use_only_their_declared_inputs():
    f=weather();short,_,_=thermal_predictors(f,'thermal_history');long,_,_=advanced_predictors(f,'combined_thermal_history')
    models=[ConstantModel(short.columns,1.),ConstantModel(long.columns,3.)]
    icing=[ConstantModel(FEATURES,-1.)]*2
    result=infer(f,models,icing,'combined_thermal_history')
    assert (result.estimated_road_temp_c==2.).all() and (result.temperature_component_spread_c==2.).all()
    assert (result.weather_history_expected_features==39).all()
