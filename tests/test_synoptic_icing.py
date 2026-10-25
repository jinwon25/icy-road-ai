import numpy as np
import pandas as pd
import pytest
from src.synoptic_icing import wetness_memory,sample_weights,feature_table,fixed_policies,BASE,ADDED

def weather(n=500):
    f=pd.DataFrame({'station':['a']*n,'time':pd.date_range('2024-11-01',periods=n,freq='10min')})
    for c in set(BASE+ADDED+['asos_age_minutes']):f[c]=0.
    f['asos_air_temp']=-2.;f['asos_ground_temp']=-1.;f['asos_dewpoint_obs']=-4.
    f['asos_humidity']=60.;f['asos_age_minutes']=10.;f.loc[0,'asos_rain_mm']=1.
    return f

def memory(f):
    return wetness_memory(f[['station','time','asos_air_temp','asos_ground_temp','asos_dewpoint_obs','asos_humidity','asos_rain_mm','asos_snow_cm','asos_age_minutes']])

def test_decay_and_reset():
    f=weather();m=memory(f)
    assert m.loc[144,'recent_wet_24h']==1 and m.loc[145,'recent_wet_24h']==0
    assert m.loc[432,'recent_wet_72h']==1 and m.loc[433,'recent_wet_72h']==0
    f.loc[20,'asos_air_temp']=3.;assert memory(f).loc[21,'recent_wet_72h']==0

def test_missing_and_station_reset():
    f=weather(10);f.loc[3,'asos_age_minutes']=70.;f.loc[6:,'station']='b'
    m=memory(f);assert m.iloc[3].isna().all();assert m.loc[4,'recent_wet_24h']==0
    assert m.loc[6,'recent_wet_24h']==0

def test_future_and_order_invariance():
    f=weather(20);m=memory(f);changed=f.copy();changed.loc[11:,'asos_rain_mm']=10.
    pd.testing.assert_frame_equal(memory(changed).iloc[:11],m.iloc[:11])
    shuffled=f.sample(frac=1,random_state=7);pd.testing.assert_frame_equal(memory(shuffled).sort_index(),m)

def test_time_gap():
    f=weather(20).drop(index=5).reset_index(drop=True);assert memory(f).loc[5,'recent_wet_72h']==0

def test_outcomes_rejected():
    f=weather(2);f['ice']=1
    with pytest.raises(ValueError):wetness_memory(f)

def test_weight_equalizes_day_class_station():
    f=pd.DataFrame({'station':['a']*7+['b']*2,'winter':[2024]*9,
        'time':pd.to_datetime(['2024-11-01']*5+['2024-11-02']*2+['2024-11-01']*2),
        'ice':[1,0,0,0,0,1,0,0,0]})
    w=sample_weights(f,'day');assert np.isclose(w.mean(),1)
    assert np.isclose(w[:7].sum(),w[7:].sum())
    assert np.isclose(w[:5].sum(),w[5:7].sum());assert np.isclose(w[0],w[1:5].sum())

def test_features_ignore_outcomes():
    f=weather(8);x=feature_table(f,'extra');f['ice']=1;f['road_temp']=-99
    pd.testing.assert_frame_equal(feature_table(f,'extra'),x)
    assert len(x.columns)==24

def test_fixed_missing_fallback():
    f=weather(4);f.loc[2,'asos_ground_temp']=np.nan
    p=fixed_policies(f);assert p['ground_wet_0h'][2]==1
    assert len(p)==6

def test_resumed_predictions_match_keys_not_dataframe_index(tmp_path):
    from scripts.evaluate_synoptic_icing import assert_matching_keys
    original=weather(4).iloc[2:].copy()
    path=tmp_path/'predictions.parquet';original.to_parquet(path,index=False)
    restored=pd.read_parquet(path)
    assert_matching_keys(restored,original)
    with pytest.raises(AssertionError):assert_matching_keys(restored.iloc[::-1],original)
    restored.loc[0,'station']='different'
    with pytest.raises(AssertionError):assert_matching_keys(restored,original)
