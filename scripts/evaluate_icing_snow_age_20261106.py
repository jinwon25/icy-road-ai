"""적설 증가 이력 정책을 원본 온도 모델과 지역 이중 제외로 평가한다."""
from datetime import datetime,timezone
from itertools import combinations
from pathlib import Path
import json,sys,time
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.submission_runtime import FEATURES,WATER,infer
from src.icing_snow_age_20261106 import snow_growth_history,filter_snow_alerts
from src.official_metrics_20261106 import evaluate,WINTERS
from src.blind_icing import event_table
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from scripts.evaluate_objective_icing import verify_preserved
from scripts.evaluate_official_icing_upgrade_20261106 import block,independent
from scripts.evaluate_icing_precision_20261106 import read,write,now


def reports_for(frame,name):
    r={};days_all={}
    for minimum in [1,144]:
        s,stations,days=evaluate(frame,frame[name],minimum_valid_slots=minimum)
        proof=independent(frame,frame[name].to_numpy(float),minimum)
        for key,value in proof.items():
            if value is None:assert s[key] is None
            else:np.testing.assert_allclose(s[key],value,atol=1e-12,rtol=0)
        r[str(minimum)]=s;days_all[minimum]=days
    r['events'],events=event_table(frame,frame[name],frame.baseline)
    r['winters']={}
    for year in [2024,2025]:
        q=frame.loc[frame.winter.eq(year)]
        r['winters'][str(year)]=evaluate(q,q[name],minimum_valid_slots=1,winters=[w for w in WINTERS if w[0].startswith(str(year))])[0]
    r['regions']={g:evaluate(q,q[name],minimum_valid_slots=1)[0] for g,q in frame.groupby('group')}
    return r,days_all,events


