"""공간 제외 온도와 기상 조건의 고정 결합. 선택과 판정을 분리한다."""
from itertools import product
import numpy as np
import pandas as pd
from src.method_blending import domain


def policies(plan):
    result={}
    for source,threshold,moisture,slots,union in product(plan['cold_sources'],plan['cold_threshold_celsius'],
            plan['moisture_gates'],plan['minimum_consecutive_slots'],plan['union_current']):
        name=f'{source}_t{threshold:+.1f}_{moisture}_n{slots}_union{int(union)}'
        result[name]=dict(source=source,threshold=threshold,moisture=moisture,slots=slots,union=union)
    if len(result)!=plan['fixed_policy_count']:raise ValueError('Fixed policy inventory differs')
    return result


def current_rule(frame):
    temp=frame.road_prediction.to_numpy(float)
    wet=(frame.aws_dewpoint.to_numpy(float)>=temp)|(frame.rain15_max_3h.to_numpy(float)>0)|(frame.asos_snow_cm.to_numpy(float)>0)
    return (np.isfinite(temp)&(temp<=0)&wet).astype(np.int8)


def consecutive(frame,raw,slots):
    if isinstance(slots,bool) or slots not in (1,3):raise ValueError('Declared consecutive-slot policy required')
    values=np.asarray(raw,dtype=bool)
    if values.shape!=(len(frame),):raise ValueError('Aligned conditions required')
    if slots==1:return values.copy()
    result=np.zeros(len(frame),dtype=bool)
    for indices in frame.groupby('station',sort=False).indices.values():
        positions=np.asarray(indices)[np.argsort(frame.iloc[indices].time.to_numpy(),kind='stable')]
        if len(positions)<slots:continue
        count=np.convolve(values[positions].astype(int),np.ones(slots,dtype=int),mode='valid')
        times=frame.iloc[positions].time.to_numpy(dtype='datetime64[ns]')
        contiguous=times[slots-1:]-times[:1-slots]==np.timedelta64(10*(slots-1),'m')
        result[positions[slots-1:]]=(count==slots)&contiguous
    return result


def predict_policy(frame,spec):
    domain(frame)
    a=frame.asos_air_temp.to_numpy(float);road=frame.road_prediction.to_numpy(float)
    if spec['source']=='air':cold=a
    elif spec['source']=='mean_air_road':cold=(a+road)/2
    else:raise ValueError('Unknown cold source')
    if spec['threshold'] not in (-2.,-1.,0.):raise ValueError('Undeclared threshold')
    if spec['moisture']=='none':water=np.ones(len(frame),dtype=bool)
    elif spec['moisture']=='humidity80':water=frame.aws_humidity.to_numpy(float)>=80
    elif spec['moisture']=='dew_or_precip':
        spread=frame.aws_air_temp.to_numpy(float)-frame.aws_dewpoint.to_numpy(float)
        water=(np.isfinite(spread)&(spread<=2))|(frame.rain15_max_3h.to_numpy(float)>0)|(frame.asos_snow_cm.to_numpy(float)>0)
    else:raise ValueError('Unknown moisture policy')
    raw=np.isfinite(cold)&(cold<=spec['threshold'])&water
    p=consecutive(frame,raw,spec['slots'])
    if not isinstance(spec['union'],bool):raise ValueError('Explicit boolean union policy required')
    if spec['union']:p|=current_rule(frame).astype(bool)
    return p.astype(np.int8)


def validate_model_origin(record,groups,outer,target):
    required={outer,target}; forbidden=set().union(*(set(groups[g]) for g in required))
    if set(record['excluded_groups'])!=required or set(record['forbidden_stations'])!=forbidden:
        raise ValueError('Both outer and target groups must be excluded from temperature fitting')
    if forbidden & set(record['training_stations']):raise ValueError('Evaluation station entered fitting')


def event_context(frame,baseline):
    domain(frame)
    if not frame.index.equals(pd.RangeIndex(len(frame))):raise ValueError('Reset index required')
    if not frame[['station','time']].equals(frame[['station','time']].sort_values(['station','time']).reset_index(drop=True)):
        raise ValueError('Sorted event input required')
    positive=frame.ice.eq(1).to_numpy()
    adjacent=frame.station.eq(frame.station.shift()).to_numpy()&frame.time.diff().eq(pd.Timedelta(minutes=10)).to_numpy()
    previous=np.r_[False,positive[:-1]]
    starts=positive&~(previous&adjacent)
    ids=np.cumsum(starts)-1
    event_ids=ids[positive];length=int(starts.sum())
    slots=np.bincount(event_ids,minlength=length)
    detected=np.bincount(event_ids,weights=np.asarray(baseline)[positive],minlength=length)>0
    return dict(positive=positive,ids=event_ids,length=length,slots=slots,baseline_detected=detected,
        identities=frame.loc[starts,['station','time']].reset_index(drop=True))


def event_report(context,prediction):
    p=np.asarray(prediction)
    if p.shape!=context['positive'].shape or not np.isin(p,[0,1]).all():raise ValueError('Complete binary event predictions required')
    detected=np.bincount(context['ids'],weights=p[context['positive']],minlength=context['length'])>0
    old=context['baseline_detected'];lost=old&~detected
    return dict(events=context['length'],baseline_detected=int(old.sum()),detected=int(detected.sum()),
        lost_events=int(lost.sum()),gained_events=int((~old&detected).sum()),
        lost_single_slot_events=int((lost&(context['slots']==1)).sum()))


def eligible(candidate,comparators,track):
    if track not in ('research','strict'):raise ValueError('Unknown research track')
    for minimum in ('144','1'):
        score=candidate['daily'][minimum]['f1_available_station_mean']
        if score is None:return False
        for name in ('current','air_zero','always_one'):
            other=comparators[name]['daily'][minimum]['f1_available_station_mean']
            if other is None or score<=other+1e-12:return False
    current=comparators['current']
    if candidate['event']['lost_events'] or any(candidate['station_tp'][s]<v for s,v in current['station_tp'].items()):return False
    if track=='research':return candidate['fp']<=comparators['air_zero']['fp']
    if candidate['fp']>current['fp'] or candidate['fn']>current['fn']:return False
    for minimum in ('144','1'):
        for metric in ('precision','recall','f1'):
            key=metric+'_available_station_mean';a=candidate['daily'][minimum][key];b=current['daily'][minimum][key]
            if a is None or b is None or a+1e-12<b:return False
    return True


def select_policy(reports,comparators,track,outer,selection_groups):
    if outer in selection_groups or len(set(selection_groups))!=3:raise ValueError('Selection must exclude the outer group')
    accepted=[name for name,r in reports.items() if eligible(r,comparators,track)]
    fallback='air_zero' if track=='research' else 'current'
    chosen=min(accepted,key=lambda n:(-reports[n]['daily']['144']['f1_available_station_mean'],reports[n]['fp'],n)) if accepted else fallback
    return chosen,accepted
