"""과거 기상 과정 입력과 공식 일별 지표에 맞춘 재현율 제약 임계값 선택."""
import numpy as np
import pandas as pd
from src.anchored_icing import linear_features
from src.synoptic_icing import sample_weights

WEATHER = ['asos_air_temp','asos_ground_temp','asos_humidity','asos_rain_mm',
           'asos_snow_cm','asos_cloud_tenths','asos_solar_mj_m2','asos_wind_speed',
           'asos_dewpoint_obs','asos_pressure','asos_visibility','asos_new_snow3h','asos_soil5cm']
PROCESS = ['air','ground','cold','thaw','ground_cold','ground_thaw',
           'wet','drying','solar','ground_dew_gap']
WINDOWS = [60,360,1440]


def features(frame, kind):
    """허용된 기상·시각 열만 읽으며, 이력은 같은 지점의 엄격한 과거만 사용한다."""
    if kind not in ('snapshot','process'):
        raise ValueError('Unregistered representation')
    needed = {'station','time',*WEATHER}
    if not needed <= set(frame) or frame.duplicated(['station','time']).any():
        raise ValueError('Unique station/time weather rows required')
    f = frame.reset_index(drop=True).copy()
    f['time'] = pd.to_datetime(f.time)
    if f.time.dt.tz is not None or f.time.isna().any():
        raise ValueError('Naive KST timestamps required')
    if not f.time.eq(f.time.dt.floor('10min')).all():
        raise ValueError('Exact 10-minute grid required')
    x = linear_features(f)
    hour = f.time.dt.hour+f.time.dt.minute/60
    doy = f.time.dt.dayofyear
    x['hour_sin'] = np.sin(2*np.pi*hour/24)
    x['hour_cos'] = np.cos(2*np.pi*hour/24)
    x['season_sin'] = np.sin(2*np.pi*doy/365.25)
    x['season_cos'] = np.cos(2*np.pi*doy/365.25)
    if kind == 'snapshot':
        return x
    air,ground,rh = f.asos_air_temp,f.asos_ground_temp,f.asos_humidity
    # 0/1 수분 표시는 입력 관측이 알려져 있을 때만 산출한다.
    water = f[['asos_rain_mm','asos_snow_cm','asos_new_snow3h']].gt(0).any(axis=1).astype(float)
    water = water.where(f[['asos_rain_mm','asos_snow_cm','asos_new_snow3h']].notna().any(axis=1))
    z = pd.DataFrame(dict(air=air,ground=ground,cold=(-air).clip(lower=0),
        thaw=air.clip(lower=0),ground_cold=(-ground).clip(lower=0),
        ground_thaw=ground.clip(lower=0),wet=water,
        drying=(1-rh/100).clip(0,1)*(1+f.asos_wind_speed),
        solar=f.asos_solar_mj_m2,ground_dew_gap=ground-f.asos_dewpoint_obs))
    for minutes in WINDOWS:
        for col in PROCESS:
            x[f'{col}_prior_{minutes}m'] = np.nan
    for col in ['air','ground']:
        for minutes in [60,360]:
            x[f'{col}_change_{minutes}m'] = np.nan
    for _,group in f.groupby('station',sort=False):
        idx = group.sort_values('time').index
        t = f.loc[idx,'time'].to_numpy(dtype='datetime64[ns]')
        right = np.arange(len(idx))
        a = z.loc[idx].to_numpy(float)
        if np.isinf(a).any():
            raise ValueError('Infinite process input')
        finite = np.isfinite(a)
        sums = np.vstack([np.zeros(a.shape[1]),np.cumsum(np.where(finite,a,0.),axis=0)])
        counts = np.vstack([np.zeros(a.shape[1],dtype=int),np.cumsum(finite,axis=0)])
        for minutes in WINDOWS:
            left = np.searchsorted(t,t-np.timedelta64(minutes,'m'),side='left')
            n = counts[right]-counts[left]
            total = sums[right]-sums[left]
            values = np.divide(total,n,out=np.full_like(total,np.nan),where=n>=np.ceil(.8*minutes/10))
            for j,col in enumerate(PROCESS):
                # cold/thaw는 평균 강도를 시간 적분한 degree-hour. 다른 열은 과거 평균.
                value = values[:,j]*(minutes/60) if col in ['cold','thaw','ground_cold','ground_thaw'] else values[:,j]
                x.loc[idx,f'{col}_prior_{minutes}m'] = np.round(value,8)
        for col in ['air','ground']:
            s = pd.Series(z.loc[idx,col].to_numpy(),index=pd.DatetimeIndex(t))
            for minutes in [60,360]:
                past = s.reindex(s.index-pd.Timedelta(minutes=minutes)).to_numpy()
                x.loc[idx,f'{col}_change_{minutes}m'] = np.round(s.to_numpy()-past,8)
    if np.isinf(x.to_numpy(float)).any():
        raise ValueError('Infinite feature')
    return x


