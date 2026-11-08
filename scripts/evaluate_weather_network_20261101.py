"""AWS 공간 정보 35특성을 추가한 고정 36적합. 결과로 설정을 재탐색하지 않는다."""
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
from src.weather_network import FIELDS,WeatherNetwork
from src.road_weather_transfer import features,baselines,constrain,balanced_weights,SOURCE_FIELDS
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network


def network_sources(plan):
    source=ROOT/plan['weather_sources']
    aws=pd.read_parquet(source/'aws.parquet',columns=['station','source_time',*FIELDS])
    c=pd.read_csv(source/'weather_coordinates.csv',dtype={'station_id':str})
    c=c.loc[c.kind.eq('AWS')].rename(columns={'station_id':'station','latitudes':'lat','longitudes':'lon'})
    c[['lat','lon']]=c[['lat','lon']].astype(float)
    coordinates=pd.read_csv(ROOT/plan['target_coordinates'],dtype={'station':str})
    coordinates=coordinates.set_index('station')[['requested_lat','requested_lon']]
    return aws,c.set_index('station')[['lat','lon']],coordinates


def prepare(plan,out,f):
    cache=out/'network_features.parquet';proof=out/'network_receipt.json'
    if proof.exists():
        assert sha(cache)==read(proof)['feature_sha256'];return
    if cache.exists():raise FileExistsError('Unrecorded feature cache')
    aws,coordinates,target_coords=network_sources(plan)
    builder=WeatherNetwork(aws,coordinates,**plan['network']);parts=[];mapping={};checks=0
    for station,q in f.groupby('station',sort=True):
        lat,lon=target_coords.loc[station]
        with deny_network() as attempts:
            x,m=builder.build(q.time,lat,lon,q)
        assert not attempts
        x.index=q.index;parts.append(x);mapping[station]=m
        if station in ['12207','23205','33205']:
            selection=q.time.ge('2024-12-15')&q.time.lt('2024-12-16')
            small,_=builder.build(q.loc[selection,'time'],lat,lon,q.loc[selection])
            pd.testing.assert_frame_equal(x.loc[selection].reset_index(drop=True),small,check_exact=True)
            checks+=small.size
    combined=pd.concat(parts).sort_index()
    assert combined.index.equals(f.index) and combined.shape==(len(f),35)
    combined.to_parquet(cache,index=False,compression='zstd')
    quality=pd.concat([f[['station','time','winter']],combined],axis=1)
    quality['date']=quality.time.dt.normalize()
    cols=[c for c in combined if c.endswith(('_count','_distance_km','_effective_n','_range'))]
    quality.groupby(['station','winter'])[cols].mean().to_csv(out/'network_quality.csv',encoding='utf-8-sig')
    write(proof,dict(status='network_features_prepared',rows=len(f),columns=list(combined),
        feature_sha256=sha(cache),prefix_exact_values=checks,mapping=mapping,
        target_columns_read=False,protected_outcomes_read=False,network_attempts=0))
    print('FEATURES',combined.shape,'prefix exact',checks,flush=True)


def reference_path(plan,target,mode,stem):
    if target=='relative_humidity':return ROOT/plan['stable_history']/mode/(stem+'.joblib')
    if mode=='spatial':return ROOT/plan['spatial_baseline']/target/('residual_hgb_'+stem+'.joblib')
    return ROOT/plan['joint_baseline']/target/('instant_residual_'+stem+'.joblib')


