"""기존 개발 지역에서 기온 시작값을 이용한 잔차 보정의 학습·내부 선택·외부 비교."""
from itertools import combinations
from pathlib import Path
import sys
import time
import numpy as np
import pandas as pd
import xgboost as xgb
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.residual_icing import prior_margin,policies,predictions,select
from src.anchored_icing import linear_features
from src.synoptic_icing import sample_weights
from src.additive_icing import metric_table
from src.blind_icing import daily_metrics,summarize_days,event_table
from src.offline_runtime import deny_network
from src.data_source import sha256_file as sha
from scripts.blind_icing_validation import DEFAULT,verify,read,write,now,old_freezes
from scripts.audit_icing_transition import independent_metrics,independent_events


def main():
    cfg=ROOT/'config/residual_icing_20261025.json';plan=read(cfg);out=ROOT/plan['out']
    if out.exists():raise FileExistsError('Preserve completed or partial experiment')
    verify(DEFAULT);f=pd.read_parquet(ROOT/plan['source']).sort_values(['station','time']).reset_index(drop=True)
    assert len(set(f.station))==23 and set(f.station).isdisjoint(plan['blocked_stations'])
    assert xgb.__version__=='3.0.1'
    groups=sorted(set(f.group)-{'competition'});assert len(groups)==4
    out.mkdir(parents=True);specs=policies(plan)
    write(out/'plan.json',dict(at_utc=now(),settings=plan,signatures={p.relative_to(ROOT).as_posix():sha(p) for p in [cfg,Path(__file__),ROOT/'src/residual_icing.py',ROOT/'src/additive_icing.py',ROOT/plan['source']]},policy_count=len(specs),xgboost=xgb.__version__,new_independent_assessment=False))
    tables={};fits=[]
    for excluded in [*(tuple([g]) for g in groups),*combinations(groups,2)]:
        train=f.loc[~f.group.isin(excluded)&f.available&f.ice.isin([0,1])];query=f.loc[f.group.isin(excluded)].copy()
        assert set(train.station).isdisjoint(query.station)
        scores=query[['station','time','group','winter','available','asos_air_temp','ice']].copy()
        x=linear_features(train);qx=linear_features(query)
        for spec in plan['models']:
            start=time.perf_counter();base=prior_margin(train.asos_air_temp,spec['prior']);qb=prior_margin(query.asos_air_temp,spec['prior'])
            weights=sample_weights(train,spec['weights']);dtrain=xgb.DMatrix(x,label=train.ice,weight=weights,base_margin=base,nthread=2);dq=xgb.DMatrix(qx,base_margin=qb,nthread=2)
            with deny_network() as attempts,threadpool_limits(limits=2):model=xgb.train(plan['parameters'],dtrain,num_boost_round=max(plan['rounds']))
            assert not attempts
            path=out/('__'.join(excluded)+'__'+spec['name']+'.ubj');model.save_model(path)
            replay=xgb.Booster();replay.load_model(path);replay.set_param({'nthread':2,'device':'cpu'})
            for rounds in plan['rounds']:
                with deny_network() as attempts,threadpool_limits(limits=2):
                    margin=model.predict(dq,output_margin=True,iteration_range=(0,rounds));again=replay.predict(dq,output_margin=True,iteration_range=(0,rounds))
                assert not attempts;np.testing.assert_array_equal(margin,again);scores[spec['name']+'_r'+str(rounds)]=margin
            fits.append(dict(excluded=list(excluded),model=spec['name'],prior=spec['prior'],weights=spec['weights'],rows=len(train),positive_rows=int(train.ice.sum()),
                stations=sorted(train.station.unique()),model_path=path.name,model_sha256=sha(path),seconds=time.perf_counter()-start))
            print('FIT',len(fits),','.join(excluded),spec['name'],round(fits[-1]['seconds'],1),flush=True)
            write(out/'progress.json',dict(planned=30,completed=len(fits),fits=fits))
        scores.to_parquet(out/('__'.join(excluded)+'__scores.parquet'),index=False,compression='zstd');tables[tuple(excluded)]=scores
    selections=[];parts=[]
    for held in groups:
        inner=pd.concat([tables[tuple(sorted([held,g]))].loc[lambda q:q.group.eq(g)] for g in groups if g!=held],ignore_index=True)
        table=metric_table(inner,predictions(inner,specs,plan['models']),specs);path=out/(held+'__inner.csv');table.to_csv(path,index=False)
        selected={track:select(table,track=='guarded') for track in ['guarded','maximum_f1']}
        selections.append(dict(held=held,selected=selected,inner_sha256=sha(path)))
        q=tables[(held,)].copy();matrix=predictions(q,specs,plan['models'])
        for j,spec in enumerate(specs):q[spec['candidate']]=matrix[:,j]
        for track,name in selected.items():q[track]=q[name]
        parts.append(q)
    write(out/'selection.json',dict(at_utc=now(),selections=selections,outer_metrics_computed=False))
    result=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    path=out/'predictions.parquet';result.to_parquet(path,index=False,compression='zstd')
    reports={};checks=0;population=sorted(result.station.unique());assert len(population)==9
    for name in [p['candidate'] for p in specs]+['guarded','maximum_f1']:
        r=summarize_days(daily_metrics(result,result[name],population,plan['winters']),population);other=independent_metrics(result,result[name])
        for k in ['f1_fixed_population','precision_available_station_mean','recall_available_station_mean','tp','fp','fn']:
            np.testing.assert_allclose(r[k],other[k],atol=1e-12,rtol=0);checks+=1
        e,events=event_table(result,result[name],result.asos_zero);assert e==independent_events(result,result[name],result.asos_zero)
        report=dict(all=r,events=e,winters={},regions={})
        for year in [2024,2025]:
            q=result.loc[result.winter.eq(year)];report['winters'][str(year)]=summarize_days(daily_metrics(q,q[name],population,[w for w in plan['winters'] if w[0].startswith(str(year))]),population)
        for group,q in result.groupby('group'):
            pop=sorted(q.station.unique());report['regions'][group]=summarize_days(daily_metrics(q,q[name],pop,plan['winters']),pop)
        reports[name]=report
        if name in ['guarded','maximum_f1']:events.to_csv(out/(name+'_events.csv'),index=False)
    b=reports['asos_zero'];c=reports['guarded']
    gates=dict(f1=c['all']['f1_fixed_population']>b['all']['f1_fixed_population'] and c['all']['f1_fixed_population']>=1.01*b['all']['f1_fixed_population'],
        precision=c['all']['precision_available_station_mean']>=b['all']['precision_available_station_mean'],recall=c['all']['recall_available_station_mean']>=b['all']['recall_available_station_mean'],
        winters=all(c['winters'][k]['f1_fixed_population']>=b['winters'][k]['f1_fixed_population'] for k in b['winters']),
        regions=all(c['regions'][k]['f1_fixed_population']>=b['regions'][k]['f1_fixed_population'] for k in b['regions']),
        stations=all(c['all']['station_f1_fixed'][s]>=b['all']['station_f1_fixed'][s] for s in population),events=c['events']['lost_events']==0)
    verify(DEFAULT);assert old_freezes()==(47,549)
    write(out/'summary.json',dict(status='residual_development_complete',at_utc=now(),fits=fits,selections=selections,reports=reports,primary_gates=gates,
        primary_success=all(gates.values()),metric_checks=checks,event_checks=len(reports),predictions_sha256=sha(path),new_four_site_outcomes_used=False,production_model_changed=False))
    print('COMPLETE',len(fits),'fits',len(specs),'policies',gates,flush=True)


if __name__=='__main__':main()
