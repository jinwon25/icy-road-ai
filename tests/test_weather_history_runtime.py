import json

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from src.data_source import sha256_file as sha
from src.road_weather_runtime import predict_weather
from src.road_weather_transfer import features
from src.weather_history_stable import stable_temporal_features
from src.weather_history_runtime import predict_humidity_history,predict_weather_history
from tests.test_weather_temporal import history_sample


@pytest.fixture
def models(tmp_path):
    f=history_sample();base=features(f);_,history=stable_temporal_features(f)
    current=tmp_path/'current';current.mkdir();past=tmp_path/'past';past.mkdir()
    parameters=dict(max_iter=5,max_leaf_nodes=3,min_samples_leaf=5,early_stopping=False,random_state=0)
    metadata=dict(format='road_weather_residual_v1',features=list(base),targets={})
    with threadpool_limits(limits=2):
        for target in ['air_temperature','relative_humidity','wind_speed']:
            model=HistGradientBoostingRegressor(**parameters).fit(base,np.sin(np.arange(len(f))/10))
            path=current/(target+'.joblib');joblib.dump(model,path)
            metadata['targets'][target]=dict(file=path.name,sha256=sha(path))
        model=HistGradientBoostingRegressor(**parameters).fit(history,np.cos(np.arange(len(f))/10))
    (current/'metadata.json').write_text(json.dumps(metadata),'utf-8')
    path=past/'humidity.joblib';joblib.dump(model,path)
    (past/'metadata.json').write_text(json.dumps(dict(format='humidity_history_residual_v1',
        file=path.name,sha256=sha(path),features=list(history))),'utf-8')
    return f,current,past


def test_runtime_causal_and_original_order(models):
    f,_,past=models;expected=predict_humidity_history(f,past)
    changed=f.copy();changed.loc[100:,'asos_air_temp']+=100
    actual=predict_humidity_history(changed,past)
    pd.testing.assert_frame_equal(actual.iloc[:100],expected.iloc[:100],check_exact=True)
    shuffled=f.sample(frac=1,random_state=7).reset_index(drop=True)
    actual=predict_humidity_history(shuffled,past)
    assert actual.time.tolist()==shuffled.time.tolist()
    pd.testing.assert_frame_equal(actual.sort_values('time').reset_index(drop=True),expected,check_exact=True)


def test_legacy_air_and_wind_exactly_preserved(models):
    f,current,past=models;legacy=predict_weather(f,current)
    actual=predict_weather_history(f,current,past)
    for column in legacy:
        if column.startswith('estimated_humidity'):continue
        pd.testing.assert_series_equal(actual[column],legacy[column],check_exact=True)
    assert actual.humidity_history_status.iloc[0]=='partial_24h'
    assert actual.humidity_history_status.iloc[143]=='complete_24h'


def test_context_crosses_october_november(models):
    f,_,past=models;f=f.copy();f['time']=pd.date_range('2024-10-31',periods=len(f),freq='10min')
    result=predict_humidity_history(f,past)
    assert result.loc[144,'humidity_history_input_slots_24h']==144
    assert result.loc[144,'humidity_history_status']=='complete_24h'


def test_unavailable_humidity_remains_missing(models):
    f,_,past=models;f=f.copy();f.loc[140,'asos_humidity']=np.nan
    result=predict_humidity_history(f,past)
    assert np.isnan(result.loc[140,'estimated_humidity_pct'])
    assert not result.loc[140,'estimated_humidity_pct_available']


def test_targets_bad_clock_and_duplicate_rejected(models):
    f,_,past=models
    for target in ['ice','relative_humidity','road_temp']:
        with pytest.raises(ValueError,match='Target measurements'):
            predict_humidity_history(f.assign(**{target:1}),past)
    wrong=f.copy();wrong.loc[0,'time']+=pd.Timedelta(minutes=1)
    with pytest.raises(ValueError,match='ten-minute'):predict_humidity_history(wrong,past)
    with pytest.raises(ValueError,match='Duplicate'):
        predict_humidity_history(pd.concat([f,f.iloc[[0]]],ignore_index=True),past)


def test_checksum_and_model_path_are_checked(models):
    f,_,past=models
    path=past/'metadata.json';metadata=json.loads(path.read_text('utf-8'))
    metadata['file']='../humidity.joblib';path.write_text(json.dumps(metadata),'utf-8')
    with pytest.raises(ValueError,match='model path'):predict_humidity_history(f,past)
    metadata['file']='humidity.joblib';path.write_text(json.dumps(metadata),'utf-8')
    with (past/'humidity.joblib').open('ab') as stream:stream.write(b'changed')
    with pytest.raises(ValueError,match='checksum'):predict_humidity_history(f,past)
