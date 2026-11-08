"""같은 관측쌍 회귀 비교와 날짜 블록 민감도."""
import numpy as np
import pandas as pd
STATIONS=["12410","23402","33411"]

def regression_numbers(observed, predicted):
    y = np.asarray(observed, float); p = np.asarray(predicted, float)
    good = np.isfinite(y) & np.isfinite(p); y = y[good]; p = p[good]
    if not len(y):
        return dict(n=0, mae=None, rmse=None, bias=None, correlation=None, r2=None)
    error = p-y
    variance = ((y-y.mean())**2).sum()
    corr = float(np.corrcoef(y, p)[0, 1]) if np.std(y)>0 and np.std(p)>0 else None
    return dict(n=len(y), mae=float(np.abs(error).mean()), rmse=float(np.sqrt((error**2).mean())),
                bias=float(error.mean()), correlation=corr,
                r2=float(1-(error**2).sum()/variance) if variance>0 else None)


def resampling(frame,target,methods,rng):
    # 세 지점에 같은 날짜를 적용하고 각 겨울 안에서 연속 7일을 순환 재표본화한다.
    days=[pd.date_range(f'{y}-11-01',f'{y+1}-03-01',inclusive='left',freq='D') for y in [2024,2025]]
    good=np.isfinite(frame[target])
    for col in methods.values():good &=np.isfinite(frame[col])
    z=frame.loc[good].copy();z['date']=z.time.dt.normalize()
    if not set(z.station)==set(STATIONS):
        return [dict(target=target,baseline=m,status='not_estimable_missing_site_observations',
            common_pairs=len(z),replicates=0,block_days=7) for m in methods if m!='estimated']
    arrays={}
    for method,col in methods.items():
        z['ae']=abs(z[col]-z[target])
        a=z.groupby(['station','date']).ae.agg(['sum','count'])
        arrays[method]=[np.array([[a.loc[(s,d),'sum'] if (s,d) in a.index else 0 for d in dates] for s in STATIONS]) for dates in days]
    counts=[np.array([[a.loc[(s,d),'count'] if (s,d) in a.index else 0 for d in dates] for s in STATIONS]) for dates in days]
    deltas={m:[] for m in methods if m!='estimated'}
    for _ in range(2000):
        index=[((rng.integers(0,len(d),size=int(np.ceil(len(d)/7)))[:,None]+np.arange(7))%len(d)).ravel()[:len(d)] for d in days]
        denominator=sum(c[:,ix].sum(axis=1) for c,ix in zip(counts,index))
        mae={m:np.mean(sum(a[:,ix].sum(axis=1) for a,ix in zip(groups,index))/denominator) for m,groups in arrays.items()}
        for m in deltas:deltas[m].append(mae['estimated']-mae[m])
    result=[]
    for method,values in deltas.items():
        values=np.asarray(values);lo,hi=np.quantile(values,[.025,.975])
        result.append(dict(target=target,baseline=method,delta_mae_percentile_2_5=float(lo),delta_mae_percentile_97_5=float(hi),
            bootstrap_fraction_delta_below_zero=float((values<0).mean()),replicates=len(values),block_days=7,
            interpretation='고정 3지점·두 겨울의 날짜 의존성 민감도; 새 도로 모집단의 신뢰구간이나 승률 아님'))
    return result

def evaluate(frame,target,methods):
    common=np.isfinite(frame[target])
    for col in methods.values():common &=np.isfinite(frame[col])
    rows=[]
    for scope,q in [('all',frame),*[(str(y),v) for y,v in frame.groupby('winter')]]:
        for station,z in [('pooled',q),*list(q.groupby('station'))]:
            good=common.loc[z.index];z=z.loc[good]
            for method,col in methods.items():
                rows.append(dict(target=target,period=scope,station=station,method=method,**regression_numbers(z[target],z[col])))
        for method in methods:
            site=[r for r in rows if r['target']==target and r['period']==scope and r['station'] in STATIONS and r['method']==method]
            assert len(site)==3
            complete=all(r['n']>0 for r in site)
            rows.append(dict(target=target,period=scope,station='station_macro',method=method,n=sum(r['n'] for r in site),
                available_stations=sum(r['n']>0 for r in site),
                **{k:float(np.mean([r[k] for r in site])) if complete else None for k in ['mae','bias','rmse']}))
    return rows

