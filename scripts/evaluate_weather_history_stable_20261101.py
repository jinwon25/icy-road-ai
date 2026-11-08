"""수치 안정성을 수정한 같은 습도 이력을 8+4회 재적합한다. 설정·게이트 불변."""
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
from scripts.evaluate_weather_history_spatial_20261101 import report
from scripts.evaluate_weather_space_time import sensitivity
from src.weather_history_stable import stable_temporal_features
from src.road_weather_transfer import baselines,balanced_weights,constrain,features
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network


def prepare(out,f,old):
    cache=out/'features.parquet';proof=out/'numeric_equivalence.json'
    if proof.exists():
        record=read(proof);assert sha(cache)==record['feature_sha256'];return
    if cache.exists():raise FileExistsError('Unrecorded stable feature cache')
    _,x=stable_temporal_features(f)
    q=f.loc[f.station.isin(['12207','23205','33205'])&f.time.ge(pd.Timestamp('2024-12-14'))&f.time.lt(pd.Timestamp('2024-12-16'))]
    _,small=stable_temporal_features(q.reset_index(drop=True))
    select=q.time.ge(pd.Timestamp('2024-12-15')).to_numpy()
    pd.testing.assert_frame_equal(x.loc[q.index[select]].reset_index(drop=True),
        small.loc[select].reset_index(drop=True),check_exact=True)
    count=int(select.sum())*len(x.columns)
    x.to_parquet(cache,index=False,compression='zstd');del x;gc.collect()
    maximum=0.;checked=0
    for hours in [3,24]:
        # 별도 시간 창 연산으로 작성된 과거 캐시와 수학적 동일성을 전량 비교한다.
        from src.weather_temporal import HISTORY_FIELDS
        columns=[f'{field}_{kind}_{hours}h' for field in HISTORY_FIELDS for kind in ['mean','departure','coverage']]
        a=pd.read_parquet(old/'history_residual_features.parquet',columns=columns)
        b=pd.read_parquet(cache,columns=columns)
        pd.testing.assert_frame_equal(a,b,atol=2e-8,rtol=1e-9,check_exact=False)
        maximum=max(maximum,float(np.nanmax(np.abs(a.to_numpy()-b.to_numpy()))));checked+=a.size
        del a,b;gc.collect();pa.default_memory_pool().release_unused()
    write(proof,dict(feature_sha256=sha(cache),mathematically_equivalent_values=checked,
        maximum_absolute_feature_difference=maximum,prefix_bit_exact_feature_values=count,
        numeric_policy='independent fixed-length local sums, no prefix state, no rounding'))
    print('STABLE FEATURES',checked,'prefix exact',count,'max difference',maximum,flush=True)


