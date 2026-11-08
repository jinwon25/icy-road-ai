"""기존 기온·풍속 추론을 유지하고 검증된 과거 이력 습도를 적용한다."""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from src.data_source import sha256_file
from src.road_weather_runtime import INPUT_COLUMNS, predict_weather
from src.road_weather_transfer import baselines, constrain
from src.weather_history_stable import stable_temporal_features


FORBIDDEN = {'ice','road_temp','state','state_raw','observed_ice','actual_ice','target','label',
             'air_temperature','relative_humidity','wind_speed'}
SENTINELS = [-999., -99.9, -99.2, -99.7]


def prepare_history_input(frame):
    if frame.empty or frame.columns.duplicated().any():
        raise ValueError('Nonempty unique weather columns required')
    if FORBIDDEN & {str(c).strip().lower() for c in frame}:
        raise ValueError('Target measurements cannot enter history inference')
    required = ['station','time',*INPUT_COLUMNS]
    if set(required)-set(frame):
        raise ValueError('Required weather input columns missing')
    f = frame.loc[:,required].copy().reset_index(drop=True)
    if f.station.isna().any():raise ValueError('Missing station identity')
    f.station = f.station.astype(str).str.strip().str.replace(r'^([0-9]+)\.0$',r'\1',regex=True)
    if f.station.str.lower().isin(['','nan','none','null','<missing>']).any():
        raise ValueError('Invalid station identity')
    f.time = pd.to_datetime(f.time,errors='raise')
    if f.time.dt.tz is not None:f.time=f.time.dt.tz_convert('Asia/Seoul').dt.tz_localize(None)
    if f.time.isna().any() or ((f.time.dt.minute%10!=0)|(f.time.dt.second!=0)|
        (f.time.dt.microsecond!=0)|(f.time.dt.nanosecond!=0)).any():
        raise ValueError('Exact ten-minute KST timestamps required')
    if f.duplicated(['station','time']).any():raise ValueError('Duplicate station timestamp')
    for column in INPUT_COLUMNS:
        f[column]=pd.to_numeric(f[column],errors='raise').replace(SENTINELS,np.nan)
        if np.isinf(f[column]).any():raise ValueError('Infinite weather input')
    for column in ['asos_humidity','aws_humidity']:
        if not f[column].dropna().between(0,100).all():raise ValueError('Invalid humidity')
    for column in ['asos_wind_speed','aws_wind_speed','asos_rain_mm','aws_rain_15m','asos_snow_cm']:
        if f[column].dropna().lt(0).any():raise ValueError('Negative wind or moisture')
    for column in ['hour_sin','hour_cos','season_sin','season_cos']:
        if f[column].isna().any() or not f[column].between(-1,1).all():
            raise ValueError('Finite cyclic input required')
    return f


def predict_humidity_history(frame,model_directory):
    """제공된 과거 기상만 사용한다. 부족한 과거 문맥은 출력에 표시한다."""
    f=prepare_history_input(frame);directory=Path(model_directory)
    metadata=json.loads((directory/'metadata.json').read_text(encoding='utf-8'))
    if metadata['format']!='humidity_history_residual_v1':raise ValueError('Unsupported history model format')
    path=directory/metadata['file']
    if path.parent.resolve()!=directory.resolve() or path.suffix!='.joblib':raise ValueError('Invalid history model path')
    if sha256_file(path)!=metadata['sha256']:raise ValueError('History model checksum mismatch')
    f['_row']=np.arange(len(f))
    f=f.sort_values(['station','time']).reset_index(drop=True)
    # 여름 경계는 과거 24시간을 10월/11월 사이에서도 연결하기 위한 그룹 메타데이터다.
    f['winter']=f.time.dt.year-(f.time.dt.month<7).astype(int)
    _,x=stable_temporal_features(f)
    if list(x)!=metadata['features']:raise ValueError('History feature schema mismatch')
    model=joblib.load(path)
    if list(model.feature_names_in_)!=list(x):raise ValueError('Stored history feature mismatch')
    a,b=baselines(f,'relative_humidity');available=np.isfinite(a)&np.isfinite(b)
    values=np.full(len(f),np.nan)
    if available.any():
        with threadpool_limits(limits=2):
            values[available]=constrain(model.predict(x.loc[available])+b[available],'relative_humidity')
    slots=np.zeros(len(f),dtype=np.int64)
    for _,q in f.groupby(['station','winter'],sort=True):
        times=pd.DatetimeIndex(q.time)
        slots[q.index]=pd.Series(np.ones(len(q)),index=times).rolling('24h',closed='right').count().to_numpy(np.int64)
    result=f[['station','time','_row']].copy()
    result['estimated_humidity_pct']=values
    result['estimated_humidity_pct_available']=available
    result['humidity_history_input_slots_24h']=slots
    result['humidity_history_status']=np.where(slots>=144,'complete_24h','partial_24h')
    outside=np.zeros(len(f),dtype=bool)
    for name,bounds in metadata.get('feature_ranges',{}).items():
        if name not in x:raise ValueError('Unknown history range feature')
        value=x[name].to_numpy(float);finite=np.isfinite(value)
        outside|=finite if bounds[0] is None else finite&((value<bounds[0])|(value>bounds[1]))
    result['humidity_history_outside_training_range']=outside
    return result.sort_values('_row').drop(columns='_row').reset_index(drop=True)


def predict_weather_history(frame,base_model_directory,history_model_directory):
    f=prepare_history_input(frame)
    result=predict_weather(f,base_model_directory).reset_index(drop=True)
    humidity=predict_humidity_history(f,history_model_directory)
    if not result[['station','time']].equals(humidity[['station','time']]):
        raise ValueError('History result identity mismatch')
    for column in humidity.columns.difference(['station','time'],sort=False):result[column]=humidity[column]
    return result
