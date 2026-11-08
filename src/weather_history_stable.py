"""각 과거 창을 독립 합산해 더 오래된 입력 유무에 따른 부동소수점 상태를 제거한다."""
import numpy as np
import pandas as pd

from src.road_weather_transfer import features
from src.weather_temporal import HISTORY_FIELDS,WINDOWS


def stable_temporal_features(frame):
    if not frame.index.equals(pd.RangeIndex(len(frame))):raise ValueError('Reset source index required')
    if frame[['station','winter','time']].isna().any().any():raise ValueError('Complete history keys required')
    if frame.duplicated(['station','time']).any():raise ValueError('Unique station timestamps required')
    base=features(frame);result=base.copy();step=pd.Timedelta(minutes=10).value
    for hours in WINDOWS:
        for field in HISTORY_FIELDS:
            for kind in ['mean','departure','coverage']:result[f'{field}_{kind}_{hours}h']=np.nan
    for _,part in frame.groupby(['station','winter'],sort=True):
        order=part.sort_values('time').index.to_numpy()
        times=pd.DatetimeIndex(frame.loc[order,'time']).asi8
        if np.any(times%step) or np.any(np.diff(times)<=0):raise ValueError('Unique ten-minute history clock required')
        positions=((times-times[0])//step).astype(np.int64)
        dense=np.full((int(positions[-1])+1,len(HISTORY_FIELDS)),np.nan)
        current=base.loc[order,HISTORY_FIELDS].to_numpy(float);dense[positions]=current
        good=np.isfinite(dense);clean=np.where(good,dense,0.)
        for hours,minimum in WINDOWS.items():
            width=hours*6
            # 길이가 고정된 각 창만 합산한다. 창 이전의 누적·보상 상태를 이어받지 않는다.
            padded=np.vstack([np.zeros((width-1,len(HISTORY_FIELDS))),clean])
            padded_good=np.vstack([np.zeros((width-1,len(HISTORY_FIELDS)),dtype=bool),good])
            windows=np.lib.stride_tricks.sliding_window_view(padded,width,axis=0)
            count_windows=np.lib.stride_tricks.sliding_window_view(padded_good,width,axis=0)
            sums=windows.sum(axis=2)[positions]
            counts=count_windows.sum(axis=2)[positions]
            means=np.divide(sums,counts,out=np.full_like(sums,np.nan),where=counts>=minimum)
            for j,field in enumerate(HISTORY_FIELDS):
                result.loc[order,f'{field}_mean_{hours}h']=means[:,j]
                result.loc[order,f'{field}_departure_{hours}h']=current[:,j]-means[:,j]
                result.loc[order,f'{field}_coverage_{hours}h']=counts[:,j]/width
    if np.isinf(result.to_numpy()).any():raise ValueError('Infinite stable history input')
    return base,result
