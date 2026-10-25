"""비보호 두 겨울 확장의 공간 비교. 과거 시간 보류평가를 새 독립 평가로 주장하지 않는다."""
import argparse
from itertools import combinations
import json
from pathlib import Path
import sys
import time
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor,HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.two_winter import validate,history,daily,curve
from src.submission_runtime import FEATURES
from src.award_ice import select_row
from src.temperature_transfer import regression_report
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import preservation

def read(p):return json.loads(p.read_text('utf-8'))
def write(p,d):
    with p.open('x',encoding='utf-8') as f:json.dump(d,f,ensure_ascii=False,indent=2,allow_nan=False)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();out=args.output
    if out.exists():raise FileExistsError('New experiment path required')
    private=ROOT/'outputs/private';source=private/'two_winter_development_20261024_v1'
    receipt=read(source/'receipt.json');assert sha(source/'development.parquet')==receipt['data_sha256']
    data=validate(pd.read_parquet(source/'development.parquet'));data=data.sort_values(['station','time']).reset_index(drop=True)
    plan=read(ROOT/'config/two_winter_development_20261024.json');groups=sorted(set(data.group)-{'competition'})
    frozen=preservation();out.mkdir(parents=True)
    write(out/'plan.json',plan|dict(data_sha256=receipt['data_sha256'],code_sha256=sha(Path(__file__)),library_sha256=sha(ROOT/'src/two_winter.py')))
    x=history(data);cache={};fits=[]
    for key in [*((g,) for g in groups),*combinations(groups,2)]:
        folder=out/'contexts'/'__'.join(key);folder.mkdir(parents=True)
        forbidden=data.group.isin(key);query=data.loc[forbidden].copy();train=data.loc[~forbidden]
        assert not set(train.station)&set(query.station)
        # 온도는 외부 단일 그룹에만 비교하므로 16개 적합. 분류는 10개 중첩 문맥.
        if len(key)==1:
            for scope in ['first','both']:
                sample=train.loc[(train.winter.eq(2024) if scope=='first' else True)&train.road_temp.notna()&train.asos_air_temp.notna()]
                predictions=[]
                for loss,label in [('squared_error','mse'),('absolute_error','mae')]:
                    model=HistGradientBoostingRegressor(loss=loss,**plan['temperature_parameters'])
                    started=time.perf_counter()
                    with threadpool_limits(limits=2):
                        model.fit(sample[list(FEATURES)],sample.road_temp)
                        predicted=model.predict(query[list(FEATURES)])
                    model_path=folder/(scope+'_'+label+'.joblib');joblib.dump(model,model_path,compress=3)
                    predictions.append(predicted)
                    fits.append(dict(context=list(key),scope=scope,kind='temperature',name=label,rows=len(sample),training_stations=sorted(sample.station.unique()),
                        model_sha256=sha(model_path),model_path=str(model_path.relative_to(out)),seconds=time.perf_counter()-started))
                    print('온도 비교',key,scope,label,round(fits[-1]['seconds'],1),flush=True)
                query['temperature_'+scope]=np.where(query.asos_air_temp.notna(),np.mean(predictions,axis=0),np.nan)
        sample=train.loc[train.ice.notna()]
        for label,weight in [('unweighted',1.),('weighted20',20.)]:
            model=HistGradientBoostingClassifier(learning_rate=.05,max_iter=200,max_leaf_nodes=7,min_samples_leaf=300,l2_regularization=20.,early_stopping=False,random_state=20261024)
            started=time.perf_counter()
            with threadpool_limits(limits=2):
                model.fit(x.loc[sample.index],sample.ice.to_numpy(int),sample_weight=np.where(sample.ice.eq(1),weight,1.))
                score=model.predict_proba(x.loc[query.index])[:,list(model.classes_).index(1)]
            model_path=folder/(label+'.joblib');joblib.dump(model,model_path,compress=3);query['score_'+label]=score
            fits.append(dict(context=list(key),scope='both',kind='classification',name=label,rows=len(sample),training_stations=sorted(sample.station.unique()),
                model_sha256=sha(model_path),model_path=str(model_path.relative_to(out)),seconds=time.perf_counter()-started))
            print('두 겨울 분류',key,label,round(fits[-1]['seconds'],1),flush=True)
        query[['station','time','winter','group','ice','road_temp','asos_air_temp',*[c for c in query if c.startswith(('temperature_','score_'))]]].to_parquet(folder/'predictions.parquet',index=False,compression='zstd')
        cache[key]=query
    write(out/'fits.json',fits);parts=[];decisions={}
    for outer in groups:
        inner=pd.concat([cache[tuple(sorted([outer,h]))].loc[lambda f:f.group.eq(h)] for h in groups if h!=outer],ignore_index=True)
        tables=[]
        for name in ['unweighted','weighted20','air_zero']:
            score=inner.asos_air_temp.le(0).to_numpy(float) if name=='air_zero' else inner['score_'+name].to_numpy()
            t=curve(inner,score,np.array([.5])) if name=='air_zero' else curve(inner,score)
            t['candidate']=name;t['smoothing_minutes']=0;tables.append(t)
        table=pd.concat(tables,ignore_index=True);table.to_csv(out/(outer+'_selection.csv'),index=False)
        choice=select_row(table);decisions[outer]=choice
        q=cache[(outer,)].copy();q['pred_asos']=q.asos_air_temp.le(0).astype(int)
        for name in ['unweighted','weighted20']:
            best=select_row(table.loc[table.candidate.eq(name)])
            q['pred_'+name]=q['score_'+name].ge(best['threshold']).astype(int)
        q['pred_selected']=q.pred_asos if choice['candidate']=='air_zero' else q['score_'+choice['candidate']].ge(choice['threshold']).astype(int)
        parts.append(q)
    combined=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    regression={};classification={};dailies=[];stations=[]
    for period in ['all',2024,2025]:
        subset=combined if period=='all' else combined.loc[combined.winter.eq(period)]
        regression[str(period)]={scope:regression_report(subset,subset['temperature_'+scope]) for scope in ['first','both']}
        classification[str(period)]={}
        for name in ['pred_asos','pred_unweighted','pred_weighted20','pred_selected']:
            report,st,d=daily(subset,subset[name]);classification[str(period)][name]=report
            if period=='all':
                st['method']=name;d['method']=name;stations.append(st);dailies.append(d)
    write(out/'decisions.json',decisions);combined.to_parquet(out/'outer_predictions.parquet',index=False,compression='zstd')
    pd.concat(dailies).to_csv(out/'daily.csv',index=False);pd.concat(stations).to_csv(out/'stations.csv',index=False)
    assert preservation()==frozen
    result=dict(status='two_winter_spatial_comparison_complete',regression=regression,classification=classification,new_fits=len(fits),
        rows=len(combined),protected_labels_read=False,new_independent_assessment=False,previous_temporal_holdout_reclassified=True,
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()})
    write(out/'summary.json',result)
    print(json.dumps({'mae':{k:{s:v[s]['pooled']['mae'] for s in v} for k,v in regression.items()},
        'f1':{k:{s:v[s]['f1_fixed_population'] for s in v} for k,v in classification.items()}},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
