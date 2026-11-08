"""가까운 AWS의 엄격한 과거 냉각·해빙·건조·강수 이력을 감쇠 누적한다."""
import numpy as np,pandas as pd
from scipy.signal import lfilter
from src.icing_precision_20261106 import features as prior_features
TAUS=(10,30,120)
def features(frame):
    f=frame.reset_index(drop=True);assert not f.duplicated(['station','time']).any();x=prior_features(f,'snapshot')
    good=f.aws_age_minutes.between(0,60,inclusive='right')
    for col in ['aws_air_temp','aws_humidity','aws_wind_speed','aws_rain_15m','aws_dewpoint']:
        x[col]=f[col].where(good).to_numpy(float)
    x['aws_age_minutes']=f.aws_age_minutes
    for _,g in f.groupby('station',sort=False):
        idx=g.sort_values('time').index;t=pd.DatetimeIndex(f.loc[idx,'time']);gap=np.r_[True,np.diff(t.asi8)!=600_000_000_000]
        air=x.loc[idx,'aws_air_temp'].to_numpy(float);rh=x.loc[idx,'aws_humidity'].to_numpy(float);wind=x.loc[idx,'aws_wind_speed'].to_numpy(float);rain=x.loc[idx,'aws_rain_15m'].to_numpy(float)
        z={'cold':np.maximum(-air,0),'thaw':np.maximum(air,0),'drying_proxy':np.clip(1-rh/100,0,1)*(1+np.maximum(wind,0)),'rain_proxy':np.maximum(rain,0)}
        for name,values in z.items():
            finite=np.isfinite(values);starts=np.flatnonzero(gap|~finite|np.r_[True,~finite[:-1]]);ends=np.r_[starts[1:],len(idx)]
            for tau in TAUS:
                result=np.full(len(idx),np.nan);a=np.exp(-10/tau);scale=(tau/60)*(1-a)
                for begin,end in zip(starts,ends):
                    if not finite[begin]:continue
                    past=np.r_[0.,values[begin:end-1]];integral=lfilter([scale],[1.,-a],past);elapsed=np.arange(end-begin)*10
                    result[begin:end]=np.where(elapsed>=3*tau,integral,np.nan)
                x.loc[idx,f'air_{name}_past_tau{tau}m']=np.round(result,8)
        series=pd.Series(air,index=t)
        for minutes in [10,30,60]:
            a=series.reindex(t-pd.Timedelta(minutes=10)).to_numpy();b=series.reindex(t-pd.Timedelta(minutes=10+minutes)).to_numpy()
            x.loc[idx,f'air_prior_change_{minutes}m']=np.round(a-b,8)
    assert not np.isinf(x.to_numpy(float)).any()
    return x
