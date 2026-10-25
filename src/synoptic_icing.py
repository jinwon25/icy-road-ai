"""관측 정답을 받지 않는 ASOS 수분 이력과 제한된 결빙 분류 입력."""
import numpy as np
import pandas as pd
from src.icing_transition import _keys

BASE=['asos_air_temp','aws_air_temp','asos_ground_temp','asos_humidity','aws_humidity','asos_rain_mm',
      'asos_snow_cm','aws_rain_15m','rain15_max_3h','asos_cloud_tenths','asos_solar_mj_m2','aws_wind_speed']
ADDED=['asos_dewpoint_obs','asos_vapor_pressure','asos_pressure','asos_wind_speed','asos_visibility',
       'asos_low_cloud','asos_new_snow3h','asos_soil5cm']
MONOTONE={'asos_air_temp':-1,'aws_air_temp':-1,'asos_ground_temp':-1,'asos_soil5cm':-1,
          'asos_humidity':1,'aws_humidity':1,'asos_rain_mm':1,'asos_snow_cm':1,'aws_rain_15m':1,
          'rain15_max_3h':1,'asos_new_snow3h':1,'recent_wet_24h':1,'recent_wet_72h':1,
          'asos_dewpoint_depression':-1,'asos_ground_dewpoint_gap':-1}


def wetness_memory(frame):
    required=['station','time','asos_air_temp','asos_ground_temp','asos_dewpoint_obs','asos_humidity','asos_rain_mm','asos_snow_cm','asos_age_minutes']
    if set(frame)!=set(required):raise ValueError('Declared weather keys only, no observed outcomes')
    f=frame.reset_index(drop=True);keys=_keys(f)
    air=f.asos_air_temp.to_numpy(float)
    valid=np.isfinite(air)&f.asos_age_minutes.between(0,60,inclusive='right').to_numpy()
    valid&=f[['asos_humidity','asos_rain_mm','asos_snow_cm']].notna().any(axis=1).to_numpy()
    water=(f.asos_rain_mm.gt(0)|f.asos_snow_cm.gt(0)|
           (f.asos_humidity.ge(90)&f.asos_ground_temp.le(f.asos_dewpoint_obs))).to_numpy()
    result=np.full((len(f),3),np.nan)
    for _,part in keys.groupby('station',sort=False):
        last_time=None;last_wet=None
        for i,t in zip(part.sort_values('time').index,part.sort_values('time').time.to_numpy(dtype='datetime64[ns]').view('int64')):
            if not valid[i]:last_time=last_wet=None;continue
            if last_time is None or t-last_time!=600_000_000_000 or air[i]>2:last_wet=None
            if water[i] and air[i]<=2:last_wet=t
            age=np.inf if last_wet is None else (t-last_wet)/3_600_000_000_000
            result[i]=[float(water[i]),float(age<=24),float(age<=72)]
            last_time=t
    return pd.DataFrame(result,columns=['wet_now','recent_wet_24h','recent_wet_72h'],index=frame.index)


def feature_table(frame,kind):
    required=['station','time','asos_air_temp','asos_ground_temp','asos_dewpoint_obs','asos_humidity','asos_rain_mm','asos_snow_cm','asos_age_minutes']
    x=frame[BASE].copy()
    if kind=='base':return x
    if kind!='extra':raise ValueError('Unplanned feature group')
    x=pd.concat([x,frame[ADDED],wetness_memory(frame[required])[['recent_wet_24h','recent_wet_72h']]],axis=1)
    x['asos_dewpoint_depression']=frame.asos_air_temp-frame.asos_dewpoint_obs
    x['asos_ground_dewpoint_gap']=frame.asos_ground_temp-frame.asos_dewpoint_obs
    if np.isinf(x.to_numpy(float)).any():raise ValueError('Infinite weather feature')
    return x


def fixed_policies(frame):
    required=['station','time','asos_air_temp','asos_ground_temp','asos_dewpoint_obs','asos_humidity','asos_rain_mm','asos_snow_cm','asos_age_minutes']
    memory=wetness_memory(frame[required]);result={}
    for kind,column in [('air','asos_air_temp'),('ground','asos_ground_temp')]:
        for hours,water in [(0,'wet_now'),(24,'recent_wet_24h'),(72,'recent_wet_72h')]:
            # 추가 자료가 없는 행에서 ASOS 기준선으로 복귀해 평가 행을 임의로 줄이지 않는다.
            known=frame[column].notna()&memory[water].notna()
            result[f'{kind}_wet_{hours}h']=np.where(known,frame[column].le(0)&memory[water].gt(0),frame.asos_air_temp.le(0)).astype(float)
    return result


def sample_weights(frame,kind):
    if not frame.ice.isin([0,1]).all():raise ValueError('Valid training labels required')
    if kind=='row':return np.ones(len(frame))
    if kind!='day':raise ValueError('Unplanned weight type')
    f=frame[['station','winter','time','ice']].copy();f['day']=pd.to_datetime(f.time).dt.normalize()
    class_size=f.groupby(['station','winter','day','ice']).ice.transform('size').to_numpy(float)
    classes=f.groupby(['station','winter','day']).ice.transform('nunique').to_numpy(float)
    days=f.groupby(['station','winter']).day.transform('nunique').to_numpy(float)
    w=1/(class_size*classes*days)
    return w/w.mean()
