"""고정 24모델을 지역 제외 평가한다. 목표 기상값 외의 RWIS 정답은 읽지 않는다."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.road_weather_transfer import (TARGETS, features, baselines, constrain,
    balanced_weights, regression_numbers)
from src.development_resampling import circular_day_indices
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from scripts.evaluate_objective_icing import read,write,verify_preserved


def report(f, column):
    return dict(pooled=regression_numbers(f.observed, f[column]),
        regions={str(k):regression_numbers(q.observed,q[column]) for k,q in f.groupby('group')},
        winters={str(k):regression_numbers(q.observed,q[column]) for k,q in f.groupby('winter')})


def bootstrap(f, candidate, plan):
    """각 겨울의 같은 날짜를 모든 지역에 함께 재표집해 시간 의존을 보존한다."""
    settings=plan['bootstrap']; moments=[]; indices=[]
    for year in [2024,2025]:
        q=f.loc[f.winter.eq(year)].copy();q['date']=q.time.dt.normalize()
        q['difference']=np.abs(q[candidate]-q.observed)-np.abs(q.aws_fallback-q.observed)
        daily=q.groupby('date').agg(difference=('difference','sum'), n=('difference','size'))
        calendar=pd.date_range(f'{year}-11-01',f'{year+1}-02-28',freq='D')
        daily=daily.reindex(calendar,fill_value=0)
        moments.append(daily.to_numpy(float))
        indices.append(circular_day_indices(len(calendar),settings['block_days'],
                       settings['repetitions'],settings['seed']+year-2024))
    total=sum(m[idx].sum(axis=1) for m,idx in zip(moments,indices))
    values=total[:,0]/total[:,1]
    return dict(delta_mae=float((np.abs(f[candidate]-f.observed)-np.abs(f.aws_fallback-f.observed)).mean()),
        quantile025_50_975=np.quantile(values,[.025,.5,.975]).tolist(),
        fraction_improved=float((values<0).mean()),repetitions=len(values),
        interpretation=settings['interpretation']),values


def gates(candidate, baseline, sensitivity, settings):
    return dict(pooled_mae=candidate['pooled']['mae'] <= baseline['pooled']['mae']*(1-settings['minimum_mae_reduction']),
        both_winters=all(candidate['winters'][y]['mae']<=b['mae']*settings['maximum_winter_mae_ratio']
                         for y,b in baseline['winters'].items()),
        every_region=all(candidate['regions'][g]['mae']<=b['mae']*settings['maximum_region_mae_ratio']
                         for g,b in baseline['regions'].items()),
        date_block_upper=sensitivity['quantile025_50_975'][2]<settings['bootstrap_upper_delta_mae'])


def main():
    config=ROOT/'config/road_weather_transfer_20261031.json';plan=read(config)
    out=ROOT/plan['output'];base=ROOT/plan['input_output'];receipt=read(base/'receipt.json')
    assert receipt['status']=='weather_targets_prepared'
    assert sha(base/'development.parquet')==receipt['data_sha256']
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in
        [config,Path(__file__),ROOT/'src/road_weather_transfer.py',base/'development.parquet',base/'receipt.json']}
    frozen=verify_preserved()
    if out.exists(): assert read(out/'plan.json')['signatures']==signatures
    else:
        out.mkdir(parents=True)
        write(out/'plan.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),settings=plan,
            signatures=signatures,preservation=frozen))
    if (out/'summary.json').exists():raise FileExistsError('Preserve completed weather experiment')
    f=pd.read_parquet(base/'development.parquet').sort_values(['station','time']).reset_index(drop=True)
    assert not set(f.station)&set(plan['blocked_stations'])
    assert not {'ice','road_temp','state_raw'}&set(f)
    x=features(f);groups=sorted(set(f.group)-{'competition'});assert len(groups)==4
    cache=out/'features.parquet'
    if cache.exists():pd.testing.assert_frame_equal(pd.read_parquet(cache),x,check_exact=True)
    else:x.to_parquet(cache,index=False,compression='zstd')
    reports={};fits=[];coverage=[]
    for target in TARGETS:
        folder=out/target;folder.mkdir(exist_ok=True)
        asos,nearest=baselines(f,target);target_ok=np.isfinite(f[target].to_numpy(float))
        good=target_ok&np.isfinite(asos)&np.isfinite(nearest)
        parts=[]
        for held in groups:
            train=f.loc[f.group.ne(held)&good];query=f.loc[f.group.eq(held)&good]
            assert len(query)>0 and not set(train.station)&set(query.station)
            result=query[['station','time','group','winter']].copy()
            result['observed']=query[target];result['asos']=asos[query.index];result['aws_fallback']=nearest[query.index]
            for candidate in plan['candidates']:
                stem=candidate+'_'+held;modelpath=folder/(stem+'.joblib');metapath=folder/(stem+'.json');predpath=folder/(stem+'.npy')
                if metapath.exists():
                    record=read(metapath)
                    assert sha(modelpath)==record['model_sha256'] and sha(predpath)==record['prediction_sha256']
                    predicted=np.load(predpath)
                else:
                    if modelpath.exists() or predpath.exists():raise FileExistsError('Unrecorded fit; inspect before resuming')
                    y=train[target].to_numpy()
                    if candidate=='residual_hgb':y=y-nearest[train.index]
                    started=time.perf_counter();model=HistGradientBoostingRegressor(**plan['model'])
                    with deny_network() as attempts,threadpool_limits(limits=2):
                        model.fit(x.loc[train.index],y,sample_weight=balanced_weights(train))
                        predicted=model.predict(x.loc[query.index])
                    if candidate=='residual_hgb':predicted=predicted+nearest[query.index]
                    predicted=constrain(predicted,target)
                    assert not attempts and np.isfinite(predicted).all()
                    joblib.dump(model,modelpath,compress=3);np.save(predpath,predicted,allow_pickle=False)
                    record=dict(target=target,candidate=candidate,held=held,training_rows=len(train),query_rows=len(query),
                        training_stations=sorted(train.station.unique()),query_stations=sorted(query.station.unique()),
                        features=list(x),model_parameters=model.get_params(),seconds=time.perf_counter()-started,
                        model_sha256=sha(modelpath),prediction_sha256=sha(predpath),network_attempts=0)
                    write(metapath,record)
                fits.append(record);result[candidate]=predicted
                print('FIT',len(fits),'/24',target,candidate,held,round(record['seconds'],1),flush=True)
            parts.append(result)
            q=f.loc[f.group.eq(held)]
            coverage.append(dict(target=target,group=held,existing_input_rows=len(q),target_valid_rows=int(target_ok[q.index].sum()),
                common_evaluation_rows=len(query),observed_stations=sorted(query.station.unique())))
        predictions=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
        predictions.to_parquet(folder/'predictions.parquet',index=False,compression='zstd')
        outputs={c:report(predictions,c) for c in ['asos','aws_fallback']+plan['candidates']}
        sensitivities={};decisions={}
        for c in plan['candidates']:
            sensitivity,samples=bootstrap(predictions,c,plan);sensitivities[c]=sensitivity
            np.save(folder/(c+'_bootstrap.npy'),samples,allow_pickle=False)
            decisions[c]=gates(outputs[c],outputs['aws_fallback'],sensitivity,plan['primary_gates'])
        primary=plan['primary_candidate']
        result=dict(metrics=outputs,bootstrap=sensitivities,gates=decisions,
                    primary_success=all(decisions[primary].values()),n=len(predictions))
        write(folder/'report.json',result);reports[target]=result
        print('RESULT',target,{c:round(v['pooled']['mae'],6) for c,v in outputs.items()},decisions,flush=True)
    pd.DataFrame(coverage).to_csv(out/'coverage.csv',index=False,encoding='utf-8-sig')
    assert verify_preserved()==frozen
    summary=dict(status='road_weather_transfer_complete',reports=reports,fits=fits,features=list(x),
        production_model_changed=False,new_independent_assessment=False,
        successful_primary_targets=[t for t,r in reports.items() if r['primary_success']],preservation=frozen,
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()})
    write(out/'summary.json',summary)
    print('COMPLETE',summary['successful_primary_targets'],flush=True)


if __name__=='__main__':main()
