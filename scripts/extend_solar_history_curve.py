"""정정 입력의 600회 모델을 동일 학습행에서 1200·2400회까지 연장한다.

평가 점수로 조기 종료하지 않는다. 단계·소스·정답 격리를 실행 전에 고정한다.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import time
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.solar_memory_search import feature_table
from src.two_winter import validate
from src.extended_search import temperature_gate
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from scripts.evaluate_method_blending import preservation


def read(p):return json.loads(p.read_text('utf-8'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();out=args.output
    parent=ROOT/'outputs/private/solar_memory_search_20261024_v1';parent_plan=read(parent/'plan.json')
    data_path=ROOT/parent_plan['settings']['data'];base_path=ROOT/parent_plan['settings']['baseline']
    assert sha(data_path)==parent_plan['signatures']['data']
    assert sha(base_path)==read(base_path.parent/'audit_runtime.json')['runtime_prediction_sha256']
    settings=dict(parent_plan['settings']);settings['purpose']='Combined ASOS solar-history capacity curve, fixed 1200/2400 stages, same training data, no validation-driven early stopping'
    settings['candidates']=[dict(name=f'combined_asos_solar_{loss}{n}',family='hgb',loss=actual,iterations=n,leaves=31,features='combined_asos_solar')
        for loss,actual in [('mae','absolute_error')] for n in [1200,2400]]
    signatures=dict(additional_sources=parent_plan['settings']['additional_source_sha256'],data=sha(data_path),code=sha(Path(__file__)),parent_plan=sha(parent/'plan.json'),
        thermal=sha(ROOT/'src/solar_memory_search.py'),extended=sha(ROOT/'src/extended_search.py'))
    if out.exists():assert read(out/'plan.json')['signatures']==signatures
    else:
        out.mkdir(parents=True);write(out/'plan.json',dict(settings=settings,signatures=signatures,started=datetime.now(timezone.utc).isoformat()))
    for source_name, expected in settings['additional_source_sha256'].items():assert sha(ROOT/source_name)==expected
    frozen=preservation();data=validate(pd.read_parquet(data_path)).sort_values(['station','time']).reset_index(drop=True)
    x=feature_table(data,'combined_asos_solar');baseline=validate(pd.read_parquet(base_path));results={}
    for loss in ['mae']:
        origin=parent/f'combined_asos_solar_{loss}600';origin_report=read(origin/'report.json')
        for initial in origin_report['fits']:
            group=initial['group'];query=data.loc[data.group.eq(group)]
            train=data.loc[~data.group.eq(group)&data.road_temp.notna()&data.asos_air_temp.notna()]
            assert sorted(train.station.unique())==initial['training_stations'] and len(train)==initial['training_rows']
            assert not set(train.station)&set(query.station)
            previous=origin/(group+'.joblib');assert sha(previous)==initial['model_sha256']
            model=joblib.load(previous)
            for n in [1200,2400]:
                name=f'combined_asos_solar_{loss}{n}';folder=out/name;folder.mkdir(exist_ok=True)
                record=folder/(group+'.json');modelpath=folder/(group+'.joblib');predpath=folder/(group+'.parquet')
                if record.exists():
                    saved=read(record);assert sha(modelpath)==saved['model_sha256'] and sha(predpath)==saved['prediction_sha256']
                    model=joblib.load(modelpath);continue
                model.set_params(warm_start=True,max_iter=n);t=time.perf_counter()
                with deny_network() as attempts,threadpool_limits(limits=2):
                    model.fit(x.loc[train.index],train.road_temp.to_numpy())
                    pred=model.predict(x.loc[query.index])
                assert not attempts and np.isfinite(pred).all() and model.n_iter_==n
                f=query[['station','time','group','winter','ice','road_temp','asos_air_temp']].copy()
                f['prediction']=np.where(query.asos_air_temp.notna(),pred,np.nan)
                f.to_parquet(predpath,index=False,compression='zstd');joblib.dump(model,modelpath,compress=3)
                write(record,dict(candidate=name,group=group,training_rows=len(train),training_stations=sorted(train.station.unique()),
                    features=list(x),parameters=model.get_params(),model_sha256=sha(modelpath),prediction_sha256=sha(predpath),
                    seconds=time.perf_counter()-t,protected_labels_read=False,initial_600_model_sha256=initial['model_sha256']))
                print(name,group,round(time.perf_counter()-t,1),flush=True)
        for n in [1200,2400]:
            name=f'combined_asos_solar_{loss}{n}';folder=out/name
            f=pd.concat([pd.read_parquet(folder/(r['group']+'.parquet')) for r in origin_report['fits']],ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
            pd.testing.assert_frame_equal(f[['station','time']],baseline[['station','time']])
            report=temperature_gate(f,f.prediction,baseline.temperature_both,settings['temperature_gate'])
            report['fits']=[read(folder/(r['group']+'.json')) for r in origin_report['fits']]
            f.to_parquet(folder/'predictions.parquet',index=False,compression='zstd');write(folder/'report.json',report);results[name]=report
            print('RESULT',name,report['regression']['pooled']['mae'],report['gates'],flush=True)
    assert preservation()==frozen
    write(out/'summary.json',dict(status='fixed_capacity_curve_complete',candidates=results,protected_labels_read=False,new_independent_assessment=False))

if __name__=='__main__':main()
