"""검증한 두 겨울 온도 모델로 새 후보를 학습·추론한다. 이전 ZIP은 보존한다."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import sys
import time
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.submission_archive import restore_archive
from src.submission_runtime import FEATURES,infer
from src.submission_io import read_weather
from src.two_winter import validate
from src.offline_runtime import deny_network
from scripts.evaluate_method_blending import preservation

PRIVATE=ROOT/'outputs/private';OUT=PRIVATE/'submission_candidate_20261024_v2'
EXPERIMENT=PRIVATE/'two_winter_models_20261024_v1'

def read(p):return json.loads(p.read_text('utf-8'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')

def manifest():
    files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)
        for p in OUT.rglob('*') if p.is_file() and p!=OUT/'manifest.json' and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    write(OUT/'manifest.json',dict(version=6,status='private_two_winter_candidate',development_scope='two_winter',
        created_at_utc=datetime.now(timezone.utc).isoformat(),files=files,independent_performance_qualified=False,competition_submitted=False))

def prepare():
    audit=read(EXPERIMENT/'audit_runtime.json');assert audit['temperature_adopt']
    assert audit['summary_sha256']==sha(EXPERIMENT/'summary.json')
    freeze=preservation()
    restore_archive(PRIVATE/'submission_candidate_20261024_v1.zip',OUT)
    (OUT/'reports/history').mkdir(exist_ok=True)
    shutil.copy2(OUT/'model/model_card.json',OUT/'reports/history/model_card_first_winter.json')
    source=PRIVATE/'two_winter_development_20261024_v1/development.parquet'
    receipt=read(source.parent/'receipt.json');assert sha(source)==receipt['data_sha256']
    f=validate(pd.read_parquet(source)).sort_values(['station','time']).reset_index(drop=True)
    train=f.loc[np.isfinite(f.road_temp)&np.isfinite(f.asos_air_temp),['station','time','road_temp',*FEATURES]].copy()
    train.to_parquet(OUT/'data/training_weather_temperature.parquet',index=False,compression='zstd')
    parameters=read(ROOT/'config/two_winter_development_20261024.json')['temperature_parameters']
    plan=dict(features=list(FEATURES),parameters=parameters,allowed_stations=sorted(train.station.unique()),weights=[.5,.5],
        periods=[['2024-11-01','2025-03-01'],['2025-11-01','2026-03-01']],second_winter_training=True,
        former_nonprotected_temporal_holdout_reclassified=True,protected_outcomes_used=False,new_independent_assessment=False,
        source_sha256=sha(source),training_data_sha256=sha(OUT/'data/training_weather_temperature.parquet'))
    write(OUT/'training_plan.json',plan);receipts=[]
    with deny_network() as attempts,threadpool_limits(limits=2):
        for name,loss in [('weather12_mse300','squared_error'),('weather12_mae300','absolute_error')]:
            started=time.perf_counter();model=HistGradientBoostingRegressor(loss=loss,**parameters).fit(train[list(FEATURES)],train.road_temp)
            path=OUT/'model'/(name+'.joblib');joblib.dump(model,path,compress=3)
            receipts.append(dict(name=name,parameters=parameters|{'loss':loss},features=list(FEATURES),training_rows=len(train),
                training_stations=plan['allowed_stations'],periods=plan['periods'],model_sha256=sha(path),fit_seconds=time.perf_counter()-started))
            print('최종 두 겨울 모델',name,len(train),round(receipts[-1]['fit_seconds'],1),flush=True)
    assert attempts==[];write(OUT/'model/fit_receipts.json',receipts)
    write(OUT/'model/model_card.json',dict(candidate='weather12_two_winter_mse_mae_mean',temperature_development_adopted=True,
        performance_qualified=False,new_independent_assessment=False,training_rows=len(train),training_stations=plan['allowed_stations'],
        second_winter_training=True,protected_outcomes_used=False,temperature=audit['temperature'],cold_temperature=audit['cold_temperature'],
        ice_validation=audit['physical']['both'],ice_policy='mean temperature <=0 and moisture evidence',
        ice_policy_note='직접 분류 후보는 기온 기준선을 넘지 못해 미채택. 고정 온도·수분 조건의 전체 F1 개선은 작고 Recall은 하락함'))
    # 완결 후보 안에서 재현 가능한 새 학습 코드. 과거 소스는 원 ZIP에 보존.
    trainer='''"""포함된 허용 23곳·두 겨울로 고정 온도 모델 두 개 재적합."""
from pathlib import Path
import argparse,json,sys
import joblib,numpy as np,pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
from src.two_winter import validate
from src.submission_runtime import FEATURES
from src.offline_runtime import deny_network
p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args()
if a.output.exists():raise FileExistsError('New output required')
plan=json.loads((HERE/'training_plan.json').read_text('utf-8'))
f=validate(pd.read_parquet(HERE/'data/training_weather_temperature.parquet'))
assert set(f.station)==set(plan['allowed_stations'])
assert np.isfinite(f.road_temp).all() and np.isfinite(f.asos_air_temp).all()
a.output.mkdir(parents=True)
with deny_network() as attempts,threadpool_limits(limits=2):
 for n,l in [('weather12_mse300','squared_error'),('weather12_mae300','absolute_error')]:
  m=HistGradientBoostingRegressor(loss=l,**plan['parameters']).fit(f[list(FEATURES)],f.road_temp)
  joblib.dump(m,a.output/(n+'.joblib'),compress=3)
assert not attempts
print('두 겨울 고정 모델 재적합 완료')
'''
    (OUT/'code/train.py').write_text(trainer,'utf-8')
    for name in ['award_ice.py','two_winter.py','runtime_metrics.py','delivery_tables.py']:
        shutil.copy2(ROOT/'src'/name,OUT/'src'/name)
    (OUT/'research/two_winter').mkdir(exist_ok=True)
    for name in ['summary.json','audit.json','audited_predictions.parquet','temperature_regions.csv','stations.csv','daily.csv','fits.json','plan.json','decisions.json']:
        shutil.copy2(EXPERIMENT/name,OUT/'research/two_winter'/name)
    shutil.copy2(EXPERIMENT/'audit.json',OUT/'research/two_winter/audit_before_runtime_correction.json')
    shutil.copy2(EXPERIMENT/'audit_runtime.json',OUT/'research/two_winter/audit.json')
    shutil.copy2(EXPERIMENT/'runtime_predictions.parquet',OUT/'research/two_winter/audited_predictions.parquet')
    assert preservation()==freeze
    write(OUT/'validation/two_winter_training.json',dict(status='two_winter_final_fit_complete',rows=len(train),models=2,network_attempts=0,
        source_zip_sha256=sha(PRIVATE/'submission_candidate_20261024_v1.zip'),source_data_sha256=sha(source),protected_overlap=[]))

def predict():
    if (OUT/'validation/two_winter_inference.json').exists():raise FileExistsError('Preserve completed inference')
    models=[joblib.load(OUT/'model'/(n+'.joblib')) for n in ['weather12_mse300','weather12_mae300']]
    groups=read(OUT/'data/prediction_group_manifest.json')
    index=pd.read_csv(OUT/'data/point_prediction_index.csv',dtype={'id':str,'prediction_group':str})
    summary=pd.read_csv(OUT/'data/segment_candidate_summary.csv',dtype={'seg_id':str,'prediction_group':str},float_precision='round_trip')
    protected=[];changed=0;total=0
    with deny_network() as attempts:
        for group,metadata in groups.items():
            path=OUT/'data/weather_groups'/(group+'.parquet');assert sha(path)==metadata['weather_sha256']
            weather=pd.read_parquet(path);result=infer(weather,models)
            old=pd.read_parquet(OUT/'data/prediction_groups'/(group+'.parquet'))
            changed+=int((result.predicted_ice.fillna(-1)!=old.predicted_ice.fillna(-1)).sum());total+=len(result)
            result.to_parquet(OUT/'data/prediction_groups'/(group+'.parquet'),index=False,compression='zstd')
            metadata['predictions_sha256']=sha(OUT/'data/prediction_groups'/(group+'.parquet'))
            for point in index.loc[index.kind.eq('protected')&index.prediction_group.eq(group)].itertuples():
                p=result.copy();p.station=point.id;p['winter']=point.winter;protected.append(p)
            good=result.predicted_ice.notna();positive=result.predicted_ice.eq(1).fillna(False)
            updates=dict(temperature_valid_slots=int(result.estimated_road_temp_c.notna().sum()),ice_valid_slots=int(good.sum()),
                cold_wet_slots=int(positive.sum()),cold_wet_hours=float(positive.sum()/6),cold_wet_fraction=float(positive.sum()/good.sum()),
                consensus_slots=int(result.condition_evidence.eq('cold_wet_consensus').sum()),disagreement_slots=int(result.condition_evidence.eq('cold_wet_disagreement').sum()),
                estimated_temp_mean_c=float(result.estimated_road_temp_c.mean()))
            for key,value in updates.items():summary.loc[summary.prediction_group.eq(group),key]=value
            if total%(17280*20)==0:print('새 모델 공간 추론',total,flush=True)
        example=infer(read_weather(OUT/'data/weather_example.csv'),models)
        example.to_csv(OUT/'data/example_predictions.csv',index=False,encoding='utf-8-sig')
    assert not attempts
    protected=pd.concat(protected,ignore_index=True).sort_values(['station','time'])
    assert len(protected)==103680 and not protected.duplicated(['station','time']).any()
    protected.to_csv(OUT/'data/protected_predictions_10min.csv.gz',index=False,encoding='utf-8-sig',compression='gzip')
    summary.to_csv(OUT/'data/segment_candidate_summary.csv',index=False,encoding='utf-8-sig')
    write(OUT/'data/prediction_group_manifest.json',groups)
    write(OUT/'validation/two_winter_inference.json',dict(status='two_winter_inference_complete',group_rows=total,
        groups=len(groups),changed_group_ice_rows=changed,protected_rows=len(protected),protected_missing=int(protected.predicted_ice.isna().sum()),
        protected_outcomes_read=False,network_attempts=0))
    manifest()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',required=True,choices=['prepare','predict','manifest'])
    globals()[parser.parse_args().stage]()
