"""2026-11-06 확인한 Q&A 556·633·693·716에 따른 날짜→지점 집계.

부분 날짜의 최소 유효 관측 수는 공식 답변에 없으므로 매 호출에서 명시한다.
이 모듈은 정답을 입력받아 집계만 하며 모델 학습·선택을 수행하지 않는다.
"""
import numpy as np
import pandas as pd
from src.validation import canonical_station_id

METRICS=('precision','recall','f1')
WINTERS=(('2024-11-01','2025-03-01'),('2025-11-01','2026-03-01'))


def evaluate(frame,predictions,*,minimum_valid_slots,station_population=None,winters=WINTERS):
    if isinstance(minimum_valid_slots,bool) or not isinstance(minimum_valid_slots,int) or not 1<=minimum_valid_slots<=144:
        raise ValueError('Explicit minimum_valid_slots from 1 to 144 required')
    f=frame[['station','time','ice']].copy()
    f['station']=f.station.map(canonical_station_id)
    if f.station.eq('<missing>').any():raise ValueError('Missing station ID')
    f['time']=pd.to_datetime(f.time,errors='raise')
    if f.time.dt.tz is not None:f['time']=f.time.dt.tz_convert('Asia/Seoul').dt.tz_localize(None)
    if f.time.isna().any() or ((f.time.dt.minute%10!=0)|f.time.dt.second.ne(0)|f.time.dt.microsecond.ne(0)).any():
        raise ValueError('Exact ten-minute KST timestamps required; no time tolerance')
    if f.duplicated(['station','time']).any():raise ValueError('Duplicate station/time')
    y=pd.to_numeric(f.ice,errors='raise').to_numpy(dtype=float,na_value=np.nan)
    p=pd.to_numeric(pd.Series(predictions),errors='raise').to_numpy(dtype=float,na_value=np.nan)
    if p.shape!=(len(f),) or not np.all(np.isnan(p)|np.isin(p,[0,1])) or not np.all(np.isnan(y)|np.isin(y,[0,1])):
        raise ValueError('Aligned binary-or-missing observations/predictions required')
    pop=sorted(f.station.unique()) if station_population is None else [canonical_station_id(s) for s in station_population]
    if not pop or len(pop)!=len(set(pop)) or not set(f.station)<=set(pop):raise ValueError('Unique station population required')
    calendars=[];in_range=np.zeros(len(f),dtype=bool)
    for start,end in winters:
        a,b=pd.Timestamp(start),pd.Timestamp(end)
        if a!=a.normalize() or b!=b.normalize() or not a<b:raise ValueError('Whole KST dates required')
        calendars.extend(pd.date_range(a,b-pd.Timedelta(days=1),freq='D'))
        in_range|=(f.time.ge(a)&f.time.lt(b)).to_numpy()
    if len(calendars)!=len(set(calendars)) or not in_range.all():raise ValueError('Unique declared calendar containing all rows required')
    # 지점 제외 여부는 예측 가용성·경보 유무가 아니라 전체 기간의 유효 관측 정답으로 결정한다.
    census=pd.DataFrame({'station':f.station,'observed_slots':np.isfinite(y).astype(int),'observed_ice_slots':(y==1).astype(int)}).groupby('station').sum().reindex(pop,fill_value=0)
    paired=np.isfinite(y)&np.isfinite(p)
    raw=pd.DataFrame({'station':f.station,'date_kst':f.time.dt.normalize(),
        'valid_slots':paired.astype(int),'tp':(paired&(y==1)&(p==1)).astype(int),
        'fp':(paired&(y==0)&(p==1)).astype(int),'fn':(paired&(y==1)&(p==0)).astype(int),
        'tn':(paired&(y==0)&(p==0)).astype(int)})
    grid=pd.MultiIndex.from_product([pop,calendars],names=['station','date_kst'])
    days=raw.groupby(['station','date_kst']).sum().reindex(grid,fill_value=0).reset_index()
    days['coverage_accepted']=days.valid_slots.ge(minimum_valid_slots)
    days['expected_slots']=144
    for metric,den in [('precision',days.tp+days.fp),('recall',days.tp+days.fn),('f1',2*days.tp+days.fp+days.fn)]:
        num=2*days.tp if metric=='f1' else days.tp
        days[metric]=num.div(den.where(den.gt(0))).where(days.coverage_accepted)
    days['station_eligible']=days.station.map(census.observed_ice_slots.gt(0))
    station_rows=[]
    for station in pop:
        q=days.loc[days.station.eq(station)]
        actual=census.loc[station];eligible=bool(actual.observed_ice_slots>0)
        record=dict(station=station,observed_slots=int(actual.observed_slots),observed_ice_slots=int(actual.observed_ice_slots),
            eligible=eligible,status='calculated' if eligible else '산출불가: 실제 결빙 없음',
            planned_days=len(q),coverage_days=int(q.coverage_accepted.sum()))
        for metric in METRICS:
            values=q.loc[q.coverage_accepted,metric].dropna() if eligible else pd.Series(dtype=float)
            record[metric+'_days']=len(values);record[metric]=float(values.mean()) if len(values) else np.nan
        if eligible and not np.isfinite(record['f1']):record['status']='산출불가: 유효 예측쌍 부족'
        station_rows.append(record)
    stations=pd.DataFrame(station_rows)
    result=dict(rule_version='official_qa_20261106',population_stations=len(pop),actual_ice_stations=int(stations.eligible.sum()),
        excluded_no_ice_stations=stations.loc[~stations.eligible,'station'].tolist(),minimum_valid_slots=minimum_valid_slots,
        minimum_coverage_officially_confirmed=False,exact_timestamp_matching=True,
        station_without_actual_ice_excluded=True,official_competition_score=False)
    for metric in METRICS:
        values=stations.loc[stations.eligible,metric].dropna()
        result[metric]=float(values.mean()) if len(values) else None
        result[metric+'_stations']=len(values);result[metric+'_days']=int(stations[metric+'_days'].sum())
    for count in ['tp','fp','fn','tn']:
        result[count]=int(days.loc[days.coverage_accepted,count].sum())
    result['pooled_counts_scope']='all declared stations with accepted dates; station eligibility is applied only to macro metrics'
    return result,stations,days