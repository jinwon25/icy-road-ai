"""ASOS 기준선의 판정을 제한적으로 보정하고 지역별 양성 보존을 확인한다."""
import numpy as np
import pandas as pd

ASOS_FEATURES=['asos_air_temp','asos_ground_temp','asos_humidity','asos_rain_mm','asos_snow_cm',
               'asos_cloud_tenths','asos_solar_mj_m2','asos_wind_speed','asos_dewpoint_obs',
               'asos_pressure','asos_visibility','asos_new_snow3h','asos_soil5cm']


def linear_features(frame):
    x=frame[ASOS_FEATURES].copy()
    x['dewpoint_depression']=frame.asos_air_temp-frame.asos_dewpoint_obs
    x['ground_dewpoint_gap']=frame.asos_ground_temp-frame.asos_dewpoint_obs
    if np.isinf(x.to_numpy(float)).any():raise ValueError('Infinite weather feature')
    return x


def anchored_prediction(air,score,bound,direction):
    a=np.asarray(air,float);s=np.asarray(score,float)
    if a.shape!=s.shape or a.ndim!=1 or not np.isfinite(bound) or not 0<=bound<=2:raise ValueError('Invalid aligned bounded correction')
    if np.isinf(a).any() or not np.isfinite(s).all() or ((s<0)|(s>1)).any():raise ValueError('Invalid temperature or model score')
    delta=bound*(2*s-1)
    if direction=='reject_only':delta=np.minimum(delta,0)
    elif direction!='symmetric':raise ValueError('Unknown correction direction')
    return np.where(np.isfinite(a),a<=delta,np.nan)


def binary_matrix_metrics(frame,predictions):
    """공통 가용 행을 쓰는 다수 고정 정책의 완전 날짜 F1과 관측 보존율."""
    p=np.asarray(predictions,float)
    if p.ndim!=2 or p.shape[0]!=len(frame) or not np.isin(p[np.isfinite(p)],[0,1]).all():raise ValueError('Aligned binary matrix required')
    available=frame.available.to_numpy(bool)
    if not np.array_equal(np.isfinite(p),np.broadcast_to(available[:,None],p.shape)):raise ValueError('Availability differs by policy')
    mask=available&frame.ice.isin([0,1]).to_numpy();f=frame.loc[mask];y=f.ice.to_numpy(int);p=p[mask].astype(int)
    stations=sorted(frame.station.unique());day,keys=pd.factorize(pd.MultiIndex.from_arrays([f.station,f.time.dt.normalize()]),sort=True)
    n=np.bincount(day,minlength=len(keys));positive=np.bincount(day,weights=y,minlength=len(keys));ds=np.array([stations.index(k) for k in keys.get_level_values(0)])
    output=[]
    for col in p.T:
        tp=np.bincount(day,weights=y*col,minlength=len(keys));fp=np.bincount(day,weights=(1-y)*col,minlength=len(keys));fn=positive-tp
        den=2*tp+fp+fn;active=(n>=144)&(den>0);values=np.divide(2*tp,den,out=np.zeros(len(keys)),where=active)
        total=np.bincount(ds,weights=values,minlength=len(stations));count=np.bincount(ds,weights=active,minlength=len(stations))
        score=np.divide(total,count,out=np.zeros(len(stations)),where=count>0).mean()
        output.append(dict(mean_f1=float(score),fp=int(fp.sum()),fn=int(fn.sum()),tp=int(tp.sum())))
    table=pd.DataFrame(output)
    base=f.asos_air_temp.le(0).to_numpy()&y.astype(bool);retention=np.ones(p.shape[1])
    for _,idx in f.reset_index(drop=True).groupby(['group','winter']).indices.items():
        denominator=int(base[idx].sum())
        if denominator:retention=np.minimum(retention,(p[idx]*base[idx,None]).sum(axis=0)/denominator)
    table['minimum_group_winter_retention']=retention
    return table


def choose_policy(table,track):
    if track=='retention_guard':
        base=table.loc[table.candidate.eq('asos_zero')].iloc[0]
        table=table.loc[table.minimum_group_winter_retention.ge(.98)&table.f1_2024.ge(base.f1_2024)&table.f1_2025.ge(base.f1_2025)]
        if table.empty:return base.to_dict()
        metric='mean_f1'
    elif track in ['mean_f1','worst_winter_f1']:metric=track
    else:raise ValueError('Unknown predeclared selection track')
    return table.sort_values([metric,'fp','complexity','candidate'],ascending=[False,True,True,True],kind='stable').iloc[0].to_dict()
