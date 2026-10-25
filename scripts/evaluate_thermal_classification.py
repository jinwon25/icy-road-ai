"""새 열 입력의 결빙 분류·임계값을 지역 이중 제외로 비교한다."""
import argparse
from itertools import combinations
import json
from pathlib import Path
import sys
import time
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.two_winter import validate,curve
from src.thermal_extended import feature_table as thermal_features
from src.solar_memory_search import feature_table as solar_features
from src.submission_runtime import FEATURES
from src.thermal_runtime import EXTRA
from src.runtime_metrics import runtime_daily
from src.extended_comparison import event_retention
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from scripts.evaluate_method_blending import preservation


def read(path):return json.loads(path.read_text('utf-8'))
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')


def available(f):
    return f.asos_air_temp.notna()&f.asos_age_minutes.between(0,60,inclusive='right')&f[['aws_dewpoint','rain15_max_3h','asos_snow_cm']].notna().any(axis=1)


def choose(table,track):
    return table.sort_values([track,'fp','threshold','candidate'],ascending=[False,True,False,True],kind='stable').iloc[0].to_dict()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args();out=args.output
    config=ROOT/'config/thermal_classification_20261024.json';plan=read(config);source=ROOT/plan['data'];baseline_path=ROOT/plan['baseline']
    signatures={str(p.relative_to(ROOT)):sha(p) for p in [config,source,baseline_path,Path(__file__),ROOT/'src/two_winter.py',ROOT/'src/thermal_extended.py',ROOT/'src/solar_memory_search.py',ROOT/'src/combined_thermal_history.py']}
    if out.exists():assert read(out/'plan.json')['signatures']==signatures
    else:out.mkdir(parents=True);write(out/'plan.json',dict(settings=plan,signatures=signatures))
    frozen=preservation()
    columns=list(dict.fromkeys(['station','time','winter','group','ice',*FEATURES,*EXTRA,'asos_solar_altitude_deg','asos_solar_sine_positive']))
    data=validate(pd.read_parquet(source,columns=columns)).sort_values(['station','time']).reset_index(drop=True)
    baseline=validate(pd.read_parquet(baseline_path));assert sha(baseline_path)==read(baseline_path.parent/'audit_runtime.json')['runtime_prediction_sha256']
    groups=sorted(set(data.group)-{'competition'});keys=[*((g,) for g in groups),*combinations(groups,2)]
    xcache={};predictions={};fits=[]
    for spec in plan['candidates']:
        name=spec['name'];kind=spec['features'];folder=out/name;folder.mkdir(exist_ok=True)
        if kind not in xcache:xcache[kind]=thermal_features(data,kind) if kind=='thermal' else solar_features(data,kind)
        x=xcache[kind];predictions[name]={}
        for key in keys:
            stem='__'.join(key);modelpath=folder/(stem+'.joblib');predpath=folder/(stem+'.parquet');record=folder/(stem+'.json')
            query=data.loc[data.group.isin(key)].copy();train=data.loc[~data.group.isin(key)&data.ice.isin([0,1])&available(data)]
            assert not set(train.station)&set(query.station) and set(train.ice)=={0.,1.}
            if record.exists():
                receipt=read(record);assert sha(modelpath)==receipt['model_sha256'] and sha(predpath)==receipt['predictions_sha256'];query=pd.read_parquet(predpath)
            else:
                model=HistGradientBoostingClassifier(**plan['parameters']);started=time.perf_counter()
                with deny_network() as attempts,threadpool_limits(limits=plan['threads']):
                    model.fit(x.loc[train.index],train.ice.to_numpy(int),sample_weight=np.where(train.ice.eq(1),spec['positive_weight'],1.))
                    scores=model.predict_proba(x.loc[query.index])[:,list(model.classes_).index(1)]
                assert not attempts and np.isfinite(scores).all()
                query=query[['station','time','winter','group','ice','asos_air_temp']].copy()
                query['available']=available(data.loc[query.index]);query['score']=scores
                query.to_parquet(predpath,index=False,compression='zstd');joblib.dump(model,modelpath,compress=3)
                receipt=dict(candidate=name,excluded_groups=list(key),training_stations=sorted(train.station.unique()),training_rows=len(train),
                    features=list(x),positive_weight=spec['positive_weight'],parameters=plan['parameters'],model_sha256=sha(modelpath),predictions_sha256=sha(predpath),
                    seconds=time.perf_counter()-started,protected_labels_read=False)
                write(record,receipt);print(name,stem,round(receipt['seconds'],1),flush=True)
            predictions[name][key]=query;fits.append(receipt)
    parts=[];decisions={};spec_names=[s['name'] for s in plan['candidates']]
    for outer in groups:
        tables=[]
        for name in [*spec_names,'asos_zero']:
            store=predictions[spec_names[0] if name=='asos_zero' else name]
            inner=pd.concat([store[tuple(sorted([outer,h]))].loc[lambda f:f.group.eq(h)] for h in groups if h!=outer],ignore_index=True)
            inner.loc[~inner.available,'ice']=np.nan
            scores=inner.asos_air_temp.le(0).to_numpy(float) if name=='asos_zero' else inner.score.to_numpy()
            thresholds=np.array([.5]) if name=='asos_zero' else None
            table=curve(inner,scores) if thresholds is None else curve(inner,scores,thresholds)
            table['mean_f1']=table.f1_fixed_population;winter=[]
            for year in [2024,2025]:
                mask=inner.winter.eq(year).to_numpy()
                t=curve(inner.loc[mask],scores[mask]) if thresholds is None else curve(inner.loc[mask],scores[mask],thresholds)
                winter.append(t.f1_fixed_population.to_numpy())
            table['worst_winter_f1']=np.minimum(*winter);table['candidate']=name;tables.append(table)
        table=pd.concat(tables,ignore_index=True);table.to_csv(out/(outer+'_selection.csv'),index=False);decisions[outer]={}
        query=predictions[spec_names[0]][(outer,)][['station','time','winter','group','ice','asos_air_temp','available']].copy()
        query['asos_zero']=np.where(query.available,query.asos_air_temp.le(0),np.nan)
        for track in plan['selection_tracks']:
            for name in spec_names:
                selected=choose(table.loc[table.candidate.eq(name)],track)
                score=predictions[name][(outer,)].score.to_numpy()
                query[name+'_'+track]=np.where(query.available,score>=selected['threshold'],np.nan)
            selected=choose(table,track);decisions[outer][track]=selected
            score=query.asos_air_temp.le(0).to_numpy(float) if selected['candidate']=='asos_zero' else predictions[selected['candidate']][(outer,)].score.to_numpy()
            query['selected_'+track]=np.where(query.available,score>=selected['threshold'],np.nan)
        parts.append(query)
    f=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(f[['station','time']],baseline[['station','time']])
    np.testing.assert_array_equal(f.available,baseline.physical_both.notna())
    names=['asos_zero',*[n+'_'+t for n in spec_names for t in plan['selection_tracks']],*['selected_'+t for t in plan['selection_tracks']]]
    old,old_st,_=runtime_daily(baseline,baseline.physical_both);reports={}
    for name in names:
        reports[name]={};new_st=None
        for year in ['all',2024,2025]:
            part=f if year=='all' else f.loc[f.winter.eq(year)]
            report,stations,_=runtime_daily(part,part[name]);reports[name][str(year)]=report
            if year=='all':new_st=stations.set_index('station')
        retention,events=event_retention(f,f[name],baseline.physical_both);events.to_csv(out/(name+'_events.csv'),index=False)
        new=reports[name]['all'];old_station=old_st.set_index('station')
        gates=dict(f1_improves=new['f1_fixed_population']>=old['f1_fixed_population']*1.01,
            precision_noninferior=new['precision_available_station_mean'] is not None and new['precision_available_station_mean']>=old['precision_available_station_mean'],
            recall_noninferior=new['recall_available_station_mean'] is not None and new['recall_available_station_mean']>=old['recall_available_station_mean'],
            each_winter=all(reports[name][str(y)]['f1_fixed_population']>=runtime_daily(baseline.loc[baseline.winter.eq(y)],baseline.loc[baseline.winter.eq(y),'physical_both'])[0]['f1_fixed_population'] for y in [2024,2025]),
            each_station=bool((new_st.f1.fillna(0)>=old_station.f1.fillna(0)).all()),events_preserved=retention['lost_events']==0)
        reports[name]['gates']=gates;reports[name]['eligible']=all(gates.values());reports[name]['events']=retention
        print('RESULT',name,new['f1_fixed_population'],gates,flush=True)
    f.to_parquet(out/'predictions.parquet',index=False,compression='zstd');write(out/'decisions.json',decisions)
    assert preservation()==frozen
    write(out/'summary.json',dict(status='thermal_classification_complete',fits=len(fits),reports=reports,protected_labels_read=False,
        new_independent_assessment=False,old_frozen_files=frozen[0],reserved_frozen_files=frozen[1],
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))

if __name__=='__main__':main()
