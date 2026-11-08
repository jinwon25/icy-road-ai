"""같은 48적합을 입력 행 복사 후 원 특성 해제 방식으로 재개한다. 후보 변경 없음."""
import gc
from pathlib import Path
import shutil
import sys
import time

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_weather_space_time import metrics,sensitivity
from scripts.evaluate_objective_icing import read,write,now,verify_preserved
from src.weather_temporal import split_masks
from src.road_weather_transfer import baselines,balanced_weights,constrain
from src.offline_runtime import deny_network
from src.data_source import sha256_file as sha


def initialize(config,plan):
    old=ROOT/plan['checkpoint_source'];out=ROOT/plan['output']
    previous=read(old/'plan.json')
    assert not (old/'summary.json').exists(), 'Do not resume after viewing completed scores'
    for relative,digest in previous['signatures'].items():assert sha(ROOT/relative)==digest,relative
    before=previous['settings']
    assert {k:v for k,v in plan.items() if k not in ['output','checkpoint_source','implementation_change']} == {k:v for k,v in before.items() if k!='output'}
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in [config,Path(__file__),
        ROOT/'scripts/evaluate_weather_space_time.py',ROOT/'src/weather_temporal.py',
        ROOT/'src/road_weather_transfer.py',ROOT/plan['input']]}
    frozen=verify_preserved()
    if out.exists():
        assert read(out/'plan.json')['signatures']==signatures
        assert not (out/'summary.json').exists(), 'Preserve completed experiment'
        return out,frozen
    out.mkdir(parents=True)
    write(out/'plan.json',dict(at_utc=now(),settings=plan,signatures=signatures,preservation=frozen))
    copied={};count=0
    for candidate in plan['candidates']:
        source=old/(candidate+'_features.parquet');target=out/source.name
        shutil.copy2(source,target);assert sha(source)==sha(target)
        copied[target.relative_to(out).as_posix()]=sha(target)
    for target in plan['targets']:
        (out/target).mkdir()
        for meta in (old/target).glob('*.json'):
            spec=read(meta)
            if 'model_sha256' not in spec:continue
            model=meta.with_suffix('.joblib');prediction=meta.with_suffix('.npy')
            assert sha(model)==spec['model_sha256'] and sha(prediction)==spec['prediction_sha256']
            for source in [meta,model,prediction]:
                destination=out/target/source.name;shutil.copy2(source,destination)
                assert sha(source)==sha(destination)
                copied[destination.relative_to(out).as_posix()]=sha(destination)
            count+=1
    write(out/'checkpoint_reuse.json',dict(at_utc=now(),source=plan['checkpoint_source'],
        source_plan_sha256=sha(old/'plan.json'),verified_completed_fits=count,files=copied,
        settings_unchanged=True,external_metrics_not_yet_computed=True))
    return out,frozen


