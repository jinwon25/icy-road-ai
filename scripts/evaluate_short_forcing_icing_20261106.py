"""짧은 감쇠 누적 후보 20적합을 지역 이중 제외·공식 지표로 검증한다."""
from pathlib import Path
from itertools import combinations
from concurrent.futures import ProcessPoolExecutor,as_completed
from datetime import datetime,timezone
import sys,json,time,os
import numpy as np,pandas as pd,joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.short_forcing_icing_20261106 import features,TAUS
from src.icing_precision_20261106 import weights,exact_threshold,binary_prediction
from src.official_metrics_20261106 import evaluate
from src.offline_runtime import deny_network
from src.data_source import sha256_file as sha
from scripts.evaluate_icing_snow_age_20261106 import reports_for
from scripts.evaluate_official_icing_upgrade_20261106 import block
from scripts.evaluate_objective_icing import verify_preserved
P=ROOT/'outputs/private';W=P/'short_forcing_icing_20261106';DATA=P/'blind_icing_20261025_v2/training.parquet'
SNOW=P/'icing_snow_age_20261106_checked';NAMES=['short_station','short_day']
PARAMS=dict(learning_rate=.05,max_iter=220,max_leaf_nodes=7,min_samples_leaf=300,l2_regularization=30,early_stopping=False,random_state=20261106,interaction_cst='pairwise')
def read(p):return json.loads(p.read_text('utf8'))
def put(p,v):
    with p.open('x',encoding='utf8') as out:json.dump(v,out,ensure_ascii=False,indent=2,allow_nan=False);out.write('\n')

def fit_job(excluded,name):
    stem='__'.join(excluded)+'__'+name;rp=W/(stem+'.json');sp=W/(stem+'.parquet');mp=W/(stem+'.joblib')
    if rp.exists():
        r=read(rp);assert sha(sp)==r['scores_sha256'] and sha(mp)==r['model_sha256'];return r
    f=pd.read_parquet(DATA,columns=['station','time','winter','group','ice','available']);x=pd.read_parquet(W/'features.parquet')
    train=~f.group.isin(excluded)&f.available&f.ice.isin([0,1]);query=f.group.isin(excluded)
    assert not set(f.loc[train,'station'])&set(f.loc[query,'station'])
    assert len(x)==len(f)
    model=HistGradientBoostingClassifier(**PARAMS);started=time.perf_counter()
    with threadpool_limits(limits=2),deny_network() as attempts:
        model.fit(x.loc[train],f.loc[train,'ice'].astype(int),sample_weight=weights(f.loc[train],name.removeprefix('short_')))
        score=model.predict_proba(x.loc[query])[:,1]
    assert not attempts and np.isfinite(score).all()
    joblib.dump(model,mp,compress=3)
    q=f.loc[query,['station','time']].copy();q['score']=score;q.to_parquet(sp,index=False,compression='zstd')
    r=dict(excluded=list(excluded),name=name,training_rows=int(train.sum()),training_stations=sorted(f.loc[train,'station'].unique()),positive_rows=int(f.loc[train,'ice'].sum()),
        feature_count=len(x.columns),seconds=time.perf_counter()-started,model_sha256=sha(mp),scores_sha256=sha(sp))
    put(rp,r);return r

def threshold_job(held,name,path,recall_floor,f1_floor):
    f=pd.read_parquet(path)
    found=exact_threshold(f,f[name].to_numpy(float),recall_floor=recall_floor,precision_f1_floor=f1_floor)
    for r in found.values():
        if r is None:continue
        proof=evaluate(f,binary_prediction(f,f[name],r['threshold']),minimum_valid_slots=1)[0]
        for k in ['precision','recall','f1']:np.testing.assert_allclose(proof[k],r[k],rtol=0,atol=1e-12)
    return held,name,found

