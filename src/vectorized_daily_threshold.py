"""날짜별 F1 변화량을 점수 순위에 누적하는 독립 임계값 검산. 원 순차 구현과 대조한다."""
import numpy as np
import pandas as pd


def threshold_curve(frame,scores,minimum=144):
    p=np.asarray(scores,float);y=frame.ice.to_numpy(float)
    if p.shape!=y.shape or np.isinf(p).any() or np.isinf(y).any():raise ValueError('Aligned finite or missing values required')
    if not np.isin(y[np.isfinite(y)],[0,1]).all() or frame.duplicated(['station','time']).any():raise ValueError('Unique binary targets required')
    valid=np.isfinite(p)&np.isfinite(y)
    if not valid.any() or set(frame.winter)!={2024,2025}:raise ValueError('Both winters and at least one scored pair required')
    population=sorted(frame.station.unique());site={s:i for i,s in enumerate(population)}
    unique=np.unique(p[valid])[::-1];rank=np.searchsorted(-unique,-p[valid]);target=y[valid].astype(int)
    f=frame.loc[valid,['station','time','winter']].copy();f['rank']=rank;f['target']=target;f['day']=f.time.dt.normalize()
    delta=np.zeros((3,len(population),len(unique)));enters=np.zeros_like(delta,dtype=np.int32)
    initial=np.zeros((3,len(population)),dtype=np.int32)
    for (station,year,_),day in f.groupby(['station','winter','day'],sort=False):
        if len(day)<minimum:continue
        st=site[station];levels,ids=np.unique(day['rank'].to_numpy(),return_inverse=True)
        n=np.bincount(ids);tp=np.bincount(ids,weights=day.target);positive=int(day.target.sum())
        values=2*np.cumsum(tp)/(positive+np.cumsum(n));changes=np.diff(np.r_[0.,values])
        for group in [0,int(year)-2023]:
            np.add.at(delta[group,st],levels,changes)
            if positive:initial[group,st]+=1
            else:enters[group,st,levels[0]]+=1
    sums=np.cumsum(delta,axis=2);counts=initial[:,:,None]+np.cumsum(enters,axis=2)
    means=np.divide(sums,counts,out=np.zeros_like(sums),where=counts>0).sum(axis=1)
    sizes=np.array([len(population),*[frame.loc[frame.winter.eq(year),'station'].nunique() for year in [2024,2025]]])
    metrics=np.clip(means/sizes[:,None],0,1)
    tp=np.cumsum(np.bincount(rank,weights=target,minlength=len(unique))).astype(int)
    fp=np.cumsum(np.bincount(rank,weights=1-target,minlength=len(unique))).astype(int)
    return pd.DataFrame(dict(threshold=np.r_[np.nextafter(unique[0],np.inf),unique],
        mean_f1=np.r_[0.,metrics[0]],worst_winter_f1=np.r_[0.,np.minimum(metrics[1],metrics[2])],
        f1_2024=np.r_[0.,metrics[1]],f1_2025=np.r_[0.,metrics[2]],
        tp=np.r_[0,tp],fp=np.r_[0,fp],fn=np.r_[target.sum(),target.sum()-tp]))


def select_threshold(table,track):
    eligible=table.loc[table[track].ge(table[track].max()-1e-12)]
    return eligible.sort_values(['fp','threshold'],ascending=[True,False],kind='stable').iloc[0].to_dict()
