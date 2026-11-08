"""잔존 적설을 현재 도로 결빙으로 간주하는 오류를 줄이기 위한 고정 기상 근거."""
import numpy as np
import pandas as pd


def snow_growth_history(frame):
    required={'station','time','asos_snow_cm','asos_new_snow3h'}
    if set(frame)!=required or frame.duplicated(['station','time']).any():
        raise ValueError('Declared weather keys only and unique rows required')
    f=frame.reset_index(drop=True)
    result=pd.DataFrame(np.nan,index=frame.index,columns=['snow_growth_6h','snow_growth_24h','snow_growth_72h'])
    for _,q in f.groupby('station',sort=False):
        idx=q.sort_values('time').index
        t=pd.DatetimeIndex(f.loc[idx,'time'])
        if t.tz is not None or t.isna().any() or not t.equals(t.floor('10min')):
            raise ValueError('KST 10-minute timestamps required')
        snow=pd.Series(f.loc[idx,'asos_snow_cm'].to_numpy(float),index=t)
        past=snow.reindex(t-pd.Timedelta(hours=1)).to_numpy()
        current=snow.to_numpy()
        known=np.isfinite(current)&np.isfinite(past)
        increased=(current-past>=.1-1e-10)
        new_snow=f.loc[idx,'asos_new_snow3h'].to_numpy(float)
        affirmative=np.isfinite(new_snow)&(new_snow>0)
        # 누락 신적설을 무강수로 확정하지 않는다. 양쪽 깊이 관측이 있으면 증가 여부는 계산 가능.
        evidence=np.where(known,increased.astype(float),np.nan)
        evidence[affirmative]=1.
        finite=np.isfinite(evidence)
        sums=np.r_[0,np.cumsum(np.where(finite,evidence,0))]
        counts=np.r_[0,np.cumsum(finite)]
        times=t.to_numpy(dtype='datetime64[ns]')
        right=np.arange(len(q))
        for hours in [6,24,72]:
            left=np.searchsorted(times,times-np.timedelta64(hours,'h'),side='left')
            n=counts[right]-counts[left]
            total=sums[right]-sums[left]
            valid=n>=np.ceil(.8*hours*6)
            result.loc[idx,f'snow_growth_{hours}h']=np.where(valid,total>0,np.nan)
    return result


def filter_snow_alerts(weather,runtime,history):
    if not weather[['station','time']].reset_index(drop=True).equals(runtime[['station','time']].reset_index(drop=True)):
        raise ValueError('Aligned weather and runtime keys required')
    if len(history)!=len(weather):
        raise ValueError('Aligned history required')
    temp=runtime.estimated_road_temp_c.to_numpy(float)
    base=runtime.predicted_ice.to_numpy(float,na_value=np.nan)
    dew=weather.aws_dewpoint.to_numpy(float)>=temp
    dew&=weather.aws_age_minutes.between(0,60,inclusive='right').to_numpy()
    rain=weather.rain15_max_3h.gt(0).to_numpy()
    snow_only=(base==1)&~dew&~rain&weather.asos_snow_cm.gt(0).to_numpy()
    values={'baseline':base}
    for name in ['snow_growth_6h','snow_growth_24h','snow_growth_72h']:
        p=base.copy()
        h=history[name].to_numpy(float)
        p[snow_only&np.isfinite(h)&(h==0)]=0.
        values[name]=p
    return values
