"""손실 네 종류를 지역 이중 제외로 학습·선택하고 동일 날짜 지표로 비교한다."""
from datetime import datetime, timezone
from itertools import combinations
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
import torch
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.objective_icing import fit, correction, policies, predictions, choose
from src.additive_icing import metric_table
from src.blind_icing import daily_metrics, summarize_days, event_table
from src.development_resampling import circular_day_indices
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from scripts.blind_icing_validation import DEFAULT, old_freezes
from scripts.audit_icing_transition import independent_metrics, independent_events


def read(p):
    return json.loads(Path(p).read_text(encoding='utf8'))


def write(p,value):
    with Path(p).open('x',encoding='utf8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write('\n')


def now():
    return datetime.now(timezone.utc).isoformat()


def verify_preserved():
    """완료 평가 자산은 원 봉인과 대조하고, 이후 수정한 공지 도구는 보관본으로 확인."""
    seal=read(DEFAULT/'prediction_seal.json')
    for relative,digest in seal['files'].items():
        assert sha(DEFAULT/relative)==digest,relative
    for relative,digest in read(DEFAULT/'input_signatures.json').items():
        assert sha(ROOT/relative)==digest,relative
    archived=[]
    for relative,digest in seal['code_signatures'].items():
        if sha(ROOT/relative)==digest:
            continue
        assert relative=='scripts/review_official_updates.py',relative
        original=ROOT/'outputs/private/submission_candidate_20261026_v7'/relative
        assert sha(original)==digest,relative
        archived.append(dict(path=relative,original_sha256=digest,current_sha256=sha(ROOT/relative)))
    assert old_freezes()==(47,549)
    return dict(seal_sha256=sha(DEFAULT/'prediction_seal.json'),
                preserved_files=len(seal['files']),preserved_inputs=len(read(DEFAULT/'input_signatures.json')),
                archived_code=archived,old_freezes=[47,549])


def report(frame, name, plan):
    pop=sorted(frame.station.unique())
    days=daily_metrics(frame,frame[name],pop,plan['winters'])
    result={'all':summarize_days(days,pop),'winters':{},'regions':{}}
    independent=independent_metrics(frame,frame[name])
    for key in ['f1_fixed_population','precision_available_station_mean','recall_available_station_mean','tp','fp','fn']:
        if result['all'][key] is None:
            assert independent[key] is None
        else:
            np.testing.assert_allclose(result['all'][key],independent[key],atol=1e-12,rtol=0)
    result['events'],events=event_table(frame,frame[name],frame.asos_zero)
    assert result['events']==independent_events(frame,frame[name],frame.asos_zero)
    for year in [2024,2025]:
        q=frame.loc[frame.winter.eq(year)]
        result['winters'][str(year)]=summarize_days(daily_metrics(q,q[name],pop,[w for w in plan['winters'] if w[0].startswith(str(year))]),pop)
    for region,q in frame.groupby('group'):
        population=sorted(q.station.unique())
        result['regions'][region]=summarize_days(daily_metrics(q,q[name],population,plan['winters']),population)
    return result,days,events


def fixed_calendar_f1(candidate, baseline):
    assert candidate[['station','date_kst']].equals(baseline[['station','date_kst']])
    keep=baseline.f1.notna()
    pop=sorted(baseline.station.unique())
    values=candidate.loc[keep,['station','f1']].copy()
    values['f1']=values.f1.fillna(0)
    return float(values.groupby('station').f1.mean().reindex(pop).fillna(0).mean())


def block_sensitivity(candidate, baseline, seed, repetitions=2000):
    ids=np.concatenate([circular_day_indices(120,7,repetitions,seed),
                        120+circular_day_indices(120,7,repetitions,seed+1)],axis=1)
    def sample(days):
        a=days.f1.fillna(0).to_numpy().reshape(-1,240)
        b=days.f1.notna().to_numpy().reshape(-1,240)
        numerator=a[:,ids].sum(axis=2); denominator=b[:,ids].sum(axis=2)
        return np.divide(numerator,denominator,out=np.zeros_like(numerator),where=denominator>0).mean(axis=0)
    delta=sample(candidate)-sample(baseline)
    return dict(repetitions=repetitions,block_days=7,seed=seed,
                difference_percentiles=np.quantile(delta,[.025,.5,.975]).tolist(),
                fraction_positive=float(np.mean(delta>0)),scope='fixed_development_predictions_calendar_sensitivity_not_new_site_confidence')


def main():
    config=ROOT/'config/objective_icing_20261031.json';plan=read(config);out=ROOT/plan['out']
    if out.exists():raise FileExistsError('Preserve previous experiment')
    torch.set_num_threads(2);torch.use_deterministic_algorithms(True)
    torch.manual_seed(plan['seed'])
    before=verify_preserved()
    inputs=[config,Path(__file__),ROOT/'src/objective_icing.py',ROOT/plan['source']]
    out.mkdir(parents=True)
    write(out/'plan.json',dict(at_utc=now(),settings=plan,torch=torch.__version__,
          signatures={p.relative_to(ROOT).as_posix():sha(p) for p in inputs},preservation=before,new_independent_assessment=False))
    f=pd.read_parquet(ROOT/plan['source']).sort_values(['station','time']).reset_index(drop=True)
    assert len(set(f.station))==23 and not set(f.station)&set(plan['blocked_stations'])
    assert not f.duplicated(['station','time']).any()
    groups=sorted(set(f.group)-{'competition'});assert len(groups)==4
    tables={};fits=[];specs=policies(plan)
    for excluded in [*((g,) for g in groups),*combinations(groups,2)]:
        stem='__'.join(excluded)
        train=f.loc[~f.group.isin(excluded)&f.available&f.ice.isin([0,1])].copy()
        query=f.loc[f.group.isin(excluded)].copy()
        assert not set(train.station)&set(query.station)
        scores=query[['station','time','group','winter','ice','available','asos_air_temp']].copy()
        for kind in plan['models']:
            started=time.perf_counter()
            with deny_network() as attempts,threadpool_limits(limits=2):
                model=fit(train,kind,plan)
                values=correction(query,model)
            assert not attempts
            path=out/(stem+'__'+kind+'.npz');np.savez_compressed(path,**model)
            with np.load(path,allow_pickle=False) as archive:
                replay={name:archive[name] for name in archive.files}
            np.testing.assert_array_equal(values,correction(query,replay))
            scores[kind]=values
            record=dict(excluded=list(excluded),kind=kind,model=path.name,sha256=sha(path),
                train_rows=len(train),train_positive_rows=int(train.ice.sum()),train_stations=sorted(train.station.unique()),
                unique_inputs=int(model['unique_training_inputs']),loss_history=model['history'].tolist(),seconds=time.perf_counter()-started)
            fits.append(record)
            write(out/(stem+'__'+kind+'.json'),record)
            print('FIT',len(fits),'/40',stem,kind,round(record['seconds'],2),flush=True)
        scores.to_parquet(out/(stem+'__scores.parquet'),index=False,compression='zstd')
        tables[excluded]=scores
    tracks=['mean_f1','recall_guard',*['loss_'+k for k in plan['models']]]
    decisions=[];parts=[]
    for held in groups:
        inner=pd.concat([tables[tuple(sorted([held,other]))].loc[lambda q:q.group.eq(other)] for other in groups if other!=held],ignore_index=True)
        table=metric_table(inner,predictions(inner,specs,plan['cap_c']),specs)
        table.to_csv(out/(held+'__inner.csv'),index=False)
        selected={track:choose(table,track) for track in tracks}
        decisions.append(dict(held=held,selected=selected))
        q=tables[(held,)].copy();matrix=predictions(q,specs,plan['cap_c'])
        for j,spec in enumerate(specs):q[spec['candidate']]=matrix[:,j]
        for track,candidate in selected.items():q[track]=q[candidate]
        parts.append(q)
    write(out/'selection.json',dict(at_utc=now(),decisions=decisions,outer_metrics_computed=False))
    result=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    result.to_parquet(out/'predictions.parquet',index=False,compression='zstd')
    reports={};daily={}
    for name in [s['candidate'] for s in specs]+tracks:
        reports[name],daily[name],events=report(result,name,plan)
        if name in tracks+['asos_zero']:
            daily[name].to_csv(out/(name+'__daily.csv'),index=False)
            events.to_csv(out/(name+'__events.csv'),index=False)
    for name in reports:
        reports[name]['baseline_calendar_f1']=fixed_calendar_f1(daily[name],daily['asos_zero'])
    sensitivity={name:block_sensitivity(daily[name],daily['asos_zero'],plan['seed']) for name in ['mean_f1','recall_guard']}
    base=reports['asos_zero'];primary=reports['mean_f1']
    gates=dict(f1=primary['all']['f1_fixed_population']>=1.01*base['all']['f1_fixed_population'],
        precision=primary['all']['precision_available_station_mean']>=base['all']['precision_available_station_mean'],
        recall=primary['all']['recall_available_station_mean']>=base['all']['recall_available_station_mean'],
        winters=all(primary['winters'][y]['f1_fixed_population']>=base['winters'][y]['f1_fixed_population'] for y in base['winters']),
        regions=all(primary['regions'][g]['f1_fixed_population']>=base['regions'][g]['f1_fixed_population'] for g in groups),
        stations=all(primary['all']['station_f1_fixed'][s]>=base['all']['station_f1_fixed'][s] for s in base['all']['station_f1_fixed']),
        events=primary['events']['lost_events']==0,
        fixed_calendar=primary['baseline_calendar_f1']>=base['baseline_calendar_f1'])
    assert verify_preserved()==before
    write(out/'summary.json',dict(status='objective_icing_development_complete',at_utc=now(),fits=fits,
        decisions=decisions,reports=reports,primary_gates=gates,primary_success=all(gates.values()),
        sensitivity=sensitivity,predictions_sha256=sha(out/'predictions.parquet'),production_model_changed=False,
        new_four_site_outcomes_used=False,protected_outcomes_used=False))
    print('COMPLETE',len(fits),'fits',len(reports),'comparisons',gates,flush=True)


if __name__=='__main__':main()