def main():
    config=ROOT/'config/weather_temporal_memory_20261101.json';plan=read(config)
    out,frozen=initialize(config,plan)
    f=pd.read_parquet(ROOT/plan['input']).sort_values(['station','time']).reset_index(drop=True)
    assert sha(ROOT/plan['input'])==plan['input_sha256']
    assert not set(f.station)&set(plan['blocked_stations'])
    assert not {'ice','road_temp','state_raw'}&set(f)
    groups=sorted(set(f.group)-{'competition'});assert len(groups)==4
    schemas={c:pq.ParquetFile(out/(c+'_features.parquet')).schema.names for c in plan['candidates']}
    fits=[];all_reports={}
    for target in plan['targets']:
        asos,nearest=baselines(f,target)
        valid=np.isfinite(f[target])&np.isfinite(asos)&np.isfinite(nearest)
        folder=out/target;parts=[]
        for year in [2024,2025]:
            for held in groups:
                train,query=split_masks(f,valid,held,year)
                result=f.loc[query,['station','time','group','winter']].copy()
                result['observed']=f.loc[query,target];result['asos']=asos[query]
                result['aws_fallback']=nearest[query];result['cold_input']=np.abs(f.loc[query,'asos_air_temp'])<=3
                for candidate in plan['candidates']:
                    stem=f'{candidate}_{held}_{year}';modelpath=folder/(stem+'.joblib')
                    predpath=folder/(stem+'.npy');metapath=folder/(stem+'.json')
                    if metapath.exists():
                        record=read(metapath)
                        assert sha(modelpath)==record['model_sha256'] and sha(predpath)==record['prediction_sha256']
                        predicted=np.load(predpath,allow_pickle=False)
                    else:
                        if modelpath.exists() or predpath.exists():raise FileExistsError('Unrecorded partial fit')
                        x=pd.read_parquet(out/(candidate+'_features.parquet'))
                        train_x=x.loc[train];query_x=x.loc[query]
                        del x;gc.collect();pa.default_memory_pool().release_unused()
                        start=time.perf_counter();model=HistGradientBoostingRegressor(**plan['model'])
                        with deny_network() as attempts,threadpool_limits(limits=2):
                            model.fit(train_x,f.loc[train,target].to_numpy()-nearest[train],sample_weight=balanced_weights(f.loc[train]))
                            predicted=constrain(model.predict(query_x)+nearest[query],target)
                        assert not attempts and np.isfinite(predicted).all()
                        joblib.dump(model,modelpath,compress=3);np.save(predpath,predicted,allow_pickle=False)
                        record=dict(target=target,candidate=candidate,held=held,query_winter=year,
                            direction=plan['directions'][str(year)],training_rows=int(train.sum()),query_rows=int(query.sum()),
                            training_stations=sorted(f.loc[train,'station'].unique()),
                            training_winters=sorted(int(y) for y in f.loc[train,'winter'].unique()),
                            query_stations=sorted(f.loc[query,'station'].unique()),features=schemas[candidate],
                            model_sha256=sha(modelpath),prediction_sha256=sha(predpath),seconds=time.perf_counter()-start,network_attempts=0)
                        write(metapath,record)
                        del model,train_x,query_x;gc.collect();pa.default_memory_pool().release_unused()
                    fits.append(record);result[candidate]=predicted
                    print('FIT',len(fits),'/48',target,candidate,year,held,round(record['seconds'],1),flush=True)
                parts.append(result)
        p=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
        assert not p.duplicated(['station','time']).any()
        p.to_parquet(folder/'predictions.parquet',index=False,compression='zstd')
        reports={c:metrics(p,c) for c in ['asos','aws_fallback',*plan['candidates']]}
        reference=reports['instant_residual'];candidate=reports['history_residual'];g=plan['gates']
        boot=sensitivity(p,'history_residual','instant_residual',plan['bootstrap'])
        gates=dict(pooled=candidate['pooled']['mae']<=reference['pooled']['mae']*(1-g['minimum_mae_reduction_vs_instant']),
            both_directions=all(candidate['directions'][y]['mae']<=b['mae']*g['maximum_direction_mae_ratio'] for y,b in reference['directions'].items()),
            every_region=all(candidate['regions'][k]['mae']<=b['mae']*g['maximum_region_mae_ratio'] for k,b in reference['regions'].items()),
            cold=candidate['cold']['mae']<=reference['cold']['mae']*g['maximum_cold_air_mae_ratio'],date_sensitivity=boot['quantiles'][2]<0)
        all_reports[target]=dict(metrics=reports,history_gates=gates,history_success=all(gates.values()),
            history_vs_instant_bootstrap=boot,instant_vs_aws_bootstrap=sensitivity(p,'instant_residual','aws_fallback',plan['bootstrap']))
    assert len(fits)==48 and verify_preserved()==frozen
    write(out/'summary.json',dict(status='weather_temporal_complete',reports=all_reports,fits=fits,
        production_model_changed=False,new_independent_assessment=False,preservation=frozen,
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
    print('COMPLETE',{t:r['history_success'] for t,r in all_reports.items()},flush=True)


if __name__=='__main__':main()
