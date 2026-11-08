"""검증된 새 풍속만 독립 실행·전체 재학습 가능한 비공개 보완 묶음으로 만든다."""
import json
from pathlib import Path
import shutil
import sys
import time

import joblib
import nbformat as nb
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,now,verify_preserved
from scripts.evaluate_weather_network_20261101 import network_sources
from src.road_weather_runtime import INPUT_COLUMNS
from src.road_weather_transfer import features,baselines,balanced_weights
from src.wind_network_runtime import predict_wind_network,network_features
from src.offline_runtime import deny_network
from src.data_source import sha256_file as sha


def main():
    plan=read(ROOT/'config/weather_network_20261101.json');study=ROOT/plan['output']
    s=read(study/'summary.json');audit=read(study/'independent_verification.json')
    assert s['accepted_targets']==['wind_speed'] and audit['status']=='passed' and audit['summary_sha256']==sha(study/'summary.json')
    out=ROOT/'outputs/private/wind_network_supplement_20261101_v2'
    if out.exists():raise FileExistsError('Preserve wind supplement')
    frozen=verify_preserved();out.mkdir();(out/'data').mkdir();(out/'model').mkdir();(out/'scripts').mkdir();(out/'notebooks').mkdir()
    for source in (ROOT/'src').rglob('*.py'):
        dest=out/source.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
    for name in ['predict_wind_network.py','retrain_wind_network.py','check_notebook.py']:shutil.copy2(ROOT/'scripts'/name,out/'scripts'/name)
    f=pd.read_parquet(ROOT/plan['input']).sort_values(['station','time']).reset_index(drop=True)
    network=pd.read_parquet(study/'network_features.parquet');x=pd.concat([features(f),network],axis=1)
    asos,anchor=baselines(f,'wind_speed');valid=np.isfinite(f.wind_speed)&np.isfinite(asos)&np.isfinite(anchor)
    assert not set(f.loc[valid,'station'])&set(plan['blocked_stations']) and int(f.loc[valid,'station'].nunique())==13
    training=pd.concat([f.loc[valid,['station','winter']].reset_index(drop=True),x.loc[valid].reset_index(drop=True)],axis=1)
    training['observed_wind_speed']=f.loc[valid,'wind_speed'].to_numpy();training['anchor_wind_speed']=anchor[valid]
    training.to_parquet(out/'data/training.parquet',index=False,compression='zstd')
    model=HistGradientBoostingRegressor(**plan['model']);started=time.perf_counter()
    with deny_network() as attempts,threadpool_limits(limits=2):
        model.fit(x.loc[valid],f.loc[valid,'wind_speed'].to_numpy()-anchor[valid],sample_weight=balanced_weights(f.loc[valid]))
    assert not attempts;joblib.dump(model,out/'model/wind_network.joblib',compress=3)
    aws,coords,locations=network_sources(plan);coordinates=coords.reset_index();coordinates.to_csv(out/'data/aws_coordinates.csv',index=False,encoding='utf-8-sig')
    point_ids=['12207','23205','33205'];points=locations.loc[point_ids].reset_index().rename(columns={'requested_lat':'lat','requested_lon':'lon'})
    points.to_csv(out/'data/points_example.csv',index=False,encoding='utf-8-sig')
    query=f.loc[f.station.isin(point_ids)&f.time.ge('2024-12-15')&f.time.lt('2024-12-16'),['station','time',*INPUT_COLUMNS]].copy()
    assert len(query)==432
    query.to_csv(out/'data/weather_example.csv',index=False,encoding='utf-8-sig')
    small=aws.loc[aws.source_time.ge('2024-12-14 23:45')&aws.source_time.lt('2024-12-16')].copy()
    assert set(small.station)<=set(coords.index)
    small.to_parquet(out/'data/aws_example.parquet',index=False,compression='zstd')
    metadata=dict(format='wind_network_residual_v1',file='wind_network.joblib',sha256=sha(out/'model/wind_network.joblib'),
        features=list(x),model_parameters=plan['model'],network=plan['network'],aws_stations=sorted(coords.index),
        training_rows=int(valid.sum()),training_stations=sorted(f.loc[valid,'station'].unique()),training_sha256=sha(out/'data/training.parquet'),
        study_summary_sha256=sha(study/'summary.json'),study_audit_sha256=sha(study/'independent_verification.json'),
        new_independent_assessment=False,road_temperature_or_icing_changed=False)
    write(out/'model/metadata.json',metadata)
    with deny_network() as attempts:
        result=predict_wind_network(query,points,small,coordinates,out/'model')
        all_source=predict_wind_network(query,points,aws,coordinates,out/'model')
    assert not attempts;pd.testing.assert_frame_equal(result,all_source,check_exact=True)
    qx=network_features(query,points,small,coordinates,plan['network'])[1]
    idx=f.set_index(['station','time']).index.get_indexer(pd.MultiIndex.from_frame(query[['station','time']]))
    np.testing.assert_array_equal(qx.to_numpy(),x.loc[idx].to_numpy())
    result.to_csv(out/'data/reference_predictions.csv',index=False,encoding='utf-8-sig')
    source=ROOT/'outputs/private/weather_history_supplement_20261101_v2/requirements.txt'
    shutil.copy2(source,out/'requirements.txt')
    for name in ['requirements-notebook.txt','requirements-dev.txt']:
        if (ROOT/name).exists():shutil.copy2(ROOT/name,out/name)
    (out/'requirements-notebook.txt').write_text('-r requirements.txt\nnbformat==5.10.4\njupyter_client==8.6.3\nipykernel==6.29.5\nipython==9.2.0\n','utf8')
    book=nb.v4.new_notebook();book.metadata['kernelspec']={'display_name':'Python 3','language':'python','name':'python3'}
    book.cells=[nb.v4.new_markdown_cell('''# 周辺AWSを使った風速モデルの再現

''' .replace('周辺AWSを使った風速モデルの再現','주변 AWS를 이용한 풍속 모형 재현')+'''지역·겨울 제외 비교를 통과한 69특성 풍속 모형입니다. 기존 기온·습도·노면온도·결빙과 독립된 보완 경로입니다. 아래3코드셀은 포함 예제의 API·실제CLI와 전체 학습을 재현합니다. 예제는 독립 성능평가가 아닙니다. 원자료·모형·행단위 예측은 GitHub에 포함하지 않습니다.'''),
    nb.v4.new_code_cell('''from pathlib import Path
import json,sys,subprocess,uuid
import pandas as pd
ROOT=next(p for p in [Path.cwd(),*Path.cwd().parents] if (p/'model/metadata.json').exists() and (p/'data/aws_example.parquet').exists())
sys.path.insert(0,str(ROOT))
from src.wind_network_runtime import predict_wind_network
read=lambda p:pd.read_csv(p,dtype={'station':str},float_precision='round_trip')
query=read(ROOT/'data/weather_example.csv');points=read(ROOT/'data/points_example.csv')
coordinates=read(ROOT/'data/aws_coordinates.csv');aws=pd.read_parquet(ROOT/'data/aws_example.parquet')
expected=read(ROOT/'data/reference_predictions.csv');expected.time=pd.to_datetime(expected.time)
api=predict_wind_network(query,points,aws,coordinates,ROOT/'model')
pd.testing.assert_frame_equal(api,expected,check_exact=True)
print('API exact rows',len(api))'''),
    nb.v4.new_code_cell('''local=ROOT/'local_review'/uuid.uuid4().hex;local.mkdir(parents=True)
command=[sys.executable,str(ROOT/'scripts/predict_wind_network.py'),'--bundle',str(ROOT),'--input',str(ROOT/'data/weather_example.csv'),
         '--aws-input',str(ROOT/'data/aws_example.parquet'),'--points',str(ROOT/'data/points_example.csv'),'--output',str(local/'cli.csv')]
run=subprocess.run(command,cwd=ROOT,text=True,capture_output=True);assert run.returncode==0,run.stderr
actual=read(local/'cli.csv');actual.time=pd.to_datetime(actual.time)
pd.testing.assert_frame_equal(actual,expected,check_exact=True)
print('Actual CLI exact rows',len(actual))'''),
    nb.v4.new_code_cell('''import shutil,hashlib,joblib
command=[sys.executable,str(ROOT/'scripts/retrain_wind_network.py'),'--bundle',str(ROOT),'--output',str(local/'refit')]
run=subprocess.run(command,cwd=ROOT,text=True,capture_output=True);assert run.returncode==0,run.stderr
meta=json.loads((ROOT/'model/metadata.json').read_text(encoding='utf8'))
meta['sha256']=hashlib.sha256((local/'refit/wind_network.joblib').read_bytes()).hexdigest()
(local/'refit/metadata.json').write_text(json.dumps(meta),encoding='utf8')
refit=predict_wind_network(query,points,aws,coordinates,local/'refit')
pd.testing.assert_frame_equal(refit,expected,check_exact=True)
print('Full-data refit exact rows',len(refit),'training rows',meta['training_rows'])''')]
    nb.write(book,out/'notebooks/wind_network_review.ipynb')
    (out/'README.md').write_text('''# 주변 AWS 관측망을 이용한 풍속 추정

기온·습도·노면온도·결빙을 바꾸지 않는 독립 풍속 보완 모형입니다. 지역 제외 MAE0.563455→0.499955m/s, 지역·겨울 동시 제외0.567465→0.508379m/s입니다. 반복 사용한4개 개발 지역의 검증으로 공식 성적이나 새 독립 표본이 아닙니다. 주변 AWS는 최대4곳·50km·엄격한 과거15분·거리 제곱 역수로 결합하며69특성을 사용합니다.

```powershell
python -m pip install -r requirements.txt
python scripts/predict_wind_network.py --bundle . --input data/weather_example.csv --aws-input data/aws_example.parquet --points data/points_example.csv --output my_wind.csv
python scripts/retrain_wind_network.py --bundle . --output my_refit
```

입력은 기존28기상 열과 station/time, 도로좌표 station/lat/lon, AWS의 station/source_time 및 air_temp/humidity/wind_speed/rain_15m/dewpoint입니다. 좌표 카탈로그는 전체34곳을 유지합니다. 같은 시각과 미래 관측은 쓰지 않고15분보다 오래된 원천은 결측입니다. 해당 기간 관측이 없는 AWS도 기하학적 후보 자리를 유지하고 빈 배열로 처리하며 먼 관측소를 대신 올리거나 가상의 관측시각·값을 만들지 않습니다. 시각은KST이며 시간대가 있으면KST로 바꿉니다.

포함 예제는3도로×144시각=432행입니다. 전체 과거와 최소 문맥 원천의 결과는 정확히 같습니다. ASOS 유효 풍속이 없으면NA를 출력합니다. 관측소 간 범위·유효 개수는 입력 진단이며 추정 오차나 예측구간이 아닙니다.

data/training.parquet은 허용13기상 지점의 두 겨울69특성·정답·잔차 기준값입니다. 전체 재학습은 같은 고정 설정과 지점·겨울 역빈도 가중치를 사용합니다. 원시AWS에서 이 학습 특성을 다시 구성하는 연구 전체에는 원 작업 공간 자료가 추가로 필요합니다. 노트북3코드셀은API·실제CLI·전체 재학습을 실행합니다. 출력은 local_review에만 쓰며 기존 파일을 덮어쓰지 않습니다.

기존843구간의 풍속 지도는 앞선 모형의 결과로 보존했습니다. 이 새 모형을 적용한 지도로 표시하지 않습니다. 새 노면온도·결빙 개선도 주장하지 않습니다. 제공 자료·모형·예측은 승인된 대회 로컬 검토용이며 GitHub 공유 대상에서 제외합니다.
''','utf8')
    assert verify_preserved()==frozen
    write(out/'receipt.json',dict(status='wind_network_supplement_created_pending_relocated_refit',at_utc=now(),training_rows=int(valid.sum()),
        training_stations=int(f.loc[valid,'station'].nunique()),features=len(x.columns),example_rows=len(result),
        prefix_exact=True,feature_values_exact=int(qx.size),seconds=time.perf_counter()-started,preservation=frozen,
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file() and '__pycache__' not in p.parts}))
    print('WIND SUPPLEMENT',len(training),'training rows;432 exact;69 features',flush=True)


if __name__=='__main__':main()
