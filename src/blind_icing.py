"""새 지역 평가 전용 입력·지표. 기존 개발/보호 영역의 허용 목록을 넓히지 않는다."""
import numpy as np
import pandas as pd

FIELDS = {
    'TA': ('air_temp', -60, 70), 'TS': ('ground_temp', -60, 70),
    'HM': ('humidity', 0, 100), 'RN': ('rain_mm', 0, 500),
    'SD_TOT': ('snow_cm', 0, 500), 'CA_TOT': ('cloud_tenths', 0, 10),
    'SI': ('solar_mj_m2', 0, 10), 'WS': ('wind_speed', 0, 100),
    'TD': ('dewpoint_obs', -80, 50), 'PA': ('pressure', 500, 1100),
    'VS': ('visibility', 0, 10000), 'SD_HR3': ('new_snow3h', 0, 500),
    'TE_005': ('soil5cm', -60, 80),
}
METRICS = ('precision', 'recall', 'f1')


def normalize_weather(raw):
    """온도 -9는 실제 값. 비음수 변수 -9 및 범위 밖 값은 0으로 대체하지 않는다."""
    f = pd.DataFrame({'station': raw.STN.astype(str), 'source_time': pd.to_datetime(raw.time)})
    if f.duplicated(['station', 'source_time']).any():
        raise ValueError('Duplicate hourly weather')
    for code, (name, low, high) in FIELDS.items():
        x = pd.to_numeric(raw[code], errors='raise')
        f[name] = x.where(np.isfinite(x) & x.between(low, high))
    return f.sort_values(['station', 'source_time']).reset_index(drop=True)


def daily_metrics(frame, prediction, population, winters, min_slots=144):
    """선언한 전체 날짜·지점 분모를 보존하고 미정의 일별 지표는 NaN으로 남긴다."""
    if min_slots not in (1, 72, 144):
        raise ValueError('Unplanned coverage sensitivity')
    f = frame[['station', 'time', 'ice']].copy()
    pop = list(map(str, population)); f.station = f.station.astype(str)
    if len(pop) != len(set(pop)) or not set(f.station) <= set(pop) or f.duplicated(['station','time']).any():
        raise ValueError('Unique declared population and observations required')
    dates = pd.DatetimeIndex(np.concatenate([pd.date_range(a,b,freq='D',inclusive='left').values for a,b in winters]))
    if dates.duplicated().any() or not f.time.dt.normalize().isin(dates).all() or f.time.dt.tz is not None:
        raise ValueError('Rows outside fixed KST calendar')
    p = np.asarray(prediction, float); y = f.ice.to_numpy(float)
    if p.shape != y.shape or not np.isin(p[np.isfinite(p)],[0,1]).all() or np.isinf(p).any() or not (np.isnan(y)|np.isin(y,[0,1])).all():
        raise ValueError('Binary or missing labels/predictions required')
    valid = np.isin(y,[0,1]) & np.isfinite(p)
    rows = pd.DataFrame({'station':f.station,'date_kst':f.time.dt.normalize(), 'valid_slots':valid.astype(int),
        'tp':(valid&(y==1)&(p==1)).astype(int),'fp':(valid&(y==0)&(p==1)).astype(int),
        'fn':(valid&(y==1)&(p==0)).astype(int),'tn':(valid&(y==0)&(p==0)).astype(int)})
    idx = pd.MultiIndex.from_product([pop,dates],names=['station','date_kst'])
    d = rows.groupby(['station','date_kst']).sum().reindex(idx,fill_value=0).reset_index()
    if d.valid_slots.gt(144).any(): raise ValueError('More than 144 ten-minute rows')
    d['coverage_accepted'] = d.valid_slots.ge(min_slots)
    for metric, den in [('precision',d.tp+d.fp),('recall',d.tp+d.fn),('f1',2*d.tp+d.fp+d.fn)]:
        d[metric] = ((2 if metric=='f1' else 1)*d.tp/den.where(den.gt(0))).where(d.coverage_accepted)
    return d


def summarize_days(days, population):
    station = days.groupby('station')[list(METRICS)].mean().reindex(population)
    summary = {'f1_fixed_population':float(station.f1.fillna(0).mean()),
               'complete_or_accepted_days':int(days.coverage_accepted.sum()), 'planned_days':len(days)}
    for metric in METRICS:
        v = station[metric].dropna()
        summary[metric+'_available_station_mean'] = float(v.mean()) if len(v) else None
        summary[metric+'_defined_stations'] = len(v)
    for k in ['tp','fp','fn','tn']: summary[k] = int(days[k].sum())
    summary['valid_rows'] = int(days.valid_slots.sum())
    t,p,n = summary['tp'],summary['fp'],summary['fn']
    summary['pooled_f1'] = 2*t/(2*t+p+n) if 2*t+p+n else None
    summary['station_f1_fixed'] = {s:float(v) for s,v in station.f1.fillna(0).items()}
    return summary


def event_table(frame, prediction, baseline):
    """공통 가용 구간의 연속 양성 10분 관측을 한 사건으로 센다. 공백에서 분리한다."""
    f=frame[['station','time','ice']].copy();f['p']=np.asarray(prediction,float);f['b']=np.asarray(baseline,float)
    f=f.sort_values(['station','time']);active=f.ice.eq(1)&f.p.notna()&f.b.notna()
    contiguous=f.station.eq(f.station.shift())&f.time.diff().eq(pd.Timedelta(minutes=10))
    event=(~active|~active.shift(fill_value=False)|~contiguous).cumsum()
    rows=[]
    for _,g in f.loc[active].groupby(event[active]):
        old=bool(g.b.eq(1).any());new=bool(g.p.eq(1).any())
        rows.append(dict(station=g.station.iloc[0],start=g.time.iloc[0],end=g.time.iloc[-1],slots=len(g),
                         baseline_detected=old,candidate_detected=new,lost=old and not new,gained=new and not old))
    e=pd.DataFrame(rows,columns=['station','start','end','slots','baseline_detected','candidate_detected','lost','gained'])
    return dict(observed_events=len(e),baseline_detected=int(e.baseline_detected.sum()),candidate_detected=int(e.candidate_detected.sum()),
                lost_events=int(e.lost.sum()),gained_events=int(e.gained.sum())),e


def paired_bootstrap(baseline, candidate, population, draws=2000, seed=20261025):
    """같은 지점·날짜 재표집으로 정책 차이를 비교. 지역 모집단 독립 CI가 아니다."""
    pd.testing.assert_frame_equal(baseline[['station','date_kst']],candidate[['station','date_kst']])
    rng=np.random.default_rng(seed);deltas=np.zeros(draws)
    for station in population:
        b=baseline.loc[baseline.station.eq(station),'f1'].to_numpy(float)
        c=candidate.loc[candidate.station.eq(station),'f1'].to_numpy(float)
        idx=rng.integers(0,len(b),size=(draws,len(b)))
        def mean_zero(x):
            z=x[idx];counts=np.isfinite(z).sum(axis=1)
            return np.divide(np.nansum(z,axis=1),counts,out=np.zeros(draws),where=counts>0)
        deltas+=(mean_zero(c)-mean_zero(b))/len(population)
    return dict(draws=draws,seed=seed,difference_ci95=np.quantile(deltas,[.025,.975]).tolist(),
                positive_fraction=float((deltas>0).mean()),scope='Conditional on four sites; days may be serially dependent, not a regional population confidence guarantee')
