"""과거 AWS 관측망을 추가한 풍속 추론. 다른 기상·온도·결빙 출력을 덮어쓰지 않는다."""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from src.data_source import sha256_file
from src.weather_history_runtime import prepare_history_input,SENTINELS
from src.road_weather_transfer import features,baselines
from src.weather_network import WeatherNetwork,FIELDS


def network_features(frame,points,observations,coordinates,settings):
    f=prepare_history_input(frame)
    if not {'station','lat','lon'}<=set(points) or points.station.duplicated().any():
        raise ValueError('Unique target station coordinates required')
    points=points.copy();points['station']=points.station.astype(str)
    if not set(f.station)<=set(points.station):raise ValueError('Target coordinates missing')
    for data in [points,coordinates]:
        if not {'station','lat','lon'}<=set(data) or data.station.duplicated().any():raise ValueError('Unique geographic coordinates required')
        if not np.isfinite(data[['lat','lon']].to_numpy(float)).all() or not data.lat.between(-90,90).all() or not data.lon.between(-180,180).all():
            raise ValueError('Valid geographic coordinates required')
    forbidden={'ice','road_temp','state','state_raw','target','label','air_temperature','relative_humidity'}
    if forbidden&{str(c).lower().strip() for c in observations}:raise ValueError('Road targets forbidden in AWS input')
    if not {'station','source_time',*FIELDS}<=set(observations):raise ValueError('Required AWS observation columns missing')
    obs=observations.loc[:,['station','source_time',*FIELDS]].copy();obs['station']=obs.station.astype(str)
    coords=coordinates.copy();coords['station']=coords.station.astype(str)
    if set(obs.station)-set(coords.station):raise ValueError('Unknown AWS station outside the declared network')
    obs.source_time=pd.to_datetime(obs.source_time,errors='raise')
    if obs.source_time.dt.tz is not None:obs.source_time=obs.source_time.dt.tz_convert('Asia/Seoul').dt.tz_localize(None)
    bounds={'air_temp':(-60,70),'humidity':(0,100),'wind_speed':(0,75),'rain_15m':(0,500),'dewpoint':(-80,60)}
    for k,(lo,hi) in bounds.items():
        obs[k]=pd.to_numeric(obs[k],errors='raise').replace(SENTINELS,np.nan)
        if np.isinf(obs[k]).any() or not obs[k].dropna().between(lo,hi).all():raise ValueError('Invalid AWS '+k)
    builder=WeatherNetwork(obs,coords.set_index('station')[['lat','lon']],**settings)
    # 선언한 관측망에서 해당 시간대 자료가 없는 지점도 후보 자리를 유지한다.
    # 먼 관측소를 승격시키거나 가상의 시각·관측값을 만들지 않는다.
    for station in coords.station:
        if station not in builder.sources:
            builder.sources[station]=(np.empty(0,dtype='datetime64[ns]'),np.empty((0,len(FIELDS))))
    parts=[]
    for station,q in f.groupby('station',sort=True):
        location=points.loc[points.station.eq(station)].iloc[0]
        x,_=builder.build(q.time,location.lat,location.lon,q);x.index=q.index;parts.append(x)
    network=pd.concat(parts).sort_index()
    x=pd.concat([features(f),network],axis=1)
    return f,x,network


def predict_wind_network(frame,points,observations,coordinates,model_directory):
    directory=Path(model_directory);metadata=json.loads((directory/'metadata.json').read_text('utf8'))
    if metadata['format']!='wind_network_residual_v1':raise ValueError('Unsupported wind model format')
    path=directory/metadata['file']
    if path.parent.resolve()!=directory.resolve() or path.suffix!='.joblib':raise ValueError('Invalid model path')
    if sha256_file(path)!=metadata['sha256']:raise ValueError('Wind model checksum mismatch')
    if sorted(coordinates.station.astype(str))!=metadata['aws_stations']:raise ValueError('AWS coordinate network mismatch')
    f,x,network=network_features(frame,points,observations,coordinates,metadata['network'])
    if list(x)!=metadata['features']:raise ValueError('Wind feature schema mismatch')
    model=joblib.load(path)
    if list(model.feature_names_in_)!=list(x):raise ValueError('Stored wind feature schema mismatch')
    a,b=baselines(f,'wind_speed');available=np.isfinite(a)&np.isfinite(b)
    values=np.full(len(f),np.nan)
    if available.any():
        with threadpool_limits(limits=2):values[available]=np.maximum(model.predict(x.loc[available])+b[available],0)
    result=f[['station','time']].copy();result['estimated_wind_speed_ms']=values;result['estimated_wind_speed_ms_available']=available
    for column in ['network_wind_speed_count','network_wind_speed_effective_n','network_wind_speed_range','network_wind_speed_distance_km']:
        result[column]=network[column].to_numpy()
    return result
