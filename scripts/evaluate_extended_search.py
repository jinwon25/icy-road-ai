"""두 겨울 4지역 제외 회귀 비교. 중단 후 완료 문맥의 해시를 확인해 재개한다."""
import argparse
from datetime import datetime,timezone
from importlib.metadata import version
import json
from pathlib import Path
import sys
import time
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.extended_search import feature_table,estimator,weights,temperature_gate
from src.two_winter import validate
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from scripts.evaluate_method_blending import preservation

def read(p):return json.loads(p.read_text('utf-8'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,default=ROOT/'config/extended_search_20261024.json')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--candidate',action='append')
    args=parser.parse_args();plan=read(args.config);out=args.output
    signatures=dict(config=sha(args.config),code=sha(Path(__file__)),library=sha(ROOT/'src/extended_search.py'),data=sha(ROOT/plan['data']))
    if out.exists():assert read(out/'plan.json')['signatures']==signatures
    else:
        out.mkdir(parents=True);write(out/'plan.json',dict(settings=plan,signatures=signatures,started=datetime.now(timezone.utc).isoformat(),
            versions={p:version(p) for p in ['scikit-learn','lightgbm','xgboost','catboost','pandas','numpy']}))
    frozen=preservation()
    data=validate(pd.read_parquet(ROOT/plan['data'])).sort_values(['station','time']).reset_index(drop=True)
    source=ROOT/plan['baseline'];baseline=validate(pd.read_parquet(source))
    assert sha(source)==read(source.parent/'audit_runtime.json')['runtime_prediction_sha256']
    groups=sorted(set(data.group)-{'competition'});features={};results={}
    specs=[s for s in plan['candidates'] if args.candidate is None or s['name'] in args.candidate]
    for spec in specs:
        name=spec['name'];folder=out/name;folder.mkdir(exist_ok=True);kind=spec.get('features','weather')
        if kind not in features:features[kind]=feature_table(data,kind)
        x=features[kind];parts=[];fit_receipts=[]
        for group in groups:
            record=folder/(group+'.json');predfile=folder/(group+'.parquet');modelpath=folder/(group+'.joblib')
            query=data.loc[data.group.eq(group)];train=data.loc[~data.group.eq(group)&data.road_temp.notna()&data.asos_air_temp.notna()]
            if record.exists():
                r=read(record);assert sha(predfile)==r['prediction_sha256'] and sha(modelpath)==r['model_sha256']
                p=pd.read_parquet(predfile)
            else:
                assert not set(train.station)&set(query.station)
                model=estimator(spec,plan['seed'],plan['threads']);target=train.road_temp.to_numpy()
                if spec.get('residual'):target=target-train.asos_air_temp.to_numpy()
                t=time.perf_counter()
                with deny_network() as attempts,threadpool_limits(limits=plan['threads']):
                    model.fit(x.loc[train.index],target,sample_weight=weights(train,spec))
                    predicted=model.predict(x.loc[query.index])
                assert not attempts and np.isfinite(predicted).all()
                if spec.get('residual'):predicted=predicted+query.asos_air_temp.to_numpy()
                predicted=np.where(query.asos_air_temp.notna(),predicted,np.nan)
                p=query[['station','time','group','winter','ice','road_temp','asos_air_temp']].copy();p['prediction']=predicted
                p.to_parquet(predfile,index=False,compression='zstd');joblib.dump(model,modelpath,compress=3)
                r=dict(candidate=name,group=group,training_stations=sorted(train.station.unique()),training_rows=len(train),
                    features=list(x),parameters=model.get_params(),model_sha256=sha(modelpath),prediction_sha256=sha(predfile),
                    seconds=time.perf_counter()-t,protected_labels_read=False)
                write(record,r);print(name,group,round(r['seconds'],1),flush=True)
            parts.append(p);fit_receipts.append(r)
        combined=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
        pd.testing.assert_frame_equal(combined[['station','time']],baseline[['station','time']],check_exact=True)
        report=temperature_gate(combined,combined.prediction,baseline.temperature_both,plan['temperature_gate'])
        report['fits']=fit_receipts;report['baseline_sha256']=sha(source)
        combined.to_parquet(folder/'predictions.parquet',index=False,compression='zstd');write(folder/'report.json',report)
        results[name]=report
        print('RESULT',name,round(report['regression']['pooled']['mae'],6),report['gates'],flush=True)
    assert preservation()==frozen
    summaries={p.parent.name:read(p) for p in out.glob('*/report.json')}
    write(out/'summary.json',dict(status='extended_search_complete',candidates=summaries,protected_labels_read=False,new_independent_assessment=False,
        old_frozen_files=frozen[0],reserved_frozen_files=frozen[1]))

if __name__=='__main__':main()
