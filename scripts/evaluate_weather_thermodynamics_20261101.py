"""고정 물리 입력과 두 출력 방식의 24적합. 현재 v10과 두 제외 검증을 직접 비교한다."""
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
from src.road_weather_transfer import baselines,balanced_weights
from src.weather_thermodynamics import thermodynamic_features,transformed_target,inverse_target
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network


def checks(candidate,baseline,boot,gates):
    return dict(pooled=candidate['pooled']['mae']<=baseline['pooled']['mae']*(1-gates['minimum_mae_reduction']),
        both_winters=all(candidate['winters'][y]['mae']<=v['mae']*gates['maximum_winter_mae_ratio'] for y,v in baseline['winters'].items()),
        every_region=all(candidate['regions'][r]['mae']<=v['mae']*gates['maximum_region_mae_ratio'] for r,v in baseline['regions'].items()),
        cold=candidate['cold']['mae']<=baseline['cold']['mae']*gates['maximum_cold_mae_ratio'],
        date_sensitivity=boot['quantiles'][2]<0)


def main():
    config=ROOT/'config/weather_thermodynamics_20261101.json';plan=read(config)
    out=ROOT/plan['output'];old=ROOT/plan['baseline']
    prior=read(old/'summary.json');audit=read(old/'independent_verification.json')
    assert audit['status']=='passed' and audit['summary_sha256']==sha(old/'summary.json')
    assert sha(ROOT/plan['input'])==plan['input_sha256']
    inputs=[config,Path(__file__),ROOT/plan['input'],ROOT/'src/weather_thermodynamics.py',
        ROOT/'src/weather_history_stable.py',ROOT/'src/road_weather_transfer.py',old/'summary.json',old/'features.parquet']
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in inputs};frozen=verify_preserved()
    if out.exists():
        assert read(out/'plan.json')['signatures']==signatures
        if (out/'summary.json').exists():raise FileExistsError('Preserve completed thermodynamic study')
    else:
        out.mkdir(parents=True);write(out/'plan.json',dict(at_utc=now(),settings=plan,signatures=signatures,preservation=frozen))
    f=pd.read_parquet(ROOT/plan['input']).sort_values(['station','time']).reset_index(drop=True)
    assert not set(f.station)&set(plan['blocked_stations']) and not {'ice','road_temp','state_raw'}&set(f)
    cache=out/'features.parquet';proof=out/'feature_receipt.json'
    if proof.exists():assert sha(cache)==read(proof)['sha256']
    else:
        if cache.exists():raise FileExistsError('Unrecorded physical features')
        history=pd.read_parquet(old/'features.parquet');x=thermodynamic_features(f,history)
        pd.testing.assert_frame_equal(x.iloc[:,:82],history,check_exact=True)
        x.to_parquet(cache,index=False,compression='zstd')
        write(proof,dict(sha256=sha(cache),shape=list(x.shape),columns=list(x),baseline_82_columns_preserved=True))
        del x,history;gc.collect();pa.default_memory_pool().release_unused()
    asos,nearest=baselines(f,'relative_humidity')
    good=np.isfinite(f.relative_humidity)&np.isfinite(asos)&np.isfinite(nearest)
    fits=[];reports={};groups=sorted(set(f.group)-{'competition'})
    assert len(groups)==4
    for mode in ['joint','spatial']:
        folder=out/mode;folder.mkdir(exist_ok=True);parts=[]
        old_predictions=pd.read_parquet(old/mode/'predictions.parquet').set_index(['station','time'])
        for year in ([2024,2025] if mode=='joint' else [None]):
            for held in groups:
                train=good&f.group.ne(held);query=good&f.group.eq(held)
                if year is not None:train&=f.winter.ne(year);query&=f.winter.eq(year)
                assert not set(f.loc[train,'station'])&set(f.loc[query,'station'])
                p=f.loc[query,['station','time','group','winter']].copy()
                aligned=old_predictions.loc[p.set_index(['station','time']).index]
                np.testing.assert_array_equal(f.loc[query,'relative_humidity'],aligned.observed)
                p['observed']=f.loc[query,'relative_humidity'];p['cold_input']=np.abs(f.loc[query,'asos_air_temp'])<=3
                p['stable_history']=aligned.stable_history.to_numpy()
                x=pd.read_parquet(cache);names=list(x);train_x=x.loc[train];query_x=x.loc[query]
                del x;gc.collect();pa.default_memory_pool().release_unused()
                for kind in plan['candidates']:
                    stem=held+('_'+str(year) if year is not None else '')+'__'+kind
                    path=folder/(stem+'.joblib');meta=path.with_suffix('.json');pred=path.with_suffix('.npy')
                    if meta.exists():
                        record=read(meta);assert sha(path)==record['model_sha256'] and sha(pred)==record['prediction_sha256']
                        values=np.load(pred,allow_pickle=False)
                    else:
                        assert not path.exists() and not pred.exists()
                        target,jacobian=transformed_target(f.loc[train,'relative_humidity'],nearest[train],kind)
                        weight=balanced_weights(f.loc[train])*jacobian
                        if kind=='thermo_logit':weight/=weight.mean()
                        model=HistGradientBoostingRegressor(**plan['model']);started=time.perf_counter()
                        with deny_network() as attempts,threadpool_limits(limits=2):
                            model.fit(train_x,target,sample_weight=weight)
                            values=inverse_target(model.predict(query_x),nearest[query],kind)
                        assert not attempts and np.isfinite(values).all()
                        joblib.dump(model,path,compress=3);np.save(pred,values,allow_pickle=False)
                        record=dict(mode=mode,kind=kind,held=held,query_winter=year,features=names,
                            training_rows=int(train.sum()),query_rows=int(query.sum()),
                            training_stations=sorted(f.loc[train,'station'].unique()),query_stations=sorted(f.loc[query,'station'].unique()),
                            training_winters=sorted(int(y) for y in f.loc[train,'winter'].unique()),
                            model_sha256=sha(path),prediction_sha256=sha(pred),seconds=time.perf_counter()-started,network_attempts=0)
                        write(meta,record);del model;gc.collect()
                    p[kind]=values;fits.append(record)
                    print('FIT',len(fits),'/24',mode,stem,round(record['seconds'],1),flush=True)
                parts.append(p);del train_x,query_x;gc.collect();pa.default_memory_pool().release_unused()
        p=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
        assert not p.duplicated(['station','time']).any()
        p.to_parquet(folder/'predictions.parquet',index=False,compression='zstd')
        metrics={c:report(p,c) for c in ['stable_history',*plan['candidates']]}
        results={}
        for kind in plan['candidates']:
            boot=sensitivity(p,kind,'stable_history',plan['bootstrap'])
            gates=checks(metrics[kind],metrics['stable_history'],boot,plan['gates'])
            results[kind]=dict(metrics=metrics[kind],bootstrap=boot,gates=gates,primary_success=all(gates.values()))
        reports[mode]=dict(baseline=metrics['stable_history'],candidates=results)
    assert len(fits)==24 and verify_preserved()==frozen
    accepted=[k for k in plan['candidates'] if all(reports[m]['candidates'][k]['primary_success'] for m in reports)]
    write(out/'summary.json',dict(status='weather_thermodynamic_comparison_complete',reports=reports,fits=fits,
        accepted_candidates=accepted,selected_candidate=accepted[0] if accepted else None,
        production_model_changed=False,new_independent_assessment=False,preservation=frozen,
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
    print('COMPLETE',accepted,flush=True)


if __name__=='__main__':main()
