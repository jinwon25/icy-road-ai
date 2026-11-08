"""목적함수 실험의 전처리·추론·지역 분리·선택·최종 지표를 별도 계산으로 검산한다."""
from collections import Counter, defaultdict
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import torch
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read, write, verify_preserved
from scripts.audit_icing_transition import independent_metrics, independent_events
from src.data_source import sha256_file as sha
from src.objective_icing import fit, group_data
from src.offline_runtime import deny_network


def independent_features(frame):
    names=['asos_air_temp','asos_ground_temp','asos_humidity','asos_rain_mm','asos_snow_cm',
           'asos_cloud_tenths','asos_solar_mj_m2','asos_wind_speed','asos_dewpoint_obs',
           'asos_pressure','asos_visibility','asos_new_snow3h','asos_soil5cm']
    x=frame[names].copy()
    x['dewpoint_depression']=frame.asos_air_temp-frame.asos_dewpoint_obs
    x['ground_dewpoint_gap']=frame.asos_ground_temp-frame.asos_dewpoint_obs
    for name,knots in [('asos_air_temp',[-5.,0.,5.]),('asos_ground_temp',[-5.,0.,5.]),
                       ('asos_humidity',[80.,95.]),('dewpoint_depression',[0.,3.])]:
        for knot in knots:x[name+'_above_'+str(knot)]=np.maximum(x[name]-knot,0)
    return x


def independent_weights(frame):
    strata=list(zip(frame.station,frame.winter,frame.time.dt.normalize(),frame.ice))
    count=Counter(strata);classes=defaultdict(set);days=defaultdict(set)
    for station,winter,day,target in count:
        classes[station,winter,day].add(target);days[station,winter].add(day)
    w=np.array([1/(count[k]*len(classes[k[:3]])*len(days[k[:2]])) for k in strata])
    return w/w.mean()


def choose_independent(table,track):
    records=table.to_dict('records');base=next(r for r in records if r['candidate']=='asos_zero')
    if track=='recall_guard':
        records=[r for r in records if r['recall']>=.9*base['recall']
                 and all(r['f1_'+y]>=base['f1_'+y] for y in ['2024','2025'])]
    elif track.startswith('loss_'):
        records=[r for r in records if r['candidate']=='asos_zero' or r['model']==track[5:]]
    if not records:return base['candidate']
    return sorted(records,key=lambda r:(-r['f1'],r['complexity'],r['candidate']))[0]['candidate']


def same(a,b):
    if b is None:assert a is None
    else:np.testing.assert_allclose(a,b,rtol=0,atol=1e-12)


