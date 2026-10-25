"""같은 입력의 혼합 정답 진단과 과거 두 관측만 쓰는 제한 외삽."""
import numpy as np
import pandas as pd


def collision_summary(features,labels):
    x=features.reset_index(drop=True).copy();y=np.asarray(labels)
    if len(x)!=len(y) or not np.isin(y,[0,1]).all() or not len(x):raise ValueError('Aligned valid labels required')
    codes=x.groupby(list(x),dropna=False,sort=False,observed=True).ngroup().to_numpy()
    n=np.bincount(codes);positive=np.bincount(codes,weights=y).astype(int);negative=n-positive
    mixed=(positive>0)&(negative>0);order=np.argsort(-(positive/n),kind='stable')
    tp=np.cumsum(positive[order]);fp=np.cumsum(negative[order]);total=int(positive.sum())
    f1=np.divide(2*tp,total+tp+fp,out=np.zeros(len(tp),float),where=total+tp+fp>0)
    return dict(rows=len(x),positive_rows=total,unique_inputs=len(n),mixed_input_groups=int(mixed.sum()),mixed_rows=int(n[mixed].sum()),
        positive_rows_in_mixed_groups=int(positive[mixed].sum()),minimum_observed_errors=int(np.minimum(positive,negative).sum()),
        minimum_fp_if_all_observed_positives_retained=int(negative[positive>0].sum()),
        label_aware_pooled_f1_upper_bound=float(f1.max()),
        interpretation='Finite-sample deterministic input equivalence diagnostic, not a predictive model, daily-F1 bound, or out-of-sample score')


def past_hour_trend(frame):
    required=['station','time','asos_source_time','asos_air_temp','asos_age_minutes']
    if list(frame)!=required:raise ValueError('Only declared weather keys may be supplied')
    f=frame.reset_index(drop=True).copy();f['__order']=np.arange(len(f))
    if f.duplicated(['station','time']).any():raise ValueError('Duplicate query time')
    known=f.asos_source_time.notna()
    if not (f.loc[known,'asos_source_time']<f.loc[known,'time']).all():raise ValueError('Future or concurrent observation forbidden')
    ages=(f.loc[known,'time']-f.loc[known,'asos_source_time']).dt.total_seconds()/60
    if not np.allclose(ages,f.loc[known,'asos_age_minutes'],atol=1e-10,rtol=0):raise ValueError('Observation age mismatch')
    unique=f.loc[known,['station','asos_source_time','asos_air_temp']].drop_duplicates()
    if unique.duplicated(['station','asos_source_time']).any():raise ValueError('Conflicting weather values for source hour')
    unique=unique.sort_values(['station','asos_source_time'])
    prev=unique.groupby('station',sort=False).shift(1)
    valid=(unique.asos_source_time-prev.asos_source_time).eq(pd.Timedelta(hours=1))
    delta=unique.asos_air_temp-prev.asos_air_temp
    valid &= np.isfinite(delta)&delta.abs().le(10)
    unique['trend_c_per_hour']=delta.where(valid)
    result=f.merge(unique.drop(columns='asos_air_temp'),on=['station','asos_source_time'],how='left',validate='many_to_one').sort_values('__order')
    eligible=result.asos_age_minutes.between(0,60,inclusive='right')&result.trend_c_per_hour.notna()
    return pd.DataFrame({'trend_c_per_hour':result.trend_c_per_hour.where(eligible).to_numpy(),
        'trend_available':eligible.to_numpy()},index=frame.index)


def extrapolated_temperature(air,age,trend,alpha,cap):
    a=np.asarray(air,float);t=np.asarray(age,float);s=np.asarray(trend,float)
    if a.ndim!=1 or a.shape!=t.shape or a.shape!=s.shape or not 0<=alpha<=1 or not 0<cap<=2:raise ValueError('Invalid inputs')
    if np.isinf(a).any() or np.isinf(s).any():raise ValueError('Infinite weather')
    usable=np.isfinite(s)&(t>0)&(t<=60)
    return a+np.where(usable,np.clip(alpha*s*t/60,-cap,cap),0)
