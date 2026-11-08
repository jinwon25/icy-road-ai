"""재현율 하한을 없앤 공식 F1 내부 선택을 저장된 지역 이중 제외 예측으로 검토한다."""
from pathlib import Path
from itertools import combinations
from concurrent.futures import ProcessPoolExecutor,as_completed
from datetime import datetime,timezone
import json,sys,time
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.icing_precision_20261106 import exact_threshold,binary_prediction
from src.data_source import sha256_file as sha
from src.official_metrics_20261106 import evaluate
from scripts.evaluate_icing_snow_age_20261106 import reports_for
from scripts.evaluate_official_icing_upgrade_20261106 import block
from scripts.evaluate_objective_icing import verify_preserved
P=ROOT/'outputs/private';W=P/'unconstrained_icing_selection_20261106'
CACHE=P/'icing_precision_20261106';SNOW=P/'icing_snow_age_20261106_checked'
NAMES=['snapshot_station','snapshot_day','process_station','process_day']

def write(p,value):
    with p.open('x',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')

def threshold_job(held,name,path):
    frame=pd.read_parquet(path);started=time.perf_counter()
    found=exact_threshold(frame,frame[name].to_numpy(float),recall_floor=0.,precision_f1_floor=0.)['f1']
    if found is None:return held,name,None,time.perf_counter()-started
    proof=evaluate(frame,binary_prediction(frame,frame[name],found['threshold']),minimum_valid_slots=1)[0]
    for key in ['precision','recall','f1']:np.testing.assert_allclose(found[key],proof[key],rtol=0,atol=1e-12)
    return held,name,found,time.perf_counter()-started

def main():
    assert not W.exists();W.mkdir();preserved=verify_preserved()
    basepath=P/'competition_submission/icy_road_model/results/evaluation/development_predictions.parquet'
    weatherpath=P/'blind_icing_20261025_v2/training.parquet'
    plan=dict(at_utc=datetime.now(timezone.utc).isoformat(),
        purpose='공식 규정에 없는 Recall>=0.70의 내부 선택 제약이 결과를 제한했는지 확인',
        selection='4개 기존 분류기와 ASOS 0도·지역 이중 제외 온도/수분 기준 중 내부 공식 F1 최대. 재현율 하한 없음. 동률은 단순한 방법·FP 적음·높은 문턱 우선',
        model_fits=0,outer_regions=4,inner_scores='해당 외부 지역과 내부 검증 지역을 모두 제외한 저장 예측',
        candidate_names=NAMES,recall_floor=0.,
        eligibility='기존 고정 물리 기준의 동일 가용 시각. 추가 216개 무결빙 시각으로 분모가 달라지지 않도록 함',
        baseline_option='내부의 물리 기준도 두 지역을 제외한 별도 저장 예측을 사용. 외부 지역 정답이 온도 학습에 들어간 예측을 내부 선택에 쓰지 않음',
        promotion_gates=dict(f1_gain_over_both_baselines=.05,precision_not_below_physical=True,
            strict144_f1_not_below_both_baselines=True,each_winter_f1_not_below_physical=True,
            maximum_absolute_regional_f1_decline=.0025,seven_day_block_lower_delta_positive=True),
        recall_and_lost_events='별도로 모두 보고하며 F1 향상으로 은폐하지 않음',
        protected_outcomes_used=False,external_four_outcomes_used=False,new_independent_assessment=False,
        production_model_changed=False,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [basepath,weatherpath,CACHE/'plan.json',CACHE/'evaluation_mask_addendum.json']})
    write(W/'plan.json',plan)
    base=pd.read_parquet(basepath).sort_values(['station','time']).reset_index(drop=True)
    weather=pd.read_parquet(weatherpath,columns=['station','time','asos_air_temp'])
    base=base.merge(weather,on=['station','time'],validate='one_to_one')
    assert len(set(base.station))==9 and not set(base.station)&{'12410','33411','23402','33402','33406','12213','23411'}
    base['physical']=base.physical_both;base['baseline']=base.physical;base['available']=base.physical.notna()
    base['asos_zero']=np.where(base.available,base.asos_air_temp.le(0),np.nan)
    groups=sorted(base.group.unique());assert len(groups)==4
    tables={};audits=[]
    for excluded in [*((g,) for g in groups),*combinations(groups,2)]:
        stem='__'.join(excluded);q=base.loc[base.group.isin(excluded)].copy()
        for name in NAMES:
            r=json.loads((CACHE/(stem+'__'+name+'.json')).read_text('utf8'))
            path=CACHE/(stem+'__'+name+'.parquet')
            assert sha(path)==r['scores_sha256'] and sha(CACHE/r['model'])==r['model_sha256']
            assert not set(q.station)&set(r['training_stations'])
            scores=pd.read_parquet(path)
            q=q.merge(scores.rename(columns={'score':name}),on=['station','time'],validate='one_to_one')
            assert np.isfinite(q[name]).all()
            audits.append(dict(excluded=excluded,name=name,scores_sha256=sha(path),model_sha256=r['model_sha256']))
        if len(excluded)==2:
            path=SNOW/(stem+'__predictions.parquet');r=json.loads((SNOW/(stem+'__receipt.json')).read_text('utf8'))
            assert sha(path)==r['predictions_sha256']
            q=q.merge(pd.read_parquet(path,columns=['station','time','baseline']).rename(columns={'baseline':'physical_nested'}),on=['station','time'],validate='one_to_one')
            assert np.array_equal(np.isfinite(q.physical_nested),q.available)
        tables[excluded]=q
    jobs=[];thresholds={g:[] for g in groups}
    for held in groups:
        inner=pd.concat([tables[tuple(sorted([held,other]))].loc[lambda x:x.group.eq(other)] for other in groups if other!=held],ignore_index=True)
        path=W/(held+'__inner_scores.parquet');inner.to_parquet(path,index=False,compression='zstd')
        for name in NAMES:jobs.append((held,name,path))
        for name,col in [('physical','physical_nested'),('asos_zero','asos_zero')]:
            report=evaluate(inner,inner[col],minimum_valid_slots=1)[0]
            thresholds[held].append(dict(name=name,threshold=0.,complexity=0 if name=='asos_zero' else 1,**{k:report[k] for k in ['precision','recall','f1','tp','fp']}))
    with ProcessPoolExecutor(max_workers=2) as pool:
        future={pool.submit(threshold_job,*job):job for job in jobs}
        for task in as_completed(future):
            held,name,found,seconds=task.result()
            if found is not None:thresholds[held].append(dict(name=name,complexity=3 if name.startswith('process') else 2,**found))
            print('THRESHOLD',held,name,round(seconds,1),flush=True)
    decisions=[]
    for held in groups:
        table=pd.DataFrame(thresholds[held]);table.to_csv(W/(held+'__selection.csv'),index=False)
        t=table.loc[table.f1.ge(table.f1.max()-1e-12)].sort_values(['complexity','fp','threshold','name'],ascending=[True,True,False,True])
        best=t.iloc[0];decisions.append(dict(held=held,name=str(best['name']),threshold=float(best.threshold)))
    write(W/'selection_seal.json',dict(decisions=decisions,outer_candidate_metrics_computed=False))
    parts=[]
    for d in decisions:
        q=tables[(d['held'],)].copy()
        q['candidate']=q[d['name']] if d['name'] in ['physical','asos_zero'] else binary_prediction(q,q[d['name']],d['threshold'])
        assert np.array_equal(np.isfinite(q.candidate),q.available)
        parts.append(q)
    result=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    reports={};days={}
    for name in ['physical','asos_zero','candidate']:
        reports[name],ds,events=reports_for(result,name);days[name]=ds[1]
        ds[1].to_csv(W/(name+'__days.csv'),index=False);events.to_csv(W/(name+'__events.csv'),index=False)
    sensitivity=block(days['candidate'],days['physical'],2026110621)
    c=reports['candidate'];b=reports['physical'];air=reports['asos_zero']
    gates=dict(f1=c['1']['f1']>=1.05*max(b['1']['f1'],air['1']['f1']),precision=c['1']['precision']>=b['1']['precision'],
        strict144=c['144']['f1']>=max(b['144']['f1'],air['144']['f1']),
        winters=all(c['winters'][y]['f1']>=b['winters'][y]['f1'] for y in b['winters']),
        regions=all(c['regions'][g]['f1']>=b['regions'][g]['f1']-.0025 for g in groups),
        calendar_sensitivity=sensitivity['difference_percentiles'][0]>0)
    result.to_parquet(W/'predictions.parquet',index=False,compression='zstd')
    assert verify_preserved()==preserved
    summary=dict(status='unconstrained_nested_selection_complete',decisions=decisions,reports=reports,sensitivity=sensitivity,
        promotion_gates=gates,promote=all(gates.values()),cached_model_scores_audited=len(audits),new_model_fits=0,
        threshold_searches=len(jobs),common_valid_pairs=int((result.available&result.ice.isin([0,1])).sum()),
        protected_outcomes_used=False,new_independent_assessment=False,production_model_changed=False)
    write(W/'summary.json',summary);write(W/'source_score_audit.json',audits)
    print(json.dumps(dict(gates=gates,promote=summary['promote'],metrics={n:{k:r['1'][k] for k in ['precision','recall','f1']} for n,r in reports.items()}),ensure_ascii=False),flush=True)
if __name__=='__main__':main()
