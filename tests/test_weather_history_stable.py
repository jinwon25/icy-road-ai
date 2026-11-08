import numpy as np
import pandas as pd

from src.weather_history_stable import stable_temporal_features
from src.weather_temporal import temporal_features
from tests.test_weather_temporal import history_sample


def longer():
    f=pd.concat([history_sample().iloc[[0]]]*720,ignore_index=True)
    f['time']=pd.date_range('2024-11-01',periods=len(f),freq='10min')
    random=np.random.default_rng(734)
    for field in ['asos_air_temp','asos_ground_temp','asos_humidity','asos_wind_speed',
        'asos_solar_mj_m2','aws_air_temp','aws_humidity','aws_wind_speed']:
        f[field]=40+random.normal(size=len(f))
    return f


def test_extra_prefix_has_bit_exact_same_window_features():
    f=longer();_,full=stable_temporal_features(f)
    short=f.iloc[432:].reset_index(drop=True);_,limited=stable_temporal_features(short)
    pd.testing.assert_frame_equal(full.iloc[576:].reset_index(drop=True),
        limited.iloc[144:].reset_index(drop=True),check_exact=True)


def test_gaps_and_mathematical_rolling_definition_agree():
    f=longer().drop(index=[100,110,500,601]).reset_index(drop=True)
    _,old=temporal_features(f);_,actual=stable_temporal_features(f)
    pd.testing.assert_frame_equal(actual,old,atol=1e-11,rtol=1e-12,check_exact=False)
    start=pd.Timestamp('2024-11-04')
    short=f.loc[f.time.ge(start-pd.Timedelta(days=1))].reset_index(drop=True)
    _,limited=stable_temporal_features(short)
    pd.testing.assert_frame_equal(actual.loc[f.time.ge(start)].reset_index(drop=True),
        limited.loc[short.time.ge(start)].reset_index(drop=True),check_exact=True)


def test_future_and_other_station_cannot_change_past_window():
    f=longer();_,expected=stable_temporal_features(f)
    changed=f.copy();changed.loc[600:,'aws_humidity']=99
    second=f.copy();second['station']='second';second['asos_humidity']=1
    combined=pd.concat([changed,second],ignore_index=True)
    _,actual=stable_temporal_features(combined)
    pd.testing.assert_frame_equal(actual.iloc[:600],expected.iloc[:600],check_exact=True)
