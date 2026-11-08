"""포함된 순수 기상 이력·습도 목표로 채택 모형 하나를 처음부터 재학습한다."""
import argparse
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from src.road_weather_transfer import baselines,balanced_weights
from src.weather_history_stable import stable_temporal_features


def train(bundle,output):
    bundle=Path(bundle).resolve();output=Path(output).resolve()
    if output.exists():raise FileExistsError('New history model directory required')
    settings=json.loads((bundle/'settings.json').read_text('utf-8'))
    source=bundle/'data/training.parquet'
    if sha(source)!=settings['data_sha256']:raise ValueError('History training checksum mismatch')
    f=pd.read_parquet(source).sort_values(['station','time']).reset_index(drop=True)
    if not set(f.station)<=set(settings['allowed_stations']) or set(f.station)&set(settings['blocked_stations']):
        raise ValueError('Blocked history training station')
    if {'ice','road_temp','state_raw','air_temperature','wind_speed'}&set(f):
        raise ValueError('Unexpected history training target')
    _,x=stable_temporal_features(f);a,b=baselines(f,'relative_humidity')
    good=f.relative_humidity.notna().to_numpy()&np.isfinite(a)&np.isfinite(b)
    q=f.loc[good];model=HistGradientBoostingRegressor(**settings['model'])
    with deny_network() as attempts,threadpool_limits(limits=2):
        model.fit(x.loc[good],q.relative_humidity.to_numpy()-b[good],sample_weight=balanced_weights(q))
    if attempts:raise RuntimeError('Unexpected history training network attempt')
    output.mkdir(parents=True);path=output/'relative_humidity_history.joblib';joblib.dump(model,path,compress=3)
    ranges={}
    for name in x:
        values=x.loc[good,name].to_numpy(float);values=values[np.isfinite(values)]
        ranges[name]=[float(values.min()),float(values.max())] if len(values) else [None,None]
    metadata=dict(format='humidity_history_residual_v1',file=path.name,sha256=sha(path),features=list(x),
        training_data_sha256=sha(source),training_rows=len(q),training_stations=sorted(q.station.unique()),
        parameters=model.get_params(),history_policy='causal provided weather rows in (t-window,t]; 3h/24h; no target history',
        feature_ranges=ranges,new_independent_assessment=False)
    (output/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
    print('HISTORY TRAINED',len(q),'rows',len(x.columns),'features',flush=True)
    return metadata


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();train(args.bundle,args.output)
