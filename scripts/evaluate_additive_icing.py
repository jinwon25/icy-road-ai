"""기존 개발 23곳에서 온난 구간 추가 탐지의 지역 이중 제외 학습·선택·평가를 실행한다."""
from itertools import combinations
from pathlib import Path
import sys
import warnings
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.anchored_icing import linear_features
from src.additive_icing import candidates,prediction_matrix,metric_table,select_policy
from src.synoptic_icing import sample_weights
from src.offline_runtime import deny_network
from src.data_source import sha256_file as sha
from src.blind_icing import daily_metrics,summarize_days,event_table
from scripts.blind_icing_validation import DEFAULT,verify,read,write,now,old_freezes
from scripts.audit_icing_transition import independent_metrics,independent_events


def main():
    config=ROOT/'config/additive_icing_20261025.json';plan=read(config);out=ROOT/plan['out']
    if out.exists():raise FileExistsError('Preserve completed or partial experiment')
    verify(DEFAULT);f=pd.read_parquet(ROOT/plan['source']).sort_values(['station','time']).reset_index(drop=True)
    assert len(set(f.station))==23 and set(f.station).isdisjoint(plan['blocked_stations'])
    groups=sorted(set(f.group)-{'competition'});assert len(groups)==4
    out.mkdir(parents=True);policies=candidates(plan)
    write(out/'plan.json',dict(at_utc=now(),settings=plan,source_sha256=sha(ROOT/plan['source']),config_sha256=sha(config),
        code_sha256=sha(Path(__file__)),module_sha256=sha(ROOT/'src/additive_icing.py'),policy_count=len(policies),
        old_frozen_counts=list(old_freezes()),new_four_site_training_or_scoring=False))
    tables={};fits=[]
    for excluded in [*(tuple([g]) for g in groups),*combinations(groups,2)]:
        train=f.loc[~f.group.isin(excluded)&f.available&f.ice.isin([0,1])&f.asos_air_temp.gt(0)&f.asos_air_temp.le(4)]
        query=f.loc[f.group.isin(excluded)].copy();assert set(train.station).isdisjoint(query.station)
        assert set(train.ice)=={0.,1.}
        models=dict(warm_logit=make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),StandardScaler(),LogisticRegression(**plan['logistic_parameters'])),
            warm_hgb=HistGradientBoostingClassifier(**plan['hgb_parameters']))
        scores=query[['station','time','group','winter','available','asos_air_temp','ice']].copy()
        for name,model in models.items():
            weights=sample_weights(train,'day');kwargs={'logisticregression__sample_weight':weights} if name=='warm_logit' else {'sample_weight':weights}
            with warnings.catch_warnings(),deny_network() as attempts,threadpool_limits(limits=2):
                warnings.simplefilter('error',ConvergenceWarning)
                model.fit(linear_features(train),train.ice.to_numpy(int),**kwargs)
                score=model.predict_proba(linear_features(query))[:,1]
            assert not attempts
            path=out/('__'.join(excluded)+'__'+name+'.joblib');joblib.dump(model,path,compress=3)
            with deny_network() as attempts,threadpool_limits(limits=2):replay=joblib.load(path).predict_proba(linear_features(query))[:,1]
            assert not attempts;np.testing.assert_array_equal(score,replay);scores[name]=score
            fits.append(dict(excluded=list(excluded),model=name,rows=len(train),positives=int(train.ice.sum()),
                train_stations=sorted(train.station.unique()),query_stations=sorted(query.station.unique()),model_path=path.name,model_sha256=sha(path),
                warm_positive_station_counts=train.loc[train.ice.eq(1)].groupby('station').size().to_dict()))
            print('FIT',','.join(excluded),name,len(train),int(train.ice.sum()),flush=True)
        path=out/('__'.join(excluded)+'__scores.parquet');scores.to_parquet(path,index=False,compression='zstd');tables[tuple(excluded)]=scores
    selections=[];parts=[]
    for held in groups:
        inner=pd.concat([tables[tuple(sorted([held,g]))].loc[lambda z:z.group.eq(g)] for g in groups if g!=held],ignore_index=True)
        assert held not in set(inner.group)
        matrix=prediction_matrix(inner,inner,policies);table=metric_table(inner,matrix,policies)
        table.to_csv(out/(held+'__inner_candidates.csv'),index=False)
        selected={track:select_policy(table,track=='guarded') for track in ['guarded','maximum_f1']}
        selections.append(dict(held=held,selected=selected,inner_groups=sorted(inner.group.unique()),inner_table_sha256=sha(out/(held+'__inner_candidates.csv'))))
        query=tables[(held,)].copy();matrix=prediction_matrix(query,query,policies)
        for j,p in enumerate(policies):query[p['candidate']]=matrix[:,j]
        for track,name in selected.items():query[track]=query[name]
        parts.append(query)
    write(out/'selection.json',dict(at_utc=now(),selections=selections,outer_metrics_computed=False))
    f=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    f.to_parquet(out/'predictions.parquet',index=False,compression='zstd');pop=sorted(f.station.unique());assert len(pop)==9
    matrix=np.column_stack([f[p['candidate']] for p in policies]);table=metric_table(f,matrix,policies)
    table.to_csv(out/'fixed_policy_metrics.csv',index=False)
    reports={};checks=0
    names=[p['candidate'] for p in policies]+['guarded','maximum_f1']
    for name in names:
        r=summarize_days(daily_metrics(f,f[name],pop,plan['winters']),pop)
        other=independent_metrics(f,f[name]);e,events=event_table(f,f[name],f.asos_zero)
        assert e==independent_events(f,f[name],f.asos_zero)
        for k in ['f1_fixed_population','precision_available_station_mean','recall_available_station_mean','tp','fp','fn']:
            np.testing.assert_allclose(r[k],other[k],atol=1e-12,rtol=0);checks+=1
        if name not in ['guarded','maximum_f1']:
            quick=table.loc[table.candidate.eq(name)].iloc[0]
            for fast,full in [('f1','f1_fixed_population'),('precision','precision_available_station_mean'),('recall','recall_available_station_mean')]:
                np.testing.assert_allclose(quick[fast],r[full],atol=1e-12,rtol=0);checks+=1
        assert not (f.asos_zero.eq(1)&f[name].eq(0)).any() and e['lost_events']==0
        report=dict(all=r,events=e,winters={},regions={})
        for year in [2024,2025]:
            part=f.loc[f.winter.eq(year)];report['winters'][str(year)]=summarize_days(daily_metrics(part,part[name],pop,[w for w in plan['winters'] if w[0].startswith(str(year))]),pop)
        for group,g in f.groupby('group'):
            local=sorted(g.station.unique());report['regions'][group]=summarize_days(daily_metrics(g,g[name],local,plan['winters']),local)
        reports[name]=report
        if name in ['guarded','maximum_f1']:events.to_csv(out/(name+'_events.csv'),index=False)
    b=reports['asos_zero'];c=reports['guarded']
    gates=dict(f1=c['all']['f1_fixed_population']>b['all']['f1_fixed_population'] and c['all']['f1_fixed_population']>=1.01*b['all']['f1_fixed_population'],
        winters=all(c['winters'][k]['f1_fixed_population']>=b['winters'][k]['f1_fixed_population'] for k in b['winters']),
        regions=all(c['regions'][k]['f1_fixed_population']>=b['regions'][k]['f1_fixed_population'] for k in b['regions']),
        stations=all(c['all']['station_f1_fixed'][s]>=b['all']['station_f1_fixed'][s] for s in pop),
        precision=c['all']['precision_available_station_mean']>=b['all']['precision_available_station_mean'],
        recall=c['all']['recall_available_station_mean']>=b['all']['recall_available_station_mean'],events=c['events']['lost_events']==0)
    verify(DEFAULT);assert old_freezes()==(47,549)
    write(out/'summary.json',dict(status='nested_additive_development_complete',at_utc=now(),fits=fits,selections=selections,reports=reports,
        primary_procedure='guarded',primary_gates=gates,primary_success=all(gates.values()),metric_checks=checks,event_checks=len(names),
        predictions_sha256=sha(out/'predictions.parquet'),new_independent_assessment=False,new_four_site_outcomes_used=False,production_model_changed=False))
    print('COMPLETE',len(fits),'fits',checks,'checks','success',all(gates.values()),flush=True)


if __name__=='__main__':main()
