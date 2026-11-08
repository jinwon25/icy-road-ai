"""엄격한 과거 ASOS 관측의 짧은 감쇠 누적. 노면 관측을 대신하는 대리 특성이다."""
import numpy as np
import pandas as pd
from scipy.signal import lfilter
from src.icing_precision_20261106 import features as prior_features

TAUS=(10,30,120)

def features(frame):
    f=frame.reset_index(drop=True)
    assert not f.duplicated(['station','time']).any()
    x=prior_features(f,'snapshot')
    for station,g in f.groupby('station',sort=False):
        idx=g.sort_values('time').index
        t=pd.DatetimeIndex(f.loc[idx,'time'])
        gap=np.r_[True,np.diff(t.asi8)!=600_000_000_000]
        for tempcol,label in [('asos_air_temp','air'),('asos_ground_temp','ground')]:
            temp=f.loc[idx,tempcol].to_numpy(float)
            dew=f.loc[idx,'asos_dewpoint_obs'].to_numpy(float)
            prev=np.r_[np.nan,temp[:-1]]
            crossing=np.where(np.isfinite(prev)&np.isfinite(temp)&(prev!=0)&(temp!=0),np.sign(prev)!=np.sign(temp),np.nan)
            z={'cold':np.maximum(-temp,0),'thaw':np.maximum(temp,0),
               'deposition_proxy':np.where(temp<=0,np.maximum(dew-temp,0),0.),'crossing':crossing}
            z['deposition_proxy'][~np.isfinite(temp)|~np.isfinite(dew)]=np.nan
            for name,values in z.items():
                good=np.isfinite(values)
                starts=np.flatnonzero(gap|~good|np.r_[True,~good[:-1]])
                ends=np.r_[starts[1:],len(idx)]
                for tau in TAUS:
                    result=np.full(len(idx),np.nan);a=np.exp(-10/tau)
                    scale=1. if name=='crossing' else (tau/60)*(1-a)
                    for begin,end in zip(starts,ends):
                        if not good[begin]:continue
                        part=values[begin:end]
                        past=np.r_[0.,part[:-1]]
                        accumulated=lfilter([scale],[1.,-a],past)
                        # Hide uninitialised histories until three decay times have elapsed.
                        elapsed=np.arange(end-begin)*10
                        result[begin:end]=np.where(elapsed>=3*tau,accumulated,np.nan)
                    x.loc[idx,f'{label}_{name}_past_tau{tau}m']=np.round(result,8)
            series=pd.Series(temp,index=t)
            for minutes in [10,30,60]:
                # Both end points precede the target: compare t-10 with t-10-window.
                a=series.reindex(t-pd.Timedelta(minutes=10)).to_numpy()
                b=series.reindex(t-pd.Timedelta(minutes=10+minutes)).to_numpy()
                x.loc[idx,f'{label}_prior_change_{minutes}m']=np.round(a-b,8)
    assert not np.isinf(x.to_numpy(float)).any()
    return x
