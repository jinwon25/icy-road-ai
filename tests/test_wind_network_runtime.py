import json

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from src.data_source import sha256_file as sha
from src.weather_network import FIELDS
from src.wind_network_runtime import network_features,predict_wind_network
from tests.test_weather_temporal import history_sample


@pytest.fixture
def wind(tmp_path):
    f=history_sample().iloc[:72].copy()
    points=pd.DataFrame({'station':f.station.unique(),'lat':35.,'lon':127.})
    coordinates=pd.DataFrame({'station':['a','b'],'lat':[35.,35.02],'lon':[127.01,127.]})
    parts=[]
    for station,delta in [('a',0.),('b',.2)]:
        q=pd.DataFrame({'station':station,'source_time':pd.date_range(f.time.min()-pd.Timedelta(minutes=10),periods=74,freq='10min')})
        for field in FIELDS:q[field]=1.+delta
        parts.append(q)
    aws=pd.concat(parts,ignore_index=True);settings=dict(neighbours=4,radius_km=50.,max_age_minutes=15.,distance_floor_km=1.,power=2.)
    _,x,_=network_features(f,points,aws,coordinates,settings)
    with threadpool_limits(limits=2):model=HistGradientBoostingRegressor(max_iter=3,min_samples_leaf=5,early_stopping=False).fit(x,np.sin(np.arange(len(f))))
    joblib.dump(model,tmp_path/'wind.joblib')
    metadata=dict(format='wind_network_residual_v1',file='wind.joblib',sha256=sha(tmp_path/'wind.joblib'),features=list(x),network=settings,aws_stations=['a','b'])
    (tmp_path/'metadata.json').write_text(json.dumps(metadata),'utf8')
    return f,points,aws,coordinates,tmp_path


def test_order_prefix_future_and_missing_preserved(wind):
    f,points,aws,coordinates,directory=wind
    expected=predict_wind_network(f,points,aws,coordinates,directory)
    changed=aws.copy();changed.loc[changed.source_time>=f.time.iloc[30],list(FIELDS)]=2.
    result=predict_wind_network(f,points,changed,coordinates,directory)
    pd.testing.assert_frame_equal(result.iloc[:31],expected.iloc[:31],check_exact=True)
    result=predict_wind_network(f.iloc[20:40],points,aws,coordinates,directory)
    pd.testing.assert_frame_equal(result,expected.iloc[20:40].reset_index(drop=True),check_exact=True)
    f=f.sample(frac=1,random_state=2).reset_index(drop=True);f.loc[0,'asos_wind_speed']=np.nan
    result=predict_wind_network(f,points,aws,coordinates,directory)
    assert result.time.tolist()==f.time.tolist()
    assert np.isnan(result.loc[0,'estimated_wind_speed_ms']) and not result.loc[0,'estimated_wind_speed_ms_available']


def test_targets_partial_network_and_duplicates_rejected(wind):
    f,points,aws,coordinates,directory=wind
    with pytest.raises(ValueError,match='Target measurements'):predict_wind_network(f.assign(wind_speed=1),points,aws,coordinates,directory)
    with pytest.raises(ValueError,match='Road targets'):predict_wind_network(f,points,aws.assign(ice=0),coordinates,directory)
    missing=predict_wind_network(f,points,aws.loc[aws.station.eq('a')],coordinates,directory)
    assert missing.network_wind_speed_count.eq(1).all()
    with pytest.raises(ValueError,match='Unknown AWS'):predict_wind_network(f,points,aws.assign(station='unknown'),coordinates,directory)
    with pytest.raises(ValueError,match='Unique'):predict_wind_network(f,pd.concat([points,points.iloc[:1]]),aws,coordinates,directory)


def test_invalid_model_and_weather_are_rejected(wind):
    f,points,aws,coordinates,directory=wind
    bad=aws.copy();bad.loc[0,'humidity']=101.
    with pytest.raises(ValueError,match='Invalid AWS'):predict_wind_network(f,points,bad,coordinates,directory)
    with (directory/'wind.joblib').open('ab') as stream:stream.write(b'changed')
    with pytest.raises(ValueError,match='checksum'):predict_wind_network(f,points,aws,coordinates,directory)
