import numpy as np
import pandas as pd
import pytest
from src.thermal_refinement import estimator, feature_table
from src.submission_runtime import FEATURES
from src.temperature_transfer import THERMAL_FEATURES


def sample():
    n=24
    f=pd.DataFrame({c:np.arange(n,dtype=float) for c in set(FEATURES)|set(THERMAL_FEATURES)})
    f['station']='12207';f['time']=pd.date_range('2024-11-01',periods=n,freq='10min')
    f['winter']=2024;f['group']='honam_baekyang';f['road_temp']=1.;f['ice']=0.
    return f


def test_memory_is_past_only_and_group_local():
    f=sample();other=f.copy();other['station']='12408';other['asos_ground_temp']=1000.
    both=pd.concat([f,other],ignore_index=True)
    x=feature_table(both,'thermal_memory')
    name='asos_ground_temp_prior_1h_mean'
    assert pd.isna(x.loc[0,name]) and pd.isna(x.loc[24,name])
    assert x.loc[6,name]==pytest.approx(2.5)
    assert x.loc[30,name]==1000.
    changed=both.copy();changed.loc[6:23,'asos_ground_temp']=999.
    assert feature_table(changed,'thermal_memory').loc[6,name]==x.loc[6,name]


def test_ablation_cannot_retain_ground_difference():
    x=feature_table(sample(),'thermal_no_ground')
    assert not {'asos_ground_temp','ground_air_gap'} & set(x)
    assert len(feature_table(sample(),'thermal_ground_only').columns)==14


def test_parameter_overrides_are_explicit():
    spec=dict(family='hgb',loss='absolute_error',iterations=600,leaves=31,
              overrides=dict(min_samples_leaf=300,l2_regularization=50.))
    model=estimator(spec)
    assert model.min_samples_leaf==300 and not model.early_stopping
    spec['overrides']['random_state']=5
    with pytest.raises(ValueError):estimator(spec)
