"""최신 공식 지표로 기존 후보와 일별 분모를 반영한 새 손실을 중첩 지역 제외 비교한다."""
from itertools import combinations
from pathlib import Path
from datetime import datetime,timezone
import json,sys,time
import numpy as np
import pandas as pd
import torch
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.official_metrics_20261106 import evaluate,WINTERS
from src.official_icing_upgrade import fit,correction
from src.objective_icing import policies,predictions
from src.blind_icing import event_table
from src.development_resampling import circular_day_indices
from scripts.evaluate_objective_icing import verify_preserved
from scripts.package_submission_channels import read,write,sha

def report(frame,values,minimum=1):
    s,stations,days=evaluate(frame,values,minimum_valid_slots=minimum)
    return s,stations,days

def rank(frame,matrix,specs,minimum=1):
    rows=[]
    for j,spec in enumerate(specs):
        s,_,_=report(frame,matrix[:,j],minimum)
        rows.append(dict(**spec,**{k:s[k] for k in ['f1','precision','recall','f1_stations','f1_days']}))
    return pd.DataFrame(rows).sort_values(['f1','complexity','candidate'],ascending=[False,True,True],kind='stable',na_position='last')

def block(candidate,baseline,seed):
    stations=sorted(candidate.loc[candidate.station_eligible,'station'].unique())
    ids=np.concatenate([circular_day_indices(120,7,2000,seed),120+circular_day_indices(120,7,2000,seed+1)],axis=1)
    def sample(days):
        q=days.loc[days.station.isin(stations)].sort_values(['station','date_kst'])
        values=q.f1.fillna(0).to_numpy().reshape(len(stations),240)
        present=q.f1.notna().to_numpy().reshape(len(stations),240)
        den=present[:,ids].sum(axis=2);num=values[:,ids].sum(axis=2)
        station=np.divide(num,den,out=np.full_like(num,np.nan,dtype=float),where=den>0)
        return np.nanmean(station,axis=0)
    delta=sample(candidate)-sample(baseline)
    return dict(seed=seed,repetitions=2000,block_days=7,difference_percentiles=np.nanquantile(delta,[.025,.5,.975]).tolist(),
        fraction_positive=float(np.mean(delta>0)),scope='same_development_calendar_sensitivity_fixed_eligible_stations_not_new_site_confidence')

def independent(frame,values,minimum):
    from collections import defaultdict
    census=defaultdict(int);counts=defaultdict(lambda:[0,0,0,0])
    for (station,stamp,y),p in zip(frame[['station','time','ice']].itertuples(index=False,name=None),values):
        if y==1:census[str(station)]+=1
        if y not in (0,1) or p not in (0,1):continue
        c=counts[(str(station),pd.Timestamp(stamp).date())];c[0]+=1
        if y==1 and p==1:c[1]+=1
        elif y==0 and p==1:c[2]+=1
        elif y==1 and p==0:c[3]+=1
    by={m:defaultdict(list) for m in ['precision','recall','f1']}
    for (station,date),(n,tp,fp,fn) in counts.items():
        if n<minimum or not census[station]:continue
        for name,num,den in [('precision',tp,tp+fp),('recall',tp,tp+fn),('f1',2*tp,2*tp+fp+fn)]:
            if den:by[name][station].append(num/den)
    result={}
    for name,mapping in by.items():
        v=[sum(a)/len(a) for a in mapping.values()]
        result[name]=sum(v)/len(v) if v else None
        result[name+'_stations']=len(v);result[name+'_days']=sum(map(len,mapping.values()))
    return result

