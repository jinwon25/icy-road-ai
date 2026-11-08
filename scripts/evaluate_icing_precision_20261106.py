"""기상 과정 추가의 정밀도·재현율·F1을 지역 이중 제외로 비교한다."""
from datetime import datetime,timezone
from itertools import combinations
from pathlib import Path
import json,sys,time
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.icing_precision_20261106 import features,weights,binary_prediction,exact_threshold
from src.official_metrics_20261106 import evaluate,WINTERS
from src.blind_icing import event_table
from src.offline_runtime import deny_network
from src.data_source import sha256_file as sha
from scripts.evaluate_objective_icing import verify_preserved
from scripts.evaluate_official_icing_upgrade_20261106 import block,independent


def read(p):
    return json.loads(Path(p).read_text(encoding='utf8'))


def write(p,value):
    with Path(p).open('x',encoding='utf8') as s:
        json.dump(value,s,ensure_ascii=False,indent=2,allow_nan=False)
        s.write('\n')


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    cfg=ROOT/'config/icing_precision_20261106.json'
    plan=read(cfg);out=ROOT/plan['output']
    signature_paths=[cfg,Path(__file__),ROOT/'src/icing_precision_20261106.py',
                     ROOT/'src/official_metrics_20261106.py',ROOT/plan['source'],ROOT/plan['reference']]
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in signature_paths}
    preserved=verify_preserved()
    if out.exists():
        seal=read(out/'plan.json')
        if seal['signatures']!=signatures:
            raise ValueError('Experiment changed after initial seal')
        if (out/'summary.json').exists():
            raise FileExistsError('Completed experiment is preserved')
    else:
        out.mkdir()
        write(out/'plan.json',dict(settings=plan,signatures=signatures,
              started_at_utc=now(),preservation=preserved,new_independent_assessment=False))
    f=pd.read_parquet(ROOT/plan['source']).sort_values(['station','time']).reset_index(drop=True)
    assert len(set(f.station))==23 and not set(f.station)&set(plan['blocked_stations'])
    assert not f.duplicated(['station','time']).any()
    groups=sorted(set(f.group)-{'competition'})
    assert len(groups)==4
    representation={k:features(f,k) for k in ['snapshot','process']}
    write_path=out/'feature_contract.json'
    if not write_path.exists():
        write(write_path,{k:dict(count=len(v.columns),names=list(v.columns)) for k,v in representation.items()})
    tables={};fits=[]
    exclusions=[*((g,) for g in groups),*combinations(groups,2)]
    for excluded in exclusions:
        stem='__'.join(excluded)
        train=(~f.group.isin(excluded)&f.available&f.ice.isin([0,1])).to_numpy()
        query=f.group.isin(excluded).to_numpy()
        q=f.loc[query,['station','time','group','winter','ice','available','asos_air_temp']].copy()
        assert not set(f.loc[train,'station'])&set(q.station)
        for spec in plan['models']:
            path=out/(stem+'__'+spec['name']+'.joblib')
            score_path=out/(stem+'__'+spec['name']+'.parquet')
            receipt_path=out/(stem+'__'+spec['name']+'.json')
            if receipt_path.exists():
                receipt=read(receipt_path)
                assert receipt['model_sha256']==sha(path) and receipt['scores_sha256']==sha(score_path)
                saved=pd.read_parquet(score_path)
                pd.testing.assert_frame_equal(saved[['station','time']],q[['station','time']].reset_index(drop=True))
                q[spec['name']]=saved.score.to_numpy()
                fits.append(receipt)
                continue
            started=time.perf_counter()
            x=representation[spec['features']]
            with threadpool_limits(limits=2),deny_network() as attempts:
                model=HistGradientBoostingClassifier(**plan['parameters'])
                model.fit(x.loc[train],f.loc[train,'ice'].astype(int),sample_weight=weights(f.loc[train],spec['weights']))
                score=model.predict_proba(x.loc[query])[:,1]
            assert not attempts
            joblib.dump(model,path,compress=3)
            with threadpool_limits(limits=2):
                np.testing.assert_array_equal(score,joblib.load(path).predict_proba(x.loc[query])[:,1])
            saved=q[['station','time']].copy()
            saved['score']=score
            saved.to_parquet(score_path,index=False,compression='zstd')
            q[spec['name']]=score
            receipt=dict(excluded=list(excluded),name=spec['name'],model=path.name,model_sha256=sha(path),
                         scores_sha256=sha(score_path),training_rows=int(train.sum()),
                         training_stations=sorted(f.loc[train,'station'].unique()),positive_rows=int(f.loc[train,'ice'].sum()),
                         feature_count=len(x.columns),seconds=time.perf_counter()-started)
            write(receipt_path,receipt)
            fits.append(receipt)
            print('FIT',len(fits),'/40',stem,spec['name'],round(receipt['seconds'],2),flush=True)
        tables[excluded]=q.reset_index(drop=True)
    # 외부 지역 정답은 자기 내부 임계값·후보 선택에 사용하지 않는다.
    choices_path=out/'selection_seal.json'
    parts=[];decisions=[]
    for held in groups:
        inner=pd.concat([tables[tuple(sorted([held,other]))].loc[lambda q:q.group.eq(other)]
                         for other in groups if other!=held],ignore_index=True)
        baseline=np.where(inner.available,inner.asos_air_temp.le(0),np.nan)
        bm=evaluate(inner,baseline,minimum_valid_slots=1)[0]
        rows=[]
        for spec in plan['models']:
            candidates=exact_threshold(inner,inner[spec['name']].to_numpy(float),recall_floor=.70,precision_f1_floor=bm['f1'])
            for track,selected in candidates.items():
                if selected is None:
                    continue
                proof=evaluate(inner,binary_prediction(inner,inner[spec['name']],selected['threshold']),minimum_valid_slots=1)[0]
                for key in ['f1','precision','recall']:
                    np.testing.assert_allclose(selected[key],proof[key],atol=1e-12,rtol=0)
                rows.append(dict(track=track,name=spec['name'],complexity=2 if spec['features']=='process' else 1,**selected))
        for track in ['f1','precision']:
            if bm['recall']>=.70:
                rows.append(dict(track=track,name='asos_zero',threshold=0.,complexity=0,
                     **{k:bm[k] for k in ['precision','recall','f1','tp','fp']}))
        table=pd.DataFrame(rows)
        table.to_csv(out/(held+'__inner.csv'),index=False,encoding='utf-8-sig')
        chosen={}
        for track in ['f1','precision']:
            t=table.loc[table.track.eq(track)]
            if t.empty:
                chosen[track]=dict(name='asos_zero',threshold=0.,fallback='no_recall_feasible_policy')
            else:
                best=t[track].max()
                t=t.loc[t[track].ge(best-1e-12)].sort_values(['complexity','fp','threshold','name'],ascending=[True,True,False,True])
                chosen[track]={k:t.iloc[0][k].item() if hasattr(t.iloc[0][k],'item') else t.iloc[0][k] for k in ['name','threshold']}
        decisions.append(dict(held=held,choices=chosen))
        q=tables[(held,)].copy()
        q['asos_zero']=np.where(q.available,q.asos_air_temp.le(0),np.nan)
        for track,selection in chosen.items():
            q[track+'_track']=q.asos_zero if selection['name']=='asos_zero' else binary_prediction(q,q[selection['name']],selection['threshold'])
        parts.append(q)
        print('SELECT',held,json.dumps(chosen),flush=True)
    seal_value=dict(at_utc=now(),decisions=decisions,outer_metrics_computed=False)
    if choices_path.exists():
        assert read(choices_path)['decisions']==decisions
    else:
        write(choices_path,seal_value)
    result=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    reference=pd.read_parquet(ROOT/plan['reference'],columns=['station','time','ice','physical_both'])
    result=result.merge(reference,on=['station','time'],validate='one_to_one',suffixes=['','_reference'])
    np.testing.assert_array_equal(result.ice,result.ice_reference)
    # 공통 입력 가용 범위를 고정하고 어려운 행을 모델별로 제외하지 않는다.
    for name in ['asos_zero','f1_track','precision_track']:
        assert np.array_equal(np.isfinite(result[name]),np.isfinite(result.physical_both))
    result.drop(columns='ice_reference').to_parquet(out/'predictions.parquet',index=False,compression='zstd')
    reports={};daily={};all_stations=[];checks=0
    for name in ['physical_both','asos_zero','f1_track','precision_track']:
        r={}
        for minimum in [1,144]:
            s,stations,days=evaluate(result,result[name],minimum_valid_slots=minimum)
            proof=independent(result,result[name].to_numpy(float),minimum)
            for key,value in proof.items():
                if value is None:
                    assert s[key] is None
                else:
                    np.testing.assert_allclose(s[key],value,atol=1e-12,rtol=0)
                checks+=1
            r[str(minimum)]=s
            daily[(name,minimum)]=days
            days.to_csv(out/(name+f'__daily_min{minimum}.csv'),index=False)
            all_stations.append(stations.assign(candidate=name,minimum_valid_slots=minimum))
        r['winters']={}
        for year in [2024,2025]:
            q=result.loc[result.winter.eq(year)]
            r['winters'][str(year)]=evaluate(q,q[name],minimum_valid_slots=1,winters=[w for w in WINTERS if w[0].startswith(str(year))])[0]
        r['regions']={g:evaluate(q,q[name],minimum_valid_slots=1)[0] for g,q in result.groupby('group')}
        r['events'],events=event_table(result,result[name],result.physical_both)
        events.to_csv(out/(name+'__events.csv'),index=False)
        r['no_actual_ice_false_alarm_days']=int(daily[(name,1)].loc[lambda d:~d.station_eligible & d.fp.gt(0)].shape[0])
        reports[name]=r
    pd.concat(all_stations,ignore_index=True).to_csv(out/'station_metrics.csv',index=False,encoding='utf-8-sig')
    sensitivity={track:block(daily[(track,1)],daily[('physical_both',1)],plan['seed']) for track in ['f1_track','precision_track']}
    c=reports['f1_track'];base=reports['physical_both'];air=reports['asos_zero'];g=plan['promotion_gate']
    gates=dict(
        precision=c['1']['precision']>=base['1']['precision']*(1+g['precision_relative_gain']),
        f1=c['1']['f1']>=max(base['1']['f1'],air['1']['f1'])*(1+g['f1_relative_gain_over_both_baselines']),
        strict144=c['144']['f1']>=max(base['144']['f1'],air['144']['f1']),
        recall=c['1']['recall']>=base['1']['recall']*g['recall_relative_to_production'],
        events=c['events']['lost_events']<=base['events']['candidate_detected']*g['maximum_lost_fraction_of_production_events'],
        winters=all(c['winters'][y]['f1']>=base['winters'][y]['f1'] for y in base['winters']),
        regions=all(c['regions'][v]['f1']>=base['regions'][v]['f1']*g['each_region_f1_relative_to_production'] for v in groups),
        calendar_sensitivity=sensitivity['f1_track']['difference_percentiles'][0]>=0.)
    assert verify_preserved()==preserved
    write(out/'summary.json',dict(status='icing_precision_evaluated',at_utc=now(),fits=fits,decisions=decisions,
          reports=reports,sensitivity=sensitivity,promotion_gates=gates,promote=all(gates.values()),
          independent_metric_checks=checks,selection_sha256=sha(choices_path),predictions_sha256=sha(out/'predictions.parquet'),
          protected_outcomes_used=False,external_four_outcomes_used=False,new_independent_assessment=False,production_model_changed=False))
    print(json.dumps(dict(status='complete',gates=gates,promote=all(gates.values()),
          metrics={k:{m:reports[k]['1'][m] for m in ['precision','recall','f1']} for k in reports}),ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