def main():
    config=ROOT/'config/weather_network_20261101.json';plan=read(config);out=ROOT/plan['output']
    assert sha(ROOT/plan['input'])==plan['input_sha256']
    required=[config,Path(__file__),ROOT/'src/weather_network.py',ROOT/'src/road_weather_transfer.py',
        ROOT/plan['input'],ROOT/plan['target_coordinates'],
        ROOT/plan['weather_sources']/'aws.parquet',ROOT/plan['weather_sources']/'weather_coordinates.csv']
    for key in ['stable_history','spatial_baseline','joint_baseline']:
        folder=ROOT/plan[key];summary=read(folder/'summary.json');audit=read(folder/'independent_verification.json')
        assert audit['status']=='passed' and audit['summary_sha256']==sha(folder/'summary.json')
        required.extend([folder/'summary.json',folder/'independent_verification.json'])
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in required}
    frozen=verify_preserved()
    if out.exists():
        assert read(out/'plan.json')['signatures']==signatures
        if (out/'summary.json').exists():raise FileExistsError('Preserve completed network experiment')
    else:
        out.mkdir(parents=True);write(out/'plan.json',dict(at_utc=now(),settings=plan,signatures=signatures,preservation=frozen))
    f=pd.read_parquet(ROOT/plan['input']).sort_values(['station','time']).reset_index(drop=True)
    assert not set(f.station)&set(plan['blocked_stations']) and not {'ice','road_temp','state_raw'}&set(f)
    prepare(plan,out,f);network=pd.read_parquet(out/'network_features.parquet')
    groups=sorted(set(f.group)-{'competition'});assert len(groups)==4
    all_reports={};fits=[]
    for target in plan['targets']:
        if target=='relative_humidity':x=pd.read_parquet(ROOT/plan['stable_history']/'features.parquet')
        else:x=features(f)
        current_x=x;augmented=pd.concat([x,network],axis=1)
        asos,nearest=baselines(f,target)
        valid=np.isfinite(f[target])&np.isfinite(asos)&np.isfinite(nearest)
        all_reports[target]={}
        for mode in ['joint','spatial']:
            folder=out/target/mode;folder.mkdir(parents=True,exist_ok=True);parts=[]
            for year in ([2024,2025] if mode=='joint' else [None]):
                for held in groups:
                    train=valid&f.group.ne(held);query=valid&f.group.eq(held)
                    if year is not None:train&=f.winter.ne(year);query&=f.winter.eq(year)
                    assert not set(f.loc[train,'station'])&set(f.loc[query,'station'])
                    stem=held+('_'+str(year) if year is not None else '')
                    reference=reference_path(plan,target,mode,stem);reference_meta=read(reference.with_suffix('.json'))
                    assert sha(reference)==reference_meta['model_sha256']
                    baseline_model=joblib.load(reference)
                    with deny_network() as attempts,threadpool_limits(limits=2):
                        existing=constrain(baseline_model.predict(current_x.loc[query])+nearest[query],target)
                    assert not attempts
                    np.testing.assert_array_equal(existing,np.load(reference.with_suffix('.npy'),allow_pickle=False))
                    del baseline_model
                    p=f.loc[query,['station','time','group','winter']].copy()
                    p['observed']=f.loc[query,target];p['asos']=asos[query];p['aws_fallback']=nearest[query]
                    p['cold_input']=np.abs(f.loc[query,'asos_air_temp'])<=3;p['current']=existing
                    idw=network.loc[query,'network_'+SOURCE_FIELDS[target]+'_idw'].to_numpy()
                    p['idw_only']=constrain(np.where(np.isfinite(idw),idw,nearest[query]),target)
                    model_path=folder/(stem+'.joblib');meta_path=model_path.with_suffix('.json');pred_path=model_path.with_suffix('.npy')
                    if meta_path.exists():
                        record=read(meta_path)
                        assert sha(model_path)==record['model_sha256'] and sha(pred_path)==record['prediction_sha256']
                        predicted=np.load(pred_path,allow_pickle=False)
                    else:
                        if model_path.exists() or pred_path.exists():raise FileExistsError('Unrecorded model output')
                        started=time.perf_counter();model=HistGradientBoostingRegressor(**plan['model'])
                        with deny_network() as attempts,threadpool_limits(limits=2):
                            model.fit(augmented.loc[train],f.loc[train,target].to_numpy()-nearest[train],sample_weight=balanced_weights(f.loc[train]))
                            predicted=constrain(model.predict(augmented.loc[query])+nearest[query],target)
                        assert not attempts and np.isfinite(predicted).all()
                        joblib.dump(model,model_path,compress=3);np.save(pred_path,predicted,allow_pickle=False)
                        record=dict(target=target,mode=mode,held=held,query_winter=year,training_rows=int(train.sum()),
                            query_rows=int(query.sum()),training_stations=sorted(f.loc[train,'station'].unique()),
                            training_winters=sorted(int(v) for v in f.loc[train,'winter'].unique()),query_stations=sorted(f.loc[query,'station'].unique()),
                            features=list(augmented),reference_model=reference.relative_to(ROOT).as_posix(),reference_model_sha256=sha(reference),
                            model_sha256=sha(model_path),prediction_sha256=sha(pred_path),seconds=time.perf_counter()-started,network_attempts=0)
                        write(meta_path,record);del model;gc.collect();pa.default_memory_pool().release_unused()
                    fits.append(record);p['network_residual']=predicted;parts.append(p)
                    print('FIT',len(fits),'/36',target,mode,held,year,round(record['seconds'],1),flush=True)
            p=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
            assert not p.duplicated(['station','time']).any()
            p.to_parquet(folder/'predictions.parquet',index=False,compression='zstd')
            measures={c:report(p,c) for c in ['asos','aws_fallback','current','idw_only','network_residual']}
            boot=sensitivity(p,'network_residual','current',plan['bootstrap'])
            c=measures['network_residual'];b=measures['current'];g=plan['gates']
            gates=dict(pooled=c['pooled']['mae']<=b['pooled']['mae']*(1-g['minimum_mae_reduction']),
                both_winters=all(c['winters'][y]['mae']<=v['mae']*g['maximum_winter_mae_ratio'] for y,v in b['winters'].items()),
                every_region=all(c['regions'][r]['mae']<=v['mae']*g['maximum_region_mae_ratio'] for r,v in b['regions'].items()),
                cold=c['cold']['mae']<=b['cold']['mae']*g['maximum_cold_mae_ratio'],date_sensitivity=boot['quantiles'][2]<0)
            all_reports[target][mode]=dict(metrics=measures,bootstrap=boot,gates=gates,primary_success=all(gates.values()))
            print('REPORT',target,mode,b['pooled']['mae'],c['pooled']['mae'],gates,flush=True)
        del x,current_x,augmented;gc.collect();pa.default_memory_pool().release_unused()
    assert len(fits)==36 and verify_preserved()==frozen
    write(out/'summary.json',dict(status='weather_network_complete',reports=all_reports,fits=fits,
        accepted_targets=[t for t,modes in all_reports.items() if all(r['primary_success'] for r in modes.values())],
        preservation=frozen,production_model_changed=False,new_independent_assessment=False,
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
    print('COMPLETE',flush=True)


if __name__=='__main__':main()