def main():
    config=ROOT/'config/weather_humidity_stable_20261101.json';plan=read(config)
    out=ROOT/plan['output'];old=ROOT/plan['old_temporal'];baseline=ROOT/plan['old_spatial_baseline']
    old_summary=read(old/'summary.json');old_audit=read(old/'independent_verification.json')
    assert old_audit['status']=='passed' and old_audit['summary_sha256']==sha(old/'summary.json')
    assert sha(ROOT/plan['input'])==plan['input_sha256']
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in [config,Path(__file__),
        ROOT/'src/weather_history_stable.py',ROOT/'src/weather_temporal.py',ROOT/'src/road_weather_transfer.py',
        ROOT/plan['input'],old/'summary.json',baseline/'summary.json']}
    if out.exists():
        assert read(out/'plan.json')['signatures']==signatures
        if (out/'summary.json').exists():raise FileExistsError('Preserve completed stable study')
    else:
        out.mkdir(parents=True);write(out/'plan.json',dict(at_utc=now(),settings=plan,signatures=signatures,
            preservation=old_summary['preservation']))
    f=pd.read_parquet(ROOT/plan['input']).sort_values(['station','time']).reset_index(drop=True)
    assert not set(f.station)&set(plan['blocked_stations']) and not {'ice','road_temp','state_raw'}&set(f)
    prepare(out,f,old)
    asos,nearest=baselines(f,'relative_humidity');good=np.isfinite(f.relative_humidity)&np.isfinite(asos)&np.isfinite(nearest)
    groups=sorted(set(f.group)-{'competition'});fits=[];reports={}
    for mode in ['joint','spatial']:
        folder=out/mode;folder.mkdir(exist_ok=True);parts=[]
        for year in ([2024,2025] if mode=='joint' else [None]):
            for held in groups:
                train=good&f.group.ne(held);query=good&f.group.eq(held)
                if year is not None:train&=f.winter.ne(year);query&=f.winter.eq(year)
                assert not set(f.loc[train,'station'])&set(f.loc[query,'station'])
                stem=held+('_'+str(year) if year is not None else '')
                reference=(old/'relative_humidity'/('instant_residual_'+stem+'.joblib')) if mode=='joint' else \
                    baseline/'relative_humidity'/('residual_hgb_'+held+'.joblib')
                reference_meta=read(reference.with_suffix('.json'));assert sha(reference)==reference_meta['model_sha256']
                current=joblib.load(reference);p=f.loc[query,['station','time','group','winter']].copy()
                p['observed']=f.loc[query,'relative_humidity'];p['asos']=asos[query];p['aws_fallback']=nearest[query]
                p['cold_input']=np.abs(f.loc[query,'asos_air_temp'])<=3
                with deny_network() as attempts,threadpool_limits(limits=2):
                    original=constrain(current.predict(features(f.loc[query]))+nearest[query],'relative_humidity')
                assert not attempts
                np.testing.assert_array_equal(original,np.load(reference.with_suffix('.npy'),allow_pickle=False))
                p['instant_residual']=original;del current
                model_path=folder/(stem+'.joblib');meta_path=folder/(stem+'.json');pred_path=folder/(stem+'.npy')
                if meta_path.exists():
                    record=read(meta_path)
                    assert sha(model_path)==record['model_sha256'] and sha(pred_path)==record['prediction_sha256']
                    predicted=np.load(pred_path,allow_pickle=False)
                else:
                    if model_path.exists() or pred_path.exists():raise FileExistsError('Unrecorded stable fit')
                    x=pd.read_parquet(out/'features.parquet');names=list(x)
                    train_x=x.loc[train];query_x=x.loc[query];del x;gc.collect();pa.default_memory_pool().release_unused()
                    start=time.perf_counter();model=HistGradientBoostingRegressor(**plan['model'])
                    with deny_network() as attempts,threadpool_limits(limits=2):
                        model.fit(train_x,f.loc[train,'relative_humidity'].to_numpy()-nearest[train],sample_weight=balanced_weights(f.loc[train]))
                        predicted=constrain(model.predict(query_x)+nearest[query],'relative_humidity')
                    assert not attempts and np.isfinite(predicted).all()
                    joblib.dump(model,model_path,compress=3);np.save(pred_path,predicted,allow_pickle=False)
                    record=dict(mode=mode,held=held,query_winter=year,training_rows=int(train.sum()),query_rows=int(query.sum()),
                        training_stations=sorted(f.loc[train,'station'].unique()),query_stations=sorted(f.loc[query,'station'].unique()),
                        training_winters=sorted(int(y) for y in f.loc[train,'winter'].unique()),features=names,
                        reference_model=reference.relative_to(ROOT).as_posix(),reference_model_sha256=sha(reference),
                        model_sha256=sha(model_path),prediction_sha256=sha(pred_path),seconds=time.perf_counter()-start,network_attempts=0)
                    write(meta_path,record);del model,train_x,query_x;gc.collect();pa.default_memory_pool().release_unused()
                fits.append(record);p['stable_history']=predicted;parts.append(p)
                print('FIT',len(fits),'/12',mode,held,year,round(record['seconds'],1),flush=True)
        p=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
        assert not p.duplicated(['station','time']).any()
        p.to_parquet(folder/'predictions.parquet',index=False,compression='zstd')
        metrics={c:report(p,c) for c in ['asos','aws_fallback','instant_residual','stable_history']}
        boot=sensitivity(p,'stable_history','instant_residual',plan['bootstrap'])
        c=metrics['stable_history'];b=metrics['instant_residual'];g=plan['gates']
        gates=dict(pooled=c['pooled']['mae']<=b['pooled']['mae']*(1-g['minimum_mae_reduction']),
            both_winters=all(c['winters'][y]['mae']<=v['mae']*g['maximum_winter_mae_ratio'] for y,v in b['winters'].items()),
            every_region=all(c['regions'][k]['mae']<=v['mae']*g['maximum_region_mae_ratio'] for k,v in b['regions'].items()),
            cold=c['cold']['mae']<=b['cold']['mae']*g['maximum_cold_mae_ratio'],date_sensitivity=boot['quantiles'][2]<0)
        reports[mode]=dict(metrics=metrics,bootstrap=boot,gates=gates,primary_success=all(gates.values()))
    assert len(fits)==12 and verify_preserved()==old_summary['preservation']
    write(out/'summary.json',dict(status='stable_humidity_history_complete',reports=reports,fits=fits,
        primary_success=all(r['primary_success'] for r in reports.values()),preservation=old_summary['preservation'],
        production_model_changed=False,new_independent_assessment=False,
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
    print('COMPLETE',{k:v['gates'] for k,v in reports.items()},flush=True)


if __name__=='__main__':main()
