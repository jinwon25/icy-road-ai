import numpy as np
import pandas as pd
import pytest
from src.antecedent_forcing import frost_point, accumulated_conditions, local_features


def test_frost_point_zero_humidity_is_missing_and_saturation_at_zero():
    x=frost_point([0,-10,0,0],[100,100,0,101])
    assert x[0]==0 and -10<x[1]<0 and np.isnan(x[2:]).all()


def test_exact_accumulation_of_constant_temperature():
    t=np.arange(0,61,10);y=accumulated_conditions(t,np.full(len(t),-2),np.full(len(t),-1),30)
    np.testing.assert_allclose(y[:,0],2*(1-np.exp(-t/30)),rtol=0,atol=1e-14)
    np.testing.assert_allclose(y[:,1],1-np.exp(-t/30),rtol=0,atol=1e-14)


def test_gap_decay_does_not_integrate_unobserved_interval():
    y=accumulated_conditions([0,10,100,110],[-2,-2,2,-2],[-1,-1,-1,-1],30)
    assert y[2,0]==pytest.approx(y[1,0]*np.exp(-90/30))
    assert y[2,2]==0 and y[3,2]==0 and y[2,3]==0


def test_zero_plateau_counts_single_crossing_and_missing_resets_sign():
    y=accumulated_conditions(np.arange(9)*10,[-1,0,0,1,0,1,np.nan,-1,1],np.zeros(9),30)
    assert y[3,2]==1 and y[5,2]==pytest.approx(np.exp(-20/30))
    assert np.isnan(y[6]).all()
    assert y[7,2]==pytest.approx(np.exp(-40/30))
    assert y[8,2]>1


def test_future_changes_do_not_change_past_and_time_order_is_strict():
    a=accumulated_conditions([0,10,20],[-1,-2,-3],[0,0,0],30)
    b=accumulated_conditions([0,10,20],[-1,-2,30],[0,0,30],30)
    np.testing.assert_array_equal(a[:2],b[:2])
    with pytest.raises(ValueError):accumulated_conditions([0,0],[0,0],[0,0],30)


def test_local_features_respect_future_station_winter_and_label_boundaries():
    rows=[]
    for station in ['a','b']:
        for year in [2024,2025]:
            for minute in [0,10,20]:
                rows.append(dict(station=station,winter=year,time=pd.Timestamp(year,11,1)+pd.Timedelta(minutes=minute)))
    frame=pd.DataFrame(rows)
    columns=['asos_air_temp','asos_ground_temp','asos_humidity','asos_rain_mm','asos_snow_cm',
        'asos_cloud_tenths','asos_solar_mj_m2','asos_wind_speed','asos_dewpoint_obs','asos_pressure',
        'asos_visibility','asos_new_snow3h','asos_soil5cm','aws_air_temp','aws_humidity',
        'aws_wind_speed','aws_rain_15m','aws_dewpoint','era5_temperature_2m',
        'era5_soil_temperature_0_to_7cm','era5_soil_temperature_7_to_28cm',
        'era5_snow_depth','era5_soil_moisture_0_to_7cm']
    for c in columns:frame[c]=-2. if 'temp' in c else 0.
    frame['asos_humidity']=90.;frame['aws_humidity']=90.;frame['aws_age_minutes']=10.
    frame.loc[2,'aws_age_minutes']=20.
    frame['ice']=0;frame['road_temp']=0.
    x,instant=local_features(frame)
    assert len(instant)==40 and x.shape==(12,64)
    np.testing.assert_array_equal(x.loc[[0,3,6,9],'asos_air_cold_30m'],0)
    assert np.isnan(x.loc[2,'aws_air_temp']) and np.isnan(x.loc[2,'aws_frost_point'])
    altered=frame.copy();altered['ice']=1;altered['road_temp']=-100.
    y,_=local_features(altered);pd.testing.assert_frame_equal(x,y,check_exact=True)
    altered.loc[2,columns]=30.
    y,_=local_features(altered)
    pd.testing.assert_frame_equal(x.drop(index=2),y.drop(index=2),check_exact=True)