def main():
    study=ROOT/'outputs/private/objective_icing_20261031_v2'
    target=study/'independent_verification.json'
    if target.exists():raise FileExistsError('Preserve first audit')
    plan=read(study/'plan.json');settings=plan['settings'];summary=read(study/'summary.json')
    for name,digest in plan['signatures'].items():assert sha(ROOT/name)==digest,name
    assert verify_preserved()==plan['preservation']
    torch.set_num_threads(2);torch.use_deterministic_algorithms(True)
    source=pd.read_parquet(ROOT/settings['source']).sort_values(['station','time']).reset_index(drop=True)
    assert not set(source.station)&set(settings['blocked_stations'])
    result=pd.read_parquet(study/'predictions.parquet');assert sha(study/'predictions.parquet')==summary['predictions_sha256']
    model_values=0;max_error=0.;refits=0;cache={};current_key=None;groups=sorted(set(source.group)-{'competition'})
    for receipt in summary['fits']:
        key=tuple(receipt['excluded']);stem='__'.join(key)
        if key!=current_key:
            train=source.loc[~source.group.isin(key)&source.available&source.ice.isin([0,1])]
            query=source.loc[source.group.isin(key)]
            x=independent_features(train);q=independent_features(query)
            median=x.median().fillna(0).to_numpy();filled=x.fillna(dict(zip(x,median))).to_numpy()
            mean=filled.mean(axis=0);scale=filled.std(axis=0);scale[scale<1e-8]=1
            weights=independent_weights(train)
            np.testing.assert_allclose(weights,group_data(train)['row_weights'],rtol=0,atol=1e-12)
            cache[key]=pd.read_parquet(study/(stem+'__scores.parquet'))
            current_key=key
        scores=cache[key]
        assert len(train)==receipt['train_rows'] and int(train.ice.sum())==receipt['train_positive_rows']
        assert sorted(train.station.unique())==receipt['train_stations']
        assert not set(train.station)&set(query.station)
        pd.testing.assert_frame_equal(query[['station','time']].reset_index(drop=True),scores[['station','time']].reset_index(drop=True))
        path=study/receipt['model'];assert sha(path)==receipt['sha256']
        with np.load(path,allow_pickle=False) as archive:model=dict(archive)
        assert list(q)==list(model['feature_names'])
        for name,value in [('medians',median),('means',mean),('scales',scale)]:
            np.testing.assert_allclose(model[name],value,rtol=0,atol=1e-12)
        a=q.to_numpy();missing=np.isnan(a)
        z=np.concatenate([np.clip((np.where(missing,median,a)-mean)/scale,-8,8),missing.astype(float)],axis=1).astype(np.float32)
        # NumPy 배정밀도 내적·tanh로 PyTorch 단정밀도 추론을 독립 대조한다.
        predicted=float(model['cap'])*np.tanh(z.astype(float)@model['coefficient'].astype(float)+float(model['intercept']))
        actual=scores[receipt['kind']].to_numpy()
        error=float(np.max(np.abs(predicted-actual)));max_error=max(max_error,error)
        np.testing.assert_allclose(predicted,actual,rtol=0,atol=5e-6)
        for offset in settings['offsets_c']:
            valid=query.available.to_numpy()
            np.testing.assert_array_equal(query.asos_air_temp.to_numpy()[valid]<=np.clip(predicted+offset,-2,2)[valid],
                                          query.asos_air_temp.to_numpy()[valid]<=np.clip(actual+offset,-2,2)[valid])
        model_values+=len(query)
        if key==(groups[0],):
            with deny_network() as attempts,threadpool_limits(limits=2):repeat=fit(train,receipt['kind'],settings)
            assert not attempts
            for name in model:np.testing.assert_array_equal(repeat[name],model[name])
            refits+=1
        print('AUDIT MODEL',receipt['kind'],stem,flush=True)
    metric_checks=0;selection_checks=0
    for decision in summary['decisions']:
        held=decision['held'];table=pd.read_csv(study/(held+'__inner.csv'))
        inner=pd.concat([cache[tuple(sorted([held,g]))].loc[lambda q:q.group.eq(g)] for g in groups if g!=held],ignore_index=True)
        assert not set(inner.station)&set(result.loc[result.group.eq(held),'station'])
        for r in table.to_dict('records'):
            delta=r['offset'] if pd.isna(r['model']) else np.clip(inner[r['model']]+r['offset'],-2,2)
            p=np.where(inner.available,inner.asos_air_temp.le(delta),np.nan)
            actual=independent_metrics(inner,p)
            for key,original in [('f1_fixed_population','f1'),('precision_available_station_mean','precision'),
                                 ('recall_available_station_mean','recall'),('tp','tp'),('fp','fp'),('fn','fn')]:same(actual[key],r[original])
            for year in [2024,2025]:
                mask=inner.winter.eq(year);same(independent_metrics(inner.loc[mask],p[mask])['f1_fixed_population'],r['f1_'+str(year)])
            metric_checks+=8
        for track,choice in decision['selected'].items():
            assert choose_independent(table,track)==choice
            q=result.loc[result.group.eq(held)];np.testing.assert_array_equal(q[track],q[choice])
            selection_checks+=1
    for name,record in summary['reports'].items():
        for label,q in [('all',result),*[(str(y),result.loc[result.winter.eq(y)]) for y in [2024,2025]],
                        *[(g,result.loc[result.group.eq(g)]) for g in groups]]:
            expected=record['all'] if label=='all' else record['winters'][label] if label.isdigit() else record['regions'][label]
            for k,value in independent_metrics(q,q[name]).items():same(value,expected[k]);metric_checks+=1
        assert independent_events(result,result[name],result.asos_zero)==record['events']
    base_days=pd.read_csv(study/'asos_zero__daily.csv')
    for name in ['mean_f1','recall_guard']:
        days=pd.read_csv(study/(name+'__daily.csv'))
        assert days[['station','date_kst']].equals(base_days[['station','date_kst']])
        site_values=[]
        for station in sorted(base_days.station.unique()):
            mask=base_days.station.eq(station)&base_days.f1.notna()
            site_values.append(float(days.loc[mask,'f1'].fillna(0).mean()) if mask.any() else 0.)
        same(float(np.mean(site_values)),summary['reports'][name]['baseline_calendar_f1'])
        # 일별 블록을 Python 반복으로 만들고 날짜별 선택 결과를 직접 집계한다.
        samples=[];generators=[np.random.default_rng(settings['seed']+i) for i in [0,1]]
        starts=[r.integers(0,120,size=(2000,18)) for r in generators]
        a=days.f1.to_numpy().reshape(-1,240);b=base_days.f1.to_numpy().reshape(-1,240)
        for i in range(2000):
            indices=[]
            for season in [0,1]:
                idx=[int((start+j)%120+120*season) for start in starts[season][i] for j in range(7)][:120]
                indices.extend(idx)
            means=[]
            for values in [a,b]:
                selected=values[:,indices];counts=np.isfinite(selected).sum(axis=1)
                means.append(np.divide(np.nansum(selected,axis=1),counts,out=np.zeros(len(selected)),where=counts>0).mean())
            samples.append(means[0]-means[1])
        expected=summary['sensitivity'][name]
        np.testing.assert_allclose(np.quantile(samples,[.025,.5,.975]),expected['difference_percentiles'],rtol=0,atol=1e-12)
        same(float(np.mean(np.array(samples)>0)),expected['fraction_positive'])
    assert verify_preserved()==plan['preservation']
    write(target,dict(status='passed',model_files=len(summary['fits']),model_values=model_values,
        maximum_numpy_torch_difference=max_error,classification_offset_comparisons=3*model_values,
        deterministic_refits=refits,metric_checks=metric_checks,nested_choices=selection_checks,
        event_checks=len(summary['reports']),fixed_calendar_checks=2,block_resampling_checks=4000,
        summary_sha256=sha(study/'summary.json'),
        predictions_sha256=sha(study/'predictions.parquet'),audit_script_sha256=sha(Path(__file__)),
        preservation=plan['preservation'],protected_outcomes_read=False,new_four_site_outcomes_read=False))
    print('AUDIT COMPLETE',metric_checks,'metrics',selection_checks,'choices',flush=True)


if __name__=='__main__':main()