def causal_checks(f,x):
    # Change present/future inputs in a contiguous sample: all accumulated features at t must stay fixed.
    sample=f.loc[f.station.eq(f.station.iloc[0])].iloc[:200].copy().reset_index(drop=True)
    a=features(sample);changed=sample.copy();changed.loc[100:,['asos_air_temp','asos_ground_temp','asos_dewpoint_obs']]=80.
    b=features(changed);history=[c for c in a if '_past_tau' in c or '_prior_change_' in c]
    np.testing.assert_array_equal(a.loc[:100,history].to_numpy(),b.loc[:100,history].to_numpy())
    for tau in TAUS:
        assert any(f'tau{tau}m' in c for c in x)
    return dict(strict_past_perturbation_passed=True,station_time_sort_verified=True)

def main():
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in [DATA,Path(__file__),ROOT/'src/short_forcing_icing_20261106.py']}
    if W.exists():
        assert read(W/'plan.json')['source_sha256']==signatures and not (W/'summary.json').exists()
    else:
        W.mkdir();put(W/'plan.json',dict(status='preregistered_before_new_fits',reference='https://arxiv.org/abs/2609.33528',
            scope='ASOS air/ground temperature proxies, not observed road temperature or a replication of the paper. Current 10-min Ice classification, not future onset forecasting.',
            decay_minutes=list(TAUS),dose='strictly past exact zero-order-hold decay integral; three-tau warmup; gaps reset; cold/thaw/deposition proxy/crossings',
            weights=NAMES,parameters=PARAMS,planned_new_fits=20,outer_regions=4,inner_pair_exclusions=6,
            selection='primary: inner official daily F1 maximum without recall floor among two classifiers, physical and air-zero. Secondary precision track requires 95% of physical recall and at least both baseline F1.',
            promotion='Precision +10%, F1 +5% over both baselines, recall >=95% physical, lost events <=5%, full-day and each-winter F1 not worse, no regional >10% F1 decline, 7-day block lower F1 difference >0.',
            protected_outcomes_used=False,external_four_outcomes_used=False,new_independent_assessment=False,production_model_changed=False,source_sha256=signatures))
    preserved=verify_preserved()
    f=pd.read_parquet(DATA);assert f[['station','time']].equals(f.sort_values(['station','time'])[['station','time']].reset_index(drop=True))
    assert len(set(f.station))==23 and not set(f.station)&{'12410','33411','23402','33402','33406','12213','23411'}
    if not (W/'features.parquet').exists():
        x=features(f);put(W/'feature_checks.json',causal_checks(f,x));x.to_parquet(W/'features.parquet',index=False,compression='zstd')
        put(W/'feature_contract.json',dict(columns=list(x.columns),rows=len(x),sha256=sha(W/'features.parquet')))
    groups=sorted(set(f.group)-{'competition'});assert len(groups)==4
    excluded=[*((g,) for g in groups),*combinations(groups,2)]
    with ProcessPoolExecutor(max_workers=2) as pool:
        tasks=[pool.submit(fit_job,key,name) for key in excluded for name in NAMES]
        for i,task in enumerate(as_completed(tasks),1):
            r=task.result();print('FIT',i,'/20','__'.join(r['excluded']),r['name'],round(r['seconds'],1),flush=True)
    base=pd.read_parquet(P/'competition_submission/icy_road_model/results/evaluation/development_predictions.parquet').sort_values(['station','time']).reset_index(drop=True)
    base=base.merge(f[['station','time','asos_air_temp']],on=['station','time'],validate='one_to_one')
    base['available']=base.physical_both.notna();base['baseline']=base.physical_both;base['physical']=base.baseline
    base['asos_zero']=np.where(base.available,base.asos_air_temp.le(0),np.nan)
    tables={}
    for key in excluded:
        q=base.loc[base.group.isin(key)].copy();stem='__'.join(key)
        for name in NAMES:
            r=read(W/(stem+'__'+name+'.json'));assert not set(q.station)&set(r['training_stations'])
            q=q.merge(pd.read_parquet(W/(stem+'__'+name+'.parquet')).rename(columns={'score':name}),on=['station','time'],validate='one_to_one')
        if len(key)==2:
            sp=SNOW/(stem+'__predictions.parquet');r=read(SNOW/(stem+'__receipt.json'));assert sha(sp)==r['predictions_sha256']
            q=q.merge(pd.read_parquet(sp,columns=['station','time','baseline']).rename(columns={'baseline':'physical_nested'}),on=['station','time'],validate='one_to_one')
            assert np.array_equal(q.physical_nested.notna(),q.available)
        tables[key]=q
    jobs=[];selections={}
    for held in groups:
        inner=pd.concat([tables[tuple(sorted([held,g]))].loc[lambda q:q.group.eq(g)] for g in groups if g!=held],ignore_index=True)
        path=W/(held+'__inner.parquet');inner.to_parquet(path,index=False,compression='zstd')
        physical=evaluate(inner,inner.physical_nested,minimum_valid_slots=1)[0];air=evaluate(inner,inner.asos_zero,minimum_valid_slots=1)[0]
        selections[held]=[dict(name=n,threshold=0.,complexity=i,track='f1',**{k:r[k] for k in ['precision','recall','f1','fp']}) for n,i,r in [('physical',0,physical),('asos_zero',1,air)]]
        for name in NAMES:jobs.append((held,name,path,.95*physical['recall'],max(physical['f1'],air['f1'])))
    # Both unconstrained F1 and recall-guarded precision get their own threshold selection.
    with ProcessPoolExecutor(max_workers=2) as pool:
        tasks={pool.submit(threshold_job,h,n,p,0.,0.):(h,n,'f1') for h,n,p,_,_ in jobs}
        tasks.update({pool.submit(threshold_job,*j):(j[0],j[1],'precision') for j in jobs})
        for task in as_completed(tasks):
            held,name,found=task.result();track=tasks[task][2];r=found[track]
            if r is not None:selections[held].append(dict(name=name,complexity=2,track=track,**r))
            print('THRESHOLD',held,name,track,flush=True)
    decisions=[]
    for held in groups:
        table=pd.DataFrame(selections[held]);table.to_csv(W/(held+'__selection.csv'),index=False)
        primary=table.loc[table.track.eq('f1')].sort_values(['f1','complexity','fp','threshold'],ascending=[False,True,True,False]).iloc[0]
        decisions.append(dict(held=held,name=primary['name'],threshold=float(primary.threshold)))
    put(W/'selection_seal.json',dict(decisions=decisions,outer_candidate_metrics_computed=False))
    parts=[]
    for d in decisions:
        q=tables[(d['held'],)].copy();q['candidate']=q[d['name']] if d['name'] in ['physical','asos_zero'] else binary_prediction(q,q[d['name']],d['threshold']);parts.append(q)
    result=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True);reports={};days={}
    for name in ['physical','asos_zero','candidate']:
        reports[name],ds,events=reports_for(result,name);days[name]=ds[1];ds[1].to_csv(W/(name+'__days.csv'),index=False);events.to_csv(W/(name+'__events.csv'),index=False)
    sensitivity=block(days['candidate'],days['physical'],2026110622);c=reports['candidate'];b=reports['physical'];a=reports['asos_zero']
    gates=dict(precision=c['1']['precision']>=b['1']['precision']*1.10,f1=c['1']['f1']>=max(b['1']['f1'],a['1']['f1'])*1.05,
        recall=c['1']['recall']>=b['1']['recall']*.95,events=c['events']['lost_events']<=b['events']['candidate_detected']*.05,
        strict144=c['144']['f1']>=max(b['144']['f1'],a['144']['f1']),winters=all(c['winters'][y]['f1']>=b['winters'][y]['f1'] for y in b['winters']),
        regions=all(c['regions'][g]['f1']>=b['regions'][g]['f1']*.9 for g in groups),calendar_sensitivity=sensitivity['difference_percentiles'][0]>0)
    result.to_parquet(W/'predictions.parquet',index=False,compression='zstd');assert verify_preserved()==preserved
    put(W/'summary.json',dict(status='short_forcing_nested_complete',new_model_fits=20,threshold_searches=16,decisions=decisions,reports=reports,sensitivity=sensitivity,
        promotion_gates=gates,promote=all(gates.values()),protected_outcomes_used=False,external_four_outcomes_used=False,new_independent_assessment=False,production_model_changed=False))
    print(json.dumps(dict(gates=gates,promote=all(gates.values()),metrics={n:{k:r['1'][k] for k in ['precision','recall','f1']} for n,r in reports.items()}),ensure_ascii=False),flush=True)
if __name__=='__main__':main()
