"""보완 묶음의 관측 기상값으로 채택된 잔차 모형을 처음부터 재학습한다."""
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
from src.road_weather_transfer import features,baselines,balanced_weights


def train(bundle,output):
    bundle=Path(bundle).resolve();output=Path(output).resolve()
    if output.exists():raise FileExistsError('New model directory required')
    settings=json.loads((bundle/'settings.json').read_text(encoding='utf-8'))
    path=bundle/'data/training.parquet';assert sha(path)==settings['data_sha256']
    f=pd.read_parquet(path)
    assert set(f.station)<=set(settings['allowed_stations'])
    assert not set(f.station)&set(settings['blocked_stations'])
    assert not {'ice','road_temp','state_raw'}&set(f)
    x=features(f);output.mkdir(parents=True)
    metadata=dict(format='road_weather_residual_v1',features=list(x),targets={},
                  training_data_sha256=sha(path),new_independent_assessment=False)
    for target in settings['selected_targets']:
        a,b=baselines(f,target);good=f[target].notna().to_numpy()&np.isfinite(a)&np.isfinite(b)
        q=f.loc[good];model=HistGradientBoostingRegressor(**settings['model'])
        with deny_network() as attempts,threadpool_limits(limits=2):
            model.fit(x.loc[q.index],q[target].to_numpy()-b[q.index],sample_weight=balanced_weights(q))
        assert not attempts
        path=output/(target+'.joblib');joblib.dump(model,path,compress=3)
        metadata['targets'][target]=dict(file=path.name,sha256=sha(path),training_rows=len(q),
            training_stations=sorted(q.station.unique()),parameters=model.get_params())
        print('보완 모형 학습:',target,len(q),'행',flush=True)
    (output/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return metadata


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args();train(args.bundle,args.output)


if __name__=='__main__':main()
