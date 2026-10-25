"""확장 후보의 고정 혼합·날짜 블록 민감도·동일 결빙 사건 비교."""
import numpy as np
import pandas as pd


def physical_ice(frame, temperature):
    t=np.asarray(temperature,float)
    water=frame[['aws_dewpoint','rain15_max_3h','asos_snow_cm']].to_numpy(float)
    valid=np.isfinite(t)&~np.isnan(water).all(axis=1)
    wet=(water[:,0]>=t)|(water[:,1]>0)|(water[:,2]>0)
    return np.where(valid,(t<=0)&wet,np.nan).astype(float)


def block_sensitivity(frame,prediction,baseline,seed=20261024,draws=2000,block_days=7):
    """겨울 안의 연속 날짜 블록을 같은 지점 집합에서 쌍으로 재표집한다."""
    t=frame.road_temp.to_numpy(float);p=np.asarray(prediction,float);b=np.asarray(baseline,float)
    valid=np.isfinite(t)&np.isfinite(p)&np.isfinite(b)
    f=frame.loc[valid,['time','winter']].copy();f['new']=np.abs(p[valid]-t[valid]);f['old']=np.abs(b[valid]-t[valid]);f['n']=1
    f['date']=f.time.dt.normalize();parts=[]
    for _,w in f.groupby('winter'):
        grouped=w.groupby('date')[['new','old','n']].sum()
        grouped=grouped.reindex(pd.date_range(grouped.index.min(),grouped.index.max(),freq='D'),fill_value=0)
        parts.append(grouped.to_numpy(float))
    rng=np.random.default_rng(seed);differences=[];relative=[]
    for _ in range(draws):
        total=np.zeros(3)
        for values in parts:
            size=len(values);starts=rng.integers(0,size,size=int(np.ceil(size/block_days)))
            indexes=((starts[:,None]+np.arange(block_days)[None,:])%size).ravel()[:size]
            total+=values[indexes].sum(axis=0)
        differences.append((total[0]-total[1])/total[2]);relative.append(1-total[0]/total[1])
    return dict(draws=draws,block_days=block_days,seed=seed,
        mae_difference_quantiles=np.quantile(differences,[.025,.5,.975]).tolist(),
        relative_improvement_quantiles=np.quantile(relative,[.025,.5,.975]).tolist(),
        scope='고정된 개발 9곳·후보에 조건부인 날짜 민감도. 공간 모집단과 후보 선택의 불확실성은 포함하지 않음.')


def event_retention(frame,prediction,baseline):
    p=np.asarray(prediction,float);b=np.asarray(baseline,float)
    f=frame[['station','time','ice']].copy();f['new']=p;f['old']=b;records=[]
    for station,part in f.groupby('station'):
        part=part.sort_values('time').reset_index(drop=True)
        active=part.ice.eq(1)&part.new.notna()&part.old.notna()
        contiguous=part.time.diff().eq(pd.Timedelta(minutes=10))
        starts=active&~(active.shift(fill_value=False)&contiguous)
        ids=starts.cumsum()
        for _,event in part.loc[active].groupby(ids[active]):
            records.append(dict(station=station,start_kst=str(event.time.iloc[0]),slots=len(event),
                old_detected=int(event.old.eq(1).sum()),new_detected=int(event.new.eq(1).sum())))
    table=pd.DataFrame(records,columns=['station','start_kst','slots','old_detected','new_detected'])
    old=table.old_detected.gt(0);new=table.new_detected.gt(0)
    return dict(observed_events=len(table),baseline_detected=int(old.sum()),candidate_detected=int(new.sum()),
        lost_events=int((old&~new).sum()),gained_events=int((~old&new).sum())),table
