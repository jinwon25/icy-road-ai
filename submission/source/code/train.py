"""제출 폴더의 고정 계획·포함 자료로 온도 및 결빙 기준 모델을 재학습한다."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    base=args.bundle.resolve();sys.path.insert(0,str(base))
    from src.offline_runtime import deny_network
    from src.solar_thermal_runtime import temperature_predictors
    from src.submission_runtime import FEATURES
    plan=json.loads((base/'extended_training_plan.json').read_text('utf-8'))
    if args.output.exists():raise FileExistsError('New output directory required')
    allowed=set(plan['allowed_stations']);protected={'12410','33411','23402'}
    if allowed&protected:raise ValueError('Protected labels cannot enter training')
    sources={}
    for name,entry in plan['training_sources'].items():
        path=base/entry['file']
        if digest(path)!=entry['sha256']:raise ValueError('Training source hash mismatch')
        f=pd.read_parquet(path)
        if set(f.station)!=allowed or f.duplicated(['station','time']).any():raise ValueError('Unexpected training identities')
        time=pd.to_datetime(f.time)
        valid_period=(time.ge('2024-11-01')&time.lt('2025-03-01'))|(time.ge('2025-11-01')&time.lt('2026-03-01'))
        if time.dt.tz is not None or not valid_period.all() or not time.eq(time.dt.floor('10min')).all():
            raise ValueError('Two fixed KST winter grids required')
        if name=='temperature':
            weather=f.drop(columns='road_temp');x,available,_=temperature_predictors(weather,plan['temperature_feature_kind'])
            mask=f.road_temp.notna()&available
        elif name=='icing_reference':
            x=f[list(FEATURES)];mask=f.road_temp.notna()&f.asos_air_temp.notna()
        else:raise ValueError('Unknown training source role')
        sources[name]=(x.loc[mask],f.loc[mask,'road_temp'])
    args.output.mkdir(parents=True);receipts=[]
    with deny_network() as attempts,threadpool_limits(limits=2):
        for spec in plan['models']:
            x,y=sources[spec['role']]
            if len(x)!=spec['training_rows'] or not set(spec['features'])<=set(x):raise ValueError('Training feature or row mismatch')
            x=x[spec['features']]
            if not np.isfinite(y).all() or np.isinf(x.to_numpy(float)).any():raise ValueError('Invalid training values')
            model=HistGradientBoostingRegressor(**spec['parameters']).fit(x,y)
            path=args.output/(spec['name']+'.joblib');joblib.dump(model,path,compress=3)
            receipts.append(dict(name=spec['name'],role=spec['role'],rows=len(x),sha256=digest(path)))
            print('고정 모델 재학습',spec['name'],len(x),flush=True)
    assert not attempts
    receipt=dict(status='fixed_models_refitted_offline',models=receipts,network_attempts=0,protected_labels_read=False,
        plan_sha256=digest(base/'extended_training_plan.json'))
    (args.output/'refit_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf-8')

if __name__=='__main__':main()
