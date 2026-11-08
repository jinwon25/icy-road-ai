"""목표별 이력 4모형을 기존 지역 제외 모형과 비교. 노면 관측은 읽지 않는다."""
import argparse
import gc
from pathlib import Path
import sys
import time

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,now,verify_preserved
from scripts.evaluate_weather_space_time import sensitivity
from src.road_weather_transfer import baselines,balanced_weights,regression_numbers,constrain,TARGETS
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network


def report(f,column):
    measure=lambda q:regression_numbers(q.observed,q[column])
    return dict(pooled=measure(f),winters={str(y):measure(q) for y,q in f.groupby('winter')},
        regions={g:measure(q) for g,q in f.groupby('group')},cold=measure(f.loc[f.cold_input]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'config/weather_air_history_spatial_20261101.json')
    args=parser.parse_args();config=args.config.resolve();plan=read(config);target=plan['target']
    assert target in TARGETS
    out=ROOT/plan['output'];source=ROOT/plan['source'];baseline=ROOT/plan['baseline']
    if out.exists():raise FileExistsError('Preserve spatial history experiment')
    temporal=read(source/'summary.json');assert temporal['status']=='weather_temporal_complete'
    for name in ['instant_residual_features.parquet','history_residual_features.parquet']:
        assert sha(source/name)==temporal['files'][name]
    assert sha(ROOT/plan['input'])==plan['input_sha256']
    out.mkdir(parents=True)
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in [config,Path(__file__),
        ROOT/plan['input'],source/'summary.json',source/'instant_residual_features.parquet',
        source/'history_residual_features.parquet',baseline/'summary.json']}
    write(out/'plan.json',dict(at_utc=now(),settings=plan,signatures=signatures,
        preservation=temporal['preservation']))
    f=pd.read_parquet(ROOT/plan['input']).sort_values(['station','time']).reset_index(drop=True)
    assert not set(f.station)&set(plan['blocked_stations'])
    assert not {'road_temp','ice','state_raw'}&set(f)
    asos,nearest=baselines(f,target)
    available=np.isfinite(asos)&np.isfinite(nearest)
    good=available&np.isfinite(f[target])
    parts=[];fits=[]
    for held in sorted(set(f.group)-{'competition'}):
        train=good&f.group.ne(held);query=available&f.group.eq(held)
        assert not set(f.loc[train,'station'])&set(f.loc[query,'station'])
        p=f.loc[query,['station','time','group','winter']].copy()
        p['observed']=f.loc[query,target];p['asos']=asos[query];p['aws_fallback']=nearest[query]
        p['cold_input']=np.abs(f.loc[query,'asos_air_temp'])<=3
        old_model=baseline/target/('residual_hgb_'+held+'.joblib')
        old_meta=read(old_model.with_suffix('.json'));assert sha(old_model)==old_meta['model_sha256']
        x=pd.read_parquet(source/'instant_residual_features.parquet');query_x=x.loc[query];del x
        old=joblib.load(old_model)
        with deny_network() as attempts,threadpool_limits(limits=2):p['instant_residual']=constrain(old.predict(query_x)+nearest[query],target)
        assert not attempts
        np.testing.assert_array_equal(p.loc[p.observed.notna(),'instant_residual'],
            np.load(old_model.with_suffix('.npy'),allow_pickle=False))
        del old,query_x;gc.collect();pa.default_memory_pool().release_unused()
        x=pd.read_parquet(source/'history_residual_features.parquet')
        names=list(x);train_x=x.loc[train];query_x=x.loc[query];del x
        gc.collect();pa.default_memory_pool().release_unused()
        start=time.perf_counter();model=HistGradientBoostingRegressor(**plan['model'])
        with deny_network() as attempts,threadpool_limits(limits=2):
            model.fit(train_x,f.loc[train,target].to_numpy()-nearest[train],sample_weight=balanced_weights(f.loc[train]))
            values=constrain(model.predict(query_x)+nearest[query],target)
        assert not attempts and np.isfinite(values).all()
        p['history_residual']=values
        model_path=out/(held+'.joblib');pred_path=out/(held+'.npy')
        joblib.dump(model,model_path,compress=3);np.save(pred_path,values,allow_pickle=False)
        record=dict(target=target,held=held,training_rows=int(train.sum()),query_rows=int(query.sum()),
            training_stations=sorted(f.loc[train,'station'].unique()),query_stations=sorted(f.loc[query,'station'].unique()),
            training_winters=[2024,2025],features=names,model_sha256=sha(model_path),prediction_sha256=sha(pred_path),
            reference_model_sha256=sha(old_model),seconds=time.perf_counter()-start,network_attempts=0)
        write(out/(held+'.json'),record);fits.append(record);parts.append(p)
        del model,train_x,query_x;gc.collect();pa.default_memory_pool().release_unused()
        print('FIT',len(fits),'/4',held,round(record['seconds'],1),flush=True)
    predictions=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    predictions.to_parquet(out/'predictions.parquet',index=False,compression='zstd')
    # 노면 정답을 읽지 않고 모델·전체 지역 예측을 먼저 저장했다.
    write(out/'weather_prediction_seal.json',dict(at_utc=now(),prediction_sha256=sha(out/'predictions.parquet'),
        source_has_surface_labels=False,new_independent_assessment=False,previously_seen_development_regions=True,
        models={r['held']:r['model_sha256'] for r in fits}))
    observed=predictions.loc[predictions.observed.notna()]
    reports={name:report(observed,name) for name in ['asos','aws_fallback','instant_residual','history_residual']}
    boot=sensitivity(observed,'history_residual','instant_residual',plan['bootstrap'])
    c=reports['history_residual'];b=reports['instant_residual'];g=plan['gates']
    gates=dict(pooled=c['pooled']['mae']<=b['pooled']['mae']*(1-g['minimum_mae_reduction']),
        both_winters=all(c['winters'][y]['mae']<=v['mae']*g['maximum_winter_mae_ratio'] for y,v in b['winters'].items()),
        every_region=all(c['regions'][k]['mae']<=v['mae']*g['maximum_region_mae_ratio'] for k,v in b['regions'].items()),
        cold=c['cold']['mae']<=b['cold']['mae']*g['maximum_cold_mae_ratio'],date_sensitivity=boot['quantiles'][2]<0)
    assert verify_preserved()==temporal['preservation']
    write(out/'summary.json',dict(status='weather_air_history_spatial_complete',reports=reports,bootstrap=boot,
        gates=gates,primary_success=all(gates.values()),fits=fits,prediction_rows=len(predictions),evaluation_rows=len(observed),
        preservation=temporal['preservation'],production_model_changed=False,new_independent_assessment=False,
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
    print('COMPLETE',gates,flush=True)


if __name__=='__main__':main()
