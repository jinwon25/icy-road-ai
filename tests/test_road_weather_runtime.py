import json

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyRegressor

from src.data_source import sha256_file
from src.road_weather_transfer import features
from src.road_weather_runtime import INPUT_COLUMNS,predict_weather


def bundle(tmp_path):
    f=pd.DataFrame({c:np.ones(6) for c in INPUT_COLUMNS})
    f['asos_air_temp']=np.arange(6,dtype=float);f['aws_air_temp']=np.arange(6,dtype=float)+1
    model=DummyRegressor(strategy='constant',constant=2).fit(features(f),np.zeros(6))
    path=tmp_path/'air.joblib';joblib.dump(model,path)
    meta=dict(format='road_weather_residual_v1',features=list(features(f)),
        targets={'air_temperature':dict(file=path.name,sha256=sha256_file(path))})
    (tmp_path/'metadata.json').write_text(json.dumps(meta),encoding='utf-8')
    return f,path


def test_runtime_keeps_missing_and_ignores_outcomes(tmp_path):
    f,_=bundle(tmp_path);f.loc[1,'asos_age_minutes']=0;f.loc[2,'aws_age_minutes']=16
    f['ice']=1;f['air_temperature']=999;f['road_temp']=999
    p=predict_weather(f,tmp_path)
    np.testing.assert_allclose(p.estimated_air_temperature_c,[3,np.nan,4,6,7,8],equal_nan=True)
    assert p.estimated_air_temperature_c_available.tolist()==[True,False,True,True,True,True]
    assert not {'ice','air_temperature','road_temp'}&set(p)
    pd.testing.assert_frame_equal(p,predict_weather(f.drop(columns=['ice','air_temperature','road_temp']),tmp_path))


def test_runtime_checksum_and_required_inputs(tmp_path):
    f,path=bundle(tmp_path)
    with pytest.raises(ValueError,match='columns missing'):predict_weather(f.drop(columns='asos_air_temp'),tmp_path)
    with path.open('ab') as stream:stream.write(b'altered')
    with pytest.raises(ValueError,match='checksum'):predict_weather(f,tmp_path)
