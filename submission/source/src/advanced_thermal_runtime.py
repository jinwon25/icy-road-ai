"""실행 시 과거 열 상태를 계산한다. 연구용 정답·개발 지점 제한을 가져오지 않는다."""
import numpy as np
import pandas as pd
from .thermal_runtime import thermal_predictors,prepare_thermal


def advanced_predictors(frame,kind):
    if kind in ['thermal','thermal_history']:
        return thermal_predictors(frame,kind)
    if kind!='combined_thermal_history':raise ValueError('Unsupported thermal input contract')
    x,valid,stale=thermal_predictors(frame,'thermal_history')
    prepared,_,_=prepare_thermal(frame)
    columns=('asos_ground_temp','asos_cloud_tenths','asos_solar_mj_m2')
    names=[f'{c}_prior_mean_{m}m' for c in columns for m in (60,180,720)]
    history=pd.DataFrame(np.nan,index=prepared.index,columns=names)
    for _,part in prepared.groupby('station',sort=False):
        part=part.sort_values('time');times=pd.DatetimeIndex(part.time)
        for column in columns:
            values=part[column].to_numpy(float);known=np.isfinite(values)
            if (np.abs(values[known])>100_000).any():raise ValueError('Thermal history bound exceeded')
            integers=np.rint(np.where(known,values,0)*1_000_000)
            for minutes in (60,180,720):
                total=pd.Series(integers,index=times).rolling(f'{minutes}min',closed='left',min_periods=1).sum().to_numpy()
                count=pd.Series(known.astype(int),index=times).rolling(f'{minutes}min',closed='left',min_periods=1).sum().to_numpy()
                value=np.divide(total,count*1_000_000,out=np.full(len(part),np.nan),where=count>=np.ceil(.8*minutes/10))
                history.loc[part.index,f'{column}_prior_mean_{minutes}m']=np.round(value,6)
    return pd.concat([x,history],axis=1),valid,stale