def weights(frame,kind):
    if kind == 'day':
        return sample_weights(frame,'day')
    if kind != 'station' or not frame.ice.isin([0,1]).all():
        raise ValueError('Planned weights and valid labels required')
    n = frame.groupby(['station','winter']).station.transform('size').to_numpy(float)
    w = 1/n
    return w/w.mean()


def binary_prediction(frame,scores,threshold):
    s = np.asarray(scores,float)
    if s.shape != (len(frame),) or not np.isfinite(s).all() or ((s<0)|(s>1)).any():
        raise ValueError('Aligned finite [0,1] scores required')
    return np.where(frame.available,(s>=threshold)&frame.asos_air_temp.le(2),np.nan)


def exact_threshold(frame,scores,recall_floor=.70,precision_f1_floor=0.):
    """같은 점수 묶음을 순회해 공식 F1/Precision 최적점을 각각 찾는다.

    실제 Ice가 없는 지점은 분모에서 제외한다. 정밀도는 경보가 있는 날짜와
    지점에서만 정의되므로 그 분모도 매 단계 갱신한다. 반환 점수는 보정 확률이 아니다.
    """
    score = np.asarray(scores,float)
    if score.shape != (len(frame),) or not np.isfinite(score).all() or ((score<0)|(score>1)).any():
        raise ValueError('Aligned finite model scores required')
    if not 0<=recall_floor<=1:
        raise ValueError('Recall floor out of range')
    if frame.duplicated(['station','time']).any():
        raise ValueError('Duplicate rows')
    yall = frame.ice.to_numpy(float)
    if not np.all(np.isnan(yall)|np.isin(yall,[0,1])):
        raise ValueError('Binary-or-missing outcomes required')
    population = sorted(frame.loc[frame.ice.eq(1),'station'].unique())
    if not population:
        raise ValueError('At least one actual-positive station required')
    keep = frame.available.to_numpy(bool)&np.isfinite(yall)&frame.station.isin(population).to_numpy()
    f = frame.loc[keep]
    y = yall[keep].astype(int)
    s = np.where(frame.asos_air_temp.le(2),score,0.)[keep]
    day,keys = pd.factorize(pd.MultiIndex.from_arrays([f.station,f.time.dt.normalize()]),sort=True)
    sid = np.array([population.index(v) for v in keys.get_level_values(0)])
    nd,ns = len(keys),len(population)
    positives = np.bincount(day,weights=y,minlength=nd)
    predicted = np.zeros(nd,int)
    true_positive = np.zeros(nd,int)
    sums = np.zeros((3,ns))
    count = np.zeros((3,ns),int)
    # recall and F1 are initially defined, equal to zero, on actual Ice days.
    for st in range(ns):
        count[1:,st] = int(((sid==st)&(positives>0)).sum())
    order = np.argsort(-s,kind='stable')
    tp=fp=0;best={'f1':None,'precision':None};distinct=0
    for pos,i in enumerate(order):
        if s[i]<=0:
            break
        d=day[i];st=sid[d]
        old_tp=true_positive[d];old_p=predicted[d];actual=positives[d]
        old_den=np.array([old_p,actual,actual+old_p],float)
        old_num=np.array([old_tp,old_tp,2*old_tp],float)
        old=np.divide(old_num,old_den,out=np.zeros(3),where=old_den>0)
        predicted[d]+=1;true_positive[d]+=y[i];tp+=y[i];fp+=1-y[i]
        new_tp=true_positive[d];new_p=predicted[d]
        den=np.array([new_p,actual,actual+new_p],float)
        num=np.array([new_tp,new_tp,2*new_tp],float)
        value=np.divide(num,den,out=np.zeros(3),where=den>0)
        sums[:,st]+=value-old
        count[:,st]+=(den>0).astype(int)-(old_den>0).astype(int)
        if pos+1<len(order) and s[order[pos+1]]==s[i]:
            continue
        distinct+=1
        station_means=np.divide(sums,count,out=np.zeros_like(sums),where=count>0)
        metrics=np.array([station_means[k,count[k]>0].mean() if (count[k]>0).any() else 0. for k in range(3)])
        if metrics[1]+1e-12<recall_floor:
            continue
        row=dict(threshold=float(s[i]),precision=float(metrics[0]),recall=float(metrics[1]),
                 f1=float(metrics[2]),tp=int(tp),fp=int(fp))
        for track in ['f1','precision']:
            if track=='precision' and row['f1']+1e-12<precision_f1_floor:
                continue
            current=best[track]
            if current is None or row[track]>current[track]+1e-12 or (
                abs(row[track]-current[track])<=1e-12 and (row['fp'],-row['threshold'])<(current['fp'],-current['threshold'])):
                best[track]=row.copy()
    for value in best.values():
        if value is not None:
            value.update(unique_thresholds=distinct,eligible_stations=ns)
    return best
