"""허용된 첫 겨울23곳으로 고정2모델을 적합하고 일반 추론 후보를 새 비공개 폴더에 준비."""
from datetime import datetime, timezone
from pathlib import Path
import json
import platform
import shutil
import sys
import time
import joblib
import numpy as np
import pandas as pd
import sklearn
import pyarrow
import threadpoolctl
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write,preservation,training
from src.method_blending import domain,ALLOWED
from src.data_source import sha256_file as sha
from src.submission_runtime import FEATURES,WATER,infer
from src.offline_runtime import deny_network

PRIVATE=ROOT/'outputs/private'
OUT=PRIVATE/'submission_candidate_20261013_v1'
SOURCE=PRIVATE/'weather_distance_20261010_v1/development_inputs.parquet'


def main():
    if OUT.exists():raise FileExistsError('Preserve earlier submission candidate')
    frozen=preservation(); plan=read(ROOT/'config/weather_memory_control_experiment.json')
    audit=read(PRIVATE/'weather_memory_controls_20261013_v1/independent_verification.json')
    assert audit['summary_sha256']==sha(PRIVATE/'weather_memory_controls_20261013_v1/summary.json')
    f=domain(pd.read_parquet(SOURCE,columns=['station','time','road_temp',*FEATURES,*[c for c in WATER if c not in FEATURES]]))
    assert set(f.station)==ALLOWED
    train=training(f,set()); assert set(train.station)==ALLOWED
    for folder in ['model','data','code','reports','figures','demo','validation']:(OUT/folder).mkdir(parents=True)
    write(OUT/'training_plan.json',dict(created_at_utc=datetime.now(timezone.utc).isoformat(),
        source_sha256=sha(SOURCE),allowed_stations=sorted(ALLOWED),training_period=['2024-11-01','2025-03-01'],
        features=list(FEATURES),weights=[.5,.5],parameters=plan['hgb_parameters'],
        development_candidate_only=True,assessment_outcomes_used=False,second_winter_training=False,
        model_promotion=False,ice_criterion='mean_temperature<=0 and (dewpoint>=temperature or previous_rain>0 or snow>0)',
        missing_prediction='nullable, never silently non-ice',official_csv_schema=False))
    train.to_parquet(OUT/'data/training_weather_temperature.parquet',index=False,compression='zstd')
    models=[];receipts=[]
    with deny_network() as attempts,threadpool_limits(limits=2):
        for name,loss in [('weather12_mse300','squared_error'),('weather12_mae300','absolute_error')]:
            params=plan['hgb_parameters']|{'loss':loss};started=time.monotonic()
            model=HistGradientBoostingRegressor(**params).fit(train[list(FEATURES)],train.road_temp)
            path=OUT/'model'/(name+'.joblib');joblib.dump(model,path,compress=3);models.append(model)
            receipts.append(dict(name=name,parameters=params,features=list(FEATURES),training_rows=len(train),
                training_stations=sorted(train.station.unique()),model_sha256=sha(path),fit_seconds=time.monotonic()-started))
            print(name,'학습 완료',len(train),flush=True)
        example=f.loc[f.station.eq('12207')&f.time.dt.normalize().eq(pd.Timestamp('2024-12-15'))].drop(columns='road_temp').reset_index(drop=True)
        assert len(example)==144
        example.to_csv(OUT/'data/weather_example.csv',index=False,encoding='utf-8-sig')
        result=infer(example,models);result.to_csv(OUT/'data/example_predictions.csv',index=False,encoding='utf-8-sig')
    assert attempts==[];write(OUT/'model/fit_receipts.json',receipts)
    shutil.copy2(ROOT/'src/submission_runtime.py',OUT/'code/predict.py')
    shutil.copy2(ROOT/'src/offline_runtime.py',OUT/'code/offline_runtime.py')
    trainer='''"""비공개 허용23곳 첫 겨울 학습 표로 고정2모델을 새 경로에 재적합한다."""
from pathlib import Path
import argparse,json
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits
from predict import FEATURES
from offline_runtime import deny_network
HERE=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
if args.output.exists():raise FileExistsError('Existing model directory preserved')
plan=json.loads((HERE/'training_plan.json').read_text('utf-8'));f=pd.read_parquet(HERE/'data/training_weather_temperature.parquet')
assert set(f.station)==set(plan['allowed_stations']) and not f.duplicated(['station','time']).any()
assert f.time.ge('2024-11-01').all() and f.time.lt('2025-03-01').all()
assert np.isfinite(f.road_temp).all() and np.isfinite(f.asos_air_temp).all()
args.output.mkdir(parents=True)
with deny_network() as attempts,threadpool_limits(limits=2):
 for name,loss in [('weather12_mse300','squared_error'),('weather12_mae300','absolute_error')]:
  m=HistGradientBoostingRegressor(**(plan['parameters']|{'loss':loss})).fit(f[list(FEATURES)],f.road_temp)
  joblib.dump(m,args.output/(name+'.joblib'),compress=3)
assert attempts==[]
print('고정2모델 재적합 완료')
'''
    (OUT/'code/train.py').write_text(trainer,encoding='utf-8')
    versions={'joblib':joblib.__version__,'numpy':np.__version__,'pandas':pd.__version__,'pyarrow':pyarrow.__version__,'scikit-learn':sklearn.__version__,'threadpoolctl':threadpoolctl.__version__}
    (OUT/'requirements.txt').write_text('\n'.join(f'{n}=={v}' for n,v in versions.items())+'\n',encoding='utf-8')
    write(OUT/'environment.json',dict(python=platform.python_version(),os=platform.platform(),versions=versions,gpu_required=False,max_compute_threads=2))
    assert preservation()==frozen
    write(OUT/'preparation_receipt.json',dict(status='submission_candidate_models_prepared',created_at_utc=datetime.now(timezone.utc).isoformat(),
        fits=2,training_rows=len(train),station_count=23,new_independent_assessment=False,
        protected_or_opened_outcomes_used=False,network_attempts=0,submitted=False,model_promoted=False,
        old_frozen_files=frozen[0],reserved_frozen_files=frozen[1]))


if __name__=='__main__':main()
