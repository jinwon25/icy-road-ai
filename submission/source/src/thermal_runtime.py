"""노면 정답을 받지 않는 열·수분·과거 기상 추론 입력 계약."""
import numpy as np
import pandas as pd
from .submission_runtime import prepare_weather,FEATURES,SENTINELS

EXTRA=('asos_ground_temp','asos_cloud_tenths','asos_solar_mj_m2','asos_rain_mm','asos_snow_cm',
       'asos_humidity','air_min_3h','rain15_max_3h','air_dewpoint_gap','ground_air_gap')
HISTORY_COLUMNS=('asos_air_temp','aws_air_temp','aws_humidity','aws_dewpoint','aws_rain_15m','aws_wind_speed')
WINDOWS=(60,180,720)
CHANGES=(60,180)
HISTORY_FEATURES=[f'{c}_past_mean_{m}m' for c in HISTORY_COLUMNS for m in WINDOWS]+[f'{c}_change_{m}m' for c in HISTORY_COLUMNS for m in CHANGES]


def prepare_thermal(frame):
    if {'sfs','tr1','neighbor_road_temp','near_road_temp','surface_dewpoint_gap','surface_air_gap'} & {str(c).lower() for c in frame}:
        raise ValueError('Road sensor observations cannot enter thermal weather inference')
    needed=set(EXTRA)-{'air_dewpoint_gap','ground_air_gap'}
    if not needed<=set(frame):raise ValueError('Declared thermal weather inputs required')
    f,asos_valid,aws_stale=prepare_weather(frame)
    if not f.index.is_unique:raise ValueError('Unique row index required')
    for c in needed:
        f[c]=pd.to_numeric(frame[c],errors='raise').replace(list(SENTINELS),np.nan)
        if np.isinf(f[c]).any():raise ValueError('Infinite thermal observation')
    for c in ['asos_cloud_tenths','asos_solar_mj_m2','asos_rain_mm','asos_snow_cm']:
        if f[c].dropna().lt(0).any():raise ValueError('Negative cloud/radiation/precipitation observation')
    if not f.asos_humidity.dropna().between(0,100).all() or not f.asos_cloud_tenths.dropna().between(0,10).all():
        raise ValueError('Invalid ASOS humidity or cloud cover')
    f.loc[aws_stale,['air_min_3h','rain15_max_3h']]=np.nan
    asos_stale=~f.asos_age_minutes.between(0,60,inclusive='right')
    f.loc[asos_stale,[c for c in needed if c.startswith('asos_')]]=np.nan
    f['air_dewpoint_gap']=f.aws_air_temp-f.aws_dewpoint
    f['ground_air_gap']=f.asos_ground_temp-f.aws_air_temp
    return f,asos_valid,aws_stale


def fixed_weather_history(frame):
    """배치 길이와 겨울 구분에 무관한 정수 누적합. 입력 시각은 과거만 참조한다."""
    result=pd.DataFrame(np.nan,index=frame.index,columns=HISTORY_FEATURES)
    for _,part in frame.groupby('station',sort=False):
        part=part.sort_values('time');t=part.time.to_numpy(dtype='datetime64[ns]');right=np.arange(len(t))
        if len(t)>1_000_000:raise ValueError('Fixed-point safety bound exceeded')
        for c in HISTORY_COLUMNS:
            a=part[c].to_numpy(float);valid=np.isfinite(a)
            if np.isinf(a).any() or (np.abs(a[valid])>100_000).any():raise ValueError('Fixed-point observation bound exceeded')
            values=np.rint(np.where(valid,a,0)*1_000_000).astype(np.int64)
            sums=np.r_[np.int64(0),np.cumsum(values,dtype=np.int64)]
            counts=np.r_[np.int64(0),np.cumsum(valid,dtype=np.int64)]
            for minutes in WINDOWS:
                left=np.searchsorted(t,t-np.timedelta64(minutes,'m'),side='left')
                n=counts[right]-counts[left];total=sums[right]-sums[left]
                mean=np.divide(total,n*1_000_000,out=np.full(len(t),np.nan),where=n>=np.ceil(.8*minutes/10))
                result.loc[part.index,f'{c}_past_mean_{minutes}m']=np.round(mean,6)
            for minutes in CHANGES:
                wanted=t-np.timedelta64(minutes,'m');pos=np.searchsorted(t,wanted);safe=pos.clip(max=len(t)-1)
                usable=(pos<len(t))&(t[safe]==wanted)&valid&valid[safe]
                delta=np.full(len(t),np.nan);delta[usable]=(values[usable]-values[safe[usable]])/1_000_000
                result.loc[part.index,f'{c}_change_{minutes}m']=delta
    return result


def thermal_predictors(frame,kind='thermal'):
    f,valid,stale=prepare_thermal(frame);x=f[list(FEATURES)].copy()
    if kind=='thermal_history':x=pd.concat([x,fixed_weather_history(f)],axis=1)
    elif kind!='thermal':raise ValueError('Supported deployment inputs are thermal and thermal_history')
    x=pd.concat([x,f[list(EXTRA)]],axis=1)
    return x,valid,stale