def main():
    cfg=ROOT/'config/icing_snow_age_20261106.json';p=read(cfg);out=ROOT/p['output']
    paths=[cfg,Path(__file__),ROOT/'src/icing_snow_age_20261106.py',ROOT/p['weather_source'],ROOT/p['training_source'],
           ROOT/p['reference'],ROOT/p['context_source'],ROOT/'src/submission_runtime.py',ROOT/'src/official_metrics_20261106.py']
    signatures={f.relative_to(ROOT).as_posix():sha(f) for f in paths}
    preserved=verify_preserved()
    if out.exists():
        assert read(out/'plan.json')['signatures']==signatures
        if (out/'summary.json').exists():raise FileExistsError('Preserve completed experiment')
    else:
        out.mkdir()
        write(out/'plan.json',dict(settings=p,signatures=signatures,started_at_utc=now(),preservation=preserved))
    f=pd.read_parquet(ROOT/p['training_source']).sort_values(['station','time']).reset_index(drop=True)
    context=pd.read_parquet(ROOT/p['context_source'],columns=['station','time',*WATER])
    added=[c for c in WATER if c not in f]
    f=f.merge(context[['station','time',*added]],on=['station','time'],validate='one_to_one')
    extra=pd.read_parquet(ROOT/p['weather_source'],columns=['station','time','asos_snow_cm','asos_new_snow3h']).sort_values(['station','time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(f[['station','time']],extra[['station','time']])
    assert len(set(f.station))==23 and not set(f.station)&set(p['blocked_stations'])
    h=snow_growth_history(extra)
    if not (out/'history.parquet').exists():
        pd.concat([extra[['station','time']],h],axis=1).to_parquet(out/'history.parquet',index=False,compression='zstd')
    fits=read(ROOT/p['temperature_models']/'fits.json');tables={};new_fits=[]
    groups=sorted(set(f.group)-{'competition'})
    reference=pd.read_parquet(ROOT/p['reference'],columns=['station','time','ice','physical_both'])
    for excluded in [*((g,) for g in groups),*combinations(groups,2)]:
        stem='__'.join(excluded);query=f.loc[f.group.isin(excluded)]
        path=out/(stem+'__predictions.parquet');receipt=out/(stem+'__receipt.json')
        if receipt.exists():
            record=read(receipt);assert record['predictions_sha256']==sha(path)
            tables[excluded]=pd.read_parquet(path);new_fits.extend(record['new_fits'])
            continue
        models=[];records=[]
        for loss,label in [('squared_error','mse'),('absolute_error','mae')]:
            if len(excluded)==1:
                old=[r for r in fits if r['kind']=='temperature' and r['scope']=='both' and r['context']==list(excluded) and r['name']==label]
                assert len(old)==1
                model_path=ROOT/p['temperature_models']/old[0]['model_path']
                assert sha(model_path)==old[0]['model_sha256']
                model=joblib.load(model_path)
            else:
                train=f.loc[~f.group.isin(excluded)&f.road_temp.notna()&f.asos_air_temp.notna()]
                assert not set(train.station)&set(query.station)
                started=time.perf_counter()
                model=HistGradientBoostingRegressor(loss=loss,**p['temperature_parameters'])
                with threadpool_limits(limits=2),deny_network() as attempts:
                    model.fit(train[list(FEATURES)],train.road_temp)
                assert not attempts
                model_path=out/(stem+'__'+label+'.joblib')
                joblib.dump(model,model_path,compress=3)
                record=dict(excluded=list(excluded),kind=label,training_stations=sorted(train.station.unique()),
                            rows=len(train),model_sha256=sha(model_path),seconds=time.perf_counter()-started)
                records.append(record);new_fits.append(record)
                print('FIT',len(new_fits),'/12',stem,label,round(record['seconds'],2),flush=True)
            models.append(model)
        weather=query[list(dict.fromkeys(['station','time',*FEATURES,*WATER]))]
        with deny_network() as attempts:
            runtime=infer(weather,models)
        assert not attempts
        policies=filter_snow_alerts(query,runtime,h.loc[query.index])
        q=query[['station','time','winter','group','ice']].copy()
        for name,value in policies.items():q[name]=value
        q['available']=np.isfinite(q.baseline)
        if len(excluded)==1:
            matched=q.merge(reference,on=['station','time'],validate='one_to_one',suffixes=['','_reference'])
            np.testing.assert_array_equal(matched.ice,matched.ice_reference)
            np.testing.assert_array_equal(matched.baseline,matched.physical_both)
        q.to_parquet(path,index=False,compression='zstd')
        write(receipt,dict(excluded=list(excluded),predictions_sha256=sha(path),new_fits=records))
        tables[excluded]=q.reset_index(drop=True)
    decisions=[];parts=[]
    for held in groups:
        inner=pd.concat([tables[tuple(sorted([held,other]))].loc[lambda q:q.group.eq(other)] for other in groups if other!=held],ignore_index=True)
        b,b_days,_=reports_for(inner,'baseline')
        rows=[]
        for name in p['candidates']:
            c,_,_=reports_for(inner,name)
            feasible=(c['1']['precision']>=b['1']['precision']*1.10 and c['1']['f1']>=b['1']['f1']*1.05 and
                      c['1']['recall']>=b['1']['recall']*.95 and c['events']['lost_events']==0 and
                      all(c['winters'][y]['f1']>=b['winters'][y]['f1'] for y in b['winters']))
            rows.append(dict(candidate=name,f1=c['1']['f1'],precision=c['1']['precision'],recall=c['1']['recall'],
                             lost_events=c['events']['lost_events'],feasible=bool(feasible)))
        table=pd.DataFrame(rows);table.to_csv(out/(held+'__inner.csv'),index=False)
        eligible=table.loc[table.feasible]
        choice='baseline' if eligible.empty else eligible.sort_values(['f1','candidate'],ascending=[False,True]).iloc[0].candidate
        decisions.append(dict(held=held,candidate=choice))
        q=tables[(held,)].copy();q['nested']=q[choice]
        parts.append(q)
    # 원본 ASOS 기온은 별도 키 결합하며 외부 정답에는 의존하지 않는다.
    result=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    result=result.merge(f[['station','time','asos_air_temp']],on=['station','time'],validate='one_to_one')
    result['asos_zero']=np.where(result.available,result.asos_air_temp.le(0),np.nan)
    seal=out/'selection_seal.json'
    if seal.exists():assert read(seal)['decisions']==decisions
    else:write(seal,dict(at_utc=now(),decisions=decisions,outer_metrics_computed=False))
    result.to_parquet(out/'predictions.parquet',index=False,compression='zstd')
    reports={};daily={}
    for name in [*p['candidates'],'nested','asos_zero']:
        r,d,e=reports_for(result,name);reports[name]=r;daily[name]=d
        d[1].to_csv(out/(name+'__daily.csv'),index=False)
        e.to_csv(out/(name+'__events.csv'),index=False)
    c=reports['nested'];b=reports['baseline'];a=reports['asos_zero']
    sensitivity=block(daily['nested'][1],daily['baseline'][1],p['seed'])
    gates=dict(precision=c['1']['precision']>=b['1']['precision']*1.10,
               f1=c['1']['f1']>=b['1']['f1']*1.05 and c['1']['f1']>a['1']['f1'],
               strict144=c['144']['f1']>=b['144']['f1'],recall=c['1']['recall']>=b['1']['recall']*.95,
               events=c['events']['lost_events']==0,
               winters=all(c['winters'][y]['f1']>=b['winters'][y]['f1'] for y in b['winters']),
               regions=all(c['regions'][g]['f1']>=b['regions'][g]['f1']*.9 for g in groups),
               calendar_sensitivity=sensitivity['difference_percentiles'][0]>=0)
    assert verify_preserved()==preserved
    write(out/'summary.json',dict(status='snow_age_icing_evaluated',at_utc=now(),reports=reports,decisions=decisions,new_fits=new_fits,
          promotion_gates=gates,promote=all(gates.values()),sensitivity=sensitivity,predictions_sha256=sha(out/'predictions.parquet'),
          protected_outcomes_used=False,external_four_outcomes_used=False,new_independent_assessment=False,production_model_changed=False))
    print(json.dumps(dict(status='complete',gates=gates,promote=all(gates.values()),
        metrics={k:{m:v['1'][m] for m in ['precision','recall','f1']} for k,v in reports.items()}),ensure_ascii=False),flush=True)


if __name__=='__main__':main()