def main():
    cfg=ROOT/'config/official_icing_upgrade_20261106.json';plan=read(cfg);out=ROOT/plan['output'];old=ROOT/plan['cached_models']
    if out.exists():raise FileExistsError('Preserve completed or partial experiment; do not change plan after results')
    torch.set_num_threads(2);torch.use_deterministic_algorithms(True);torch.manual_seed(plan['seed'])
    audit=read(old/'independent_verification.json');assert audit['status']=='passed' and audit['summary_sha256']==sha(old/'summary.json')
    assert audit['predictions_sha256']==sha(old/'predictions.parquet')
    preserved=verify_preserved()
    f=pd.read_parquet(ROOT/plan['source']).sort_values(['station','time']).reset_index(drop=True)
    assert len(set(f.station))==23 and not set(f.station)&set(plan['blocked_stations'])
    reference_path=ROOT/'outputs/private/two_winter_models_20261024_v1/runtime_predictions.parquet'
    reference=pd.read_parquet(reference_path,columns=['station','time','ice','physical_both'])
    compare=f.loc[f.group.ne('competition'),['station','time','ice']].merge(reference,on=['station','time'],validate='one_to_one',suffixes=['','_reference'])
    np.testing.assert_array_equal(compare.ice,compare.ice_reference)
    source_files=[cfg,Path(__file__),ROOT/'src/official_metrics_20261106.py',ROOT/'src/official_icing_upgrade.py',ROOT/plan['source'],reference_path]
    source_files+=list(old.glob('*__scores.parquet'))
    out.mkdir()
    write(out/'plan.json',dict(settings=plan,started_at_utc=datetime.now(timezone.utc).isoformat(),preservation=preserved,
        signatures={p.relative_to(ROOT).as_posix():sha(p) for p in source_files},available_development_stations=sorted(reference.station.unique())))
    groups=sorted(set(f.group)-{'competition'});assert len(groups)==4
    oldplan=read(old/'plan.json')['settings'];specs=policies(oldplan)
    specs += [dict(candidate=f'official_day_ratio_offset{v:g}',model='official_day_ratio',offset=v,complexity=2+abs(v)) for v in [-.5,0.,.5]]
    tables={};fits=[]
    for excluded in [*((g,) for g in groups),*combinations(groups,2)]:
        stem='__'.join(excluded);q=pd.read_parquet(old/(stem+'__scores.parquet'))
        query=f.loc[f.group.isin(excluded)].copy()
        pd.testing.assert_frame_equal(q[['station','time']].reset_index(drop=True),query[['station','time']].reset_index(drop=True))
        train=f.loc[~f.group.isin(excluded)&f.available&f.ice.isin([0,1])].copy()
        assert not set(train.station)&set(query.station)
        started=time.perf_counter()
        with threadpool_limits(limits=2):model=fit(train,plan);q['official_day_ratio']=correction(query,model)
        path=out/(stem+'.npz');np.savez_compressed(path,**model)
        with np.load(path,allow_pickle=False) as z:np.testing.assert_array_equal(q.official_day_ratio,correction(query,{k:z[k] for k in z.files}))
        q=q.merge(reference[['station','time','physical_both']],on=['station','time'],validate='one_to_one')
        q['available']=q.available&np.isfinite(q.physical_both)
        q.to_parquet(out/(stem+'__scores.parquet'),index=False,compression='zstd');tables[excluded]=q
        record=dict(excluded=list(excluded),model_file=path.name,model_sha256=sha(path),training_rows=len(train),training_stations=sorted(train.station.unique()),
            seconds=time.perf_counter()-started,loss=model['history'].tolist())
        fits.append(record);write(out/(stem+'_fit.json'),record)
        print('FIT',len(fits),'/10',stem,round(record['seconds'],2),flush=True)
    decisions=[];parts=[]
    for held in groups:
        inner=pd.concat([tables[tuple(sorted([held,other]))].loc[lambda q:q.group.eq(other)] for other in groups if other!=held],ignore_index=True)
        matrix=predictions(inner,specs,cap=2.);table=rank(inner,matrix,specs);table.to_csv(out/(held+'__inner.csv'),index=False)
        tracks={'official_nested':table,'cached_only':table.loc[table.model.ne('official_day_ratio')],
                'new_only':table.loc[table.model.eq('official_day_ratio')|table.model.isna()]}
        choices={name:str(t.iloc[0].candidate) for name,t in tracks.items()}
        decisions.append(dict(held=held,choices=choices))
        q=tables[(held,)].copy();matrix=predictions(q,specs,cap=2.)
        for j,spec in enumerate(specs):q[spec['candidate']]=matrix[:,j]
        for name,candidate in choices.items():q[name]=q[candidate]
        parts.append(q)
    write(out/'selection_seal.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),decisions=decisions,outer_scores_read=False))
    result=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    result.to_parquet(out/'predictions.parquet',index=False,compression='zstd')
    reports={};days={};station_tables=[];checks=0
    for name in ['physical_both','asos_zero','official_nested','cached_only','new_only']:
        reports[name]={}
        for minimum in [1,144]:
            s,stations,daily=report(result,result[name].to_numpy(float),minimum)
            proof=independent(result,result[name].to_numpy(float),minimum)
            for key,value in proof.items():
                if value is None:assert s[key] is None
                else:np.testing.assert_allclose(s[key],value,atol=1e-12,rtol=0)
                checks+=1
            reports[name][str(minimum)]=s
            daily.to_csv(out/(name+f'_daily_min{minimum}.csv'),index=False,encoding='utf-8-sig')
            station_tables.append(stations.assign(candidate=name,minimum_valid_slots=minimum))
            days[(name,minimum)]=daily
        reports[name]['winters']={}
        for year in [2024,2025]:
            q=result.loc[result.winter.eq(year)]
            reports[name]['winters'][str(year)]=evaluate(q,q[name],minimum_valid_slots=1,winters=[w for w in WINTERS if w[0].startswith(str(year))])[0]
        reports[name]['regions']={}
        for group,q in result.groupby('group'):reports[name]['regions'][group]=report(q,q[name].to_numpy(float))[0]
        reports[name]['events'],events=event_table(result,result[name],result.asos_zero)
        events.to_csv(out/(name+'_events.csv'),index=False)
    pd.concat(station_tables,ignore_index=True).to_csv(out/'station_metrics.csv',index=False,encoding='utf-8-sig')
    sensitivity={name:block(days[(name,1)],days[('asos_zero',1)],plan['seed']) for name in ['official_nested','cached_only','new_only']}
    base=reports['asos_zero'];candidate=reports['official_nested'];gate=plan['promotion_gate']
    gates=dict(f1=candidate['1']['f1']>=base['1']['f1']*(1+gate['minimum_relative_f1_gain']),
        strict144=candidate['144']['f1']>=base['144']['f1'],recall=candidate['1']['recall']>=base['1']['recall']*gate['minimum_relative_recall'],
        regions=all(candidate['regions'][g]['f1'] is not None and candidate['regions'][g]['f1']>=base['regions'][g]['f1']*(1-gate['region_worsening_limit'])
                    for g in groups if base['regions'][g]['f1'] is not None))
    assert verify_preserved()==preserved
    write(out/'summary.json',dict(status='official_icing_upgrade_evaluated',at_utc=datetime.now(timezone.utc).isoformat(),fits=fits,
        reports=reports,sensitivity=sensitivity,promotion_gates=gates,promote=all(gates.values()),metric_independent_checks=checks,
        predictions_sha256=sha(out/'predictions.parquet'),selection_sha256=sha(out/'selection_seal.json'),
        protected_outcomes_read=False,new_four_site_outcomes_read=False,new_independent_assessment=False))
    print(json.dumps(dict(status='complete',gates=gates,promote=all(gates.values()),
        metrics={n:{m:reports[n]['1'][m] for m in ['f1','precision','recall','f1_stations','f1_days']} for n in reports}),ensure_ascii=False),flush=True)

if __name__=='__main__':main()