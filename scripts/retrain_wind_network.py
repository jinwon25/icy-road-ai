"""묶음의 69특성·풍속 정답·잔차 기준값으로 고정 최종 풍속 모형을 재학습한다."""
import argparse
import json
from pathlib import Path
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,default=Path('.'));p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();bundle=args.bundle.resolve();out=args.output.resolve()
    if out.exists():raise FileExistsError('Use a new refit directory')
    metadata=json.loads((bundle/'model/metadata.json').read_text('utf8'));source=bundle/'data/training.parquet'
    assert sha(source)==metadata['training_sha256']
    f=pd.read_parquet(source);names=metadata['features']
    assert not {'ice','road_temp','state_raw','station','winter','observed_wind_speed','anchor_wind_speed'}&set(names)
    count=f.groupby(['station','winter']).station.transform('size').to_numpy(float);weight=1/count;weight/=weight.mean()
    model=HistGradientBoostingRegressor(**metadata['model_parameters']);started=time.perf_counter()
    with deny_network() as attempts,threadpool_limits(limits=2):
        model.fit(f[names],f.observed_wind_speed-f.anchor_wind_speed,sample_weight=weight)
    assert not attempts
    out.mkdir(parents=True);joblib.dump(model,out/'wind_network.joblib',compress=3)
    record=dict(status='wind_network_refit_complete',training_rows=len(f),features=names,network_attempts=0,
        sha256=sha(out/'wind_network.joblib'),seconds=time.perf_counter()-started)
    (out/'receipt.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n','utf8');print(record['status'],len(f),flush=True)


if __name__=='__main__':main()
