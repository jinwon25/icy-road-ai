"""기상 이력에 공공 지면온도·운량·일사의 과거 상태를 더하는 고정 대조."""
import numpy as np
import pandas as pd
from src.thermal_extended import feature_table as base_features

MEMORY_COLUMNS=('asos_ground_temp','asos_cloud_tenths','asos_solar_mj_m2')
MEMORY_WINDOWS=(60,180,720)


def thermal_memory(frame):
    columns=[f'{c}_prior_mean_{m}m' for c in MEMORY_COLUMNS for m in MEMORY_WINDOWS]
    output=pd.DataFrame(np.nan,index=frame.index,columns=columns)
    for _,part in frame.groupby('station',sort=False):
        part=part.sort_values('time');times=part.time.to_numpy(dtype='datetime64[ns]');right=np.arange(len(part))
        if len(part)>1_000_000:raise ValueError('Fixed-point safety bound exceeded')
        for column in MEMORY_COLUMNS:
            values=part[column].to_numpy(float);good=np.isfinite(values)
            if np.isinf(values).any() or (np.abs(values[good])>100_000).any():raise ValueError('Invalid thermal memory')
            integers=np.rint(np.where(good,values,0)*1_000_000).astype(np.int64)
            sums=np.r_[np.int64(0),np.cumsum(integers,dtype=np.int64)];counts=np.r_[np.int64(0),np.cumsum(good,dtype=np.int64)]
            for minutes in MEMORY_WINDOWS:
                left=np.searchsorted(times,times-np.timedelta64(minutes,'m'),side='left')
                n=counts[right]-counts[left];total=sums[right]-sums[left]
                result=np.divide(total,n*1_000_000,out=np.full(len(part),np.nan),where=n>=np.ceil(.8*minutes/10))
                output.loc[part.index,f'{column}_prior_mean_{minutes}m']=np.round(result,6)
    return output


def feature_table(frame,kind='combined_thermal_history'):
    if kind!='combined_thermal_history':raise ValueError('Combined thermal history required')
    return pd.concat([base_features(frame,'thermal_history'),thermal_memory(frame)],axis=1)
