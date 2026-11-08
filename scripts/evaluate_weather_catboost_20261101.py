"""고정 CatBoost12모형과 v10의 1:1평균을 동일 두 검증에서 평가한다."""
import gc
from pathlib import Path
import sys
import time
import catboost
from catboost import CatBoostRegressor
import numpy as np
import pandas as pd
import pyarrow as pa
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,now,verify_preserved
from scripts.evaluate_weather_history_spatial_20261101 import report
from scripts.evaluate_weather_space_time import sensitivity
from src.road_weather_transfer import baselines,balanced_weights
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network


def main():
    cfg=ROOT/'config/weather_catboost_20261101.json';plan=read(cfg);out=ROOT/plan['output'];old=ROOT/plan['baseline']
    audit=read(old/'independent_verification.json');assert audit['status']=='passed' and audit['summary_sha256']==sha(old/'summary.json')
    assert catboost.__version__=='1.2.8' and sha(ROOT/plan['input'])==plan['input_sha256']
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in [cfg,Path(__file__),ROOT/plan['input'],old/'features.parquet',old/'summary.json',ROOT/'src/road_weather_transfer.py']}
    frozen=verify_preserved()
    if out.exists():
        assert read(out/'plan.json')['signatures']==signatures
        if (out/'summary.json').exists():raise FileExistsError('Preserve CatBoost study')
    else:
        out.mkdir(parents=True);write(out/'plan.json',dict(at_utc=now(),settings=plan,signatures=signatures,preservation=frozen,catboost=catboost.__version__))
    f=pd.read_parquet(ROOT/plan['input']).sort_values(['station','time']).reset_index(drop=True)
    assert not set(f.station)&set(plan['blocked_stations']) and not {'ice','road_temp','state_raw'}&set(f)
    asos,base=baselines(f,'relative_humidity');good=np.isfinite(f.relative_humidity)&np.isfinite(asos)&np.isfinite(base)
    fits=[];reports={};groups=sorted(set(f.group)-{'competition'})
    for mode in ['joint','spatial']:
        folder=out/mode;folder.mkdir(exist_ok=True);parts=[]
        original=pd.read_parquet(old/mode/'predictions.parquet').set_index(['station','time'])
        for year in ([2024,2025] if mode=='joint' else [None]):
            for held in groups:
                train=good&f.group.ne(held);query=good&f.group.eq(held)
                if year is not None:train&=f.winter.ne(year);query&=f.winter.eq(year)
                assert not set(f.loc[train,'station'])&set(f.loc[query,'station'])
                p=f.loc[query,['station','time','group','winter']].copy();p['observed']=f.loc[query,'relative_humidity']
                p['cold_input']=np.abs(f.loc[query,'asos_air_temp'])<=3
                p['stable_history']=original.loc[p.set_index(['station','time']).index,'stable_history'].to_numpy()
                stem=held+('_'+str(year) if year is not None else '');model_path=folder/(stem+'.cbm');meta=model_path.with_suffix('.json');pred=model_path.with_suffix('.npy')
                if meta.exists():
                    record=read(meta);assert sha(model_path)==record['model_sha256'] and sha(pred)==record['prediction_sha256']
                    values=np.load(pred,allow_pickle=False)
                else:
                    assert not model_path.exists() and not pred.exists()
                    x=pd.read_parquet(old/'features.parquet');names=list(x);train_x=x.loc[train];query_x=x.loc[query];del x;gc.collect();pa.default_memory_pool().release_unused()
                    model=CatBoostRegressor(**plan['model']);started=time.perf_counter()
                    with deny_network() as attempts,threadpool_limits(limits=2):
                        model.fit(train_x,f.loc[train,'relative_humidity'].to_numpy()-base[train],sample_weight=balanced_weights(f.loc[train]))
                        values=np.clip(model.predict(query_x)+base[query],0,100)
                    assert not attempts and np.isfinite(values).all()
                    model.save_model(str(model_path));np.save(pred,values,allow_pickle=False)
                    record=dict(mode=mode,held=held,query_winter=year,features=names,training_rows=int(train.sum()),query_rows=int(query.sum()),
                        training_stations=sorted(f.loc[train,'station'].unique()),query_stations=sorted(f.loc[query,'station'].unique()),
                        training_winters=sorted(int(y) for y in f.loc[train,'winter'].unique()),
                        model_sha256=sha(model_path),prediction_sha256=sha(pred),seconds=time.perf_counter()-started,network_attempts=0)
                    write(meta,record);del model,train_x,query_x;gc.collect();pa.default_memory_pool().release_unused()
                p['catboost_history']=values;p['half_hgb_catboost']=(p.stable_history.to_numpy()+values)/2
                parts.append(p);fits.append(record);print('CAT FIT',len(fits),'/12',mode,stem,round(record['seconds'],1),flush=True)
        p=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
        p.to_parquet(folder/'predictions.parquet',index=False,compression='zstd')
        baseline=report(p,'stable_history');results={};g=plan['gates']
        for kind in plan['candidates']:
            a=report(p,kind);boot=sensitivity(p,kind,'stable_history',plan['bootstrap'])
            gates=dict(pooled=a['pooled']['mae']<=baseline['pooled']['mae']*(1-g['minimum_mae_reduction']),
                both_winters=all(a['winters'][y]['mae']<=v['mae'] for y,v in baseline['winters'].items()),
                every_region=all(a['regions'][r]['mae']<=v['mae']*g['maximum_region_mae_ratio'] for r,v in baseline['regions'].items()),
                cold=a['cold']['mae']<=baseline['cold']['mae'],date_sensitivity=boot['quantiles'][2]<0)
            results[kind]=dict(metrics=a,bootstrap=boot,gates=gates,primary_success=all(gates.values()))
        reports[mode]=dict(baseline=baseline,candidates=results)
    assert len(fits)==12 and verify_preserved()==frozen
    accepted=[k for k in plan['candidates'] if all(reports[m]['candidates'][k]['primary_success'] for m in reports)]
    write(out/'summary.json',dict(status='weather_catboost_comparison_complete',reports=reports,fits=fits,accepted_candidates=accepted,
        selected_candidate=accepted[0] if accepted else None,production_model_changed=False,new_independent_assessment=False,
        preservation=frozen,files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
    print('CAT COMPLETE',accepted,flush=True)


if __name__=='__main__':main()
