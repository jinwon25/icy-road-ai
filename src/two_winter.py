"""명시적으로 재분류한 비보호 두 겨울 개발 범위와 집계. 과거 독립 평가와 별도."""
import numpy as np
import pandas as pd
from src.method_blending import ALLOWED
from src.award_ice import history_features,THRESHOLDS
from src.qa633_metrics import daily_table,aggregate


def validate(frame):
    if frame.empty or not set(frame.station)<=ALLOWED or frame.duplicated(['station','time']).any():
        raise ValueError('Unique allowed development stations required')
    t=pd.to_datetime(frame.time)
    allowed=(t.ge('2024-11-01')&t.lt('2025-03-01'))|(t.ge('2025-11-01')&t.lt('2026-03-01'))
    if t.dt.tz is not None or not allowed.all() or not t.eq(t.dt.floor('10min')).all():
        raise ValueError('Two explicit winter KST grids required')
    return frame


def history(frame):
    validate(frame);f=frame.reset_index(drop=True);parts=[]
    for winter,part in f.groupby('winter'):
        shifted=part.copy()
        if winter==2025:shifted['time']=shifted.time-pd.DateOffset(years=1)
        x=history_features(shifted);x.index=part.index;parts.append(x)
    return pd.concat(parts).sort_index()


def daily(frame,prediction,minimum=144):
    validate(frame);f=frame.copy();f['_prediction']=np.asarray(prediction)
    pop=sorted(f.station.unique());parts=[]
    for winter,part in f.groupby('winter'):
        part=part.copy()
        if winter==2025:part['time']=part.time-pd.DateOffset(years=1)
        d=daily_table(part,part['_prediction'],pop,minimum)
        if winter==2025:d['date_kst']=d.date_kst+pd.DateOffset(years=1)
        parts.append(d)
    days=pd.concat(parts,ignore_index=True);report,stations=aggregate(days,pop)
    report['f1_fixed_population']=float(stations.f1.fillna(0).mean())
    return report,stations,days


def curve(frame,scores,thresholds=THRESHOLDS):
    validate(frame);s=np.asarray(scores,float);ts=np.asarray(thresholds,float)
    if s.shape!=(len(frame),) or not np.isfinite(s).all():raise ValueError('Finite aligned score required')
    valid=frame.ice.isin([0,1]).to_numpy();y=frame.ice.to_numpy(float)[valid].astype(int)
    pop=sorted(frame.station.unique())
    day,keys=pd.factorize(pd.MultiIndex.from_arrays([frame.station[valid],frame.time[valid].dt.normalize()]),sort=True)
    ds=np.array([pop.index(k) for k in keys.get_level_values(0)])
    nd,nt=len(keys),len(ts);n=np.bincount(day,minlength=nd);positive=np.bincount(day,weights=y,minlength=nd)
    bins=np.searchsorted(ts,s[valid],side='right')
    def counts(weights):
        h=np.bincount(day*(nt+1)+bins,weights=weights,minlength=nd*(nt+1)).reshape(nd,nt+1)
        return np.cumsum(h[:,::-1],axis=1)[:,::-1][:,1:]
    tp,fp=counts(y),counts(1-y);fn=positive[:,None]-tp;den=2*tp+fp+fn
    active=(n[:,None]>=144)&(den>0);values=np.divide(2*tp,den,out=np.zeros_like(tp),where=active)
    sums=np.zeros((len(pop),nt));numbers=np.zeros_like(sums)
    np.add.at(sums,ds,values);np.add.at(numbers,ds,active)
    avg=np.divide(sums,numbers,out=np.zeros_like(sums),where=numbers>0).mean(axis=0)
    return pd.DataFrame(dict(threshold=ts,f1_fixed_population=avg,fp=fp.sum(axis=0),fn=fn.sum(axis=0),tp=tp.sum(axis=0)))
