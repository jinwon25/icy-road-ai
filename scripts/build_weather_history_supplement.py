"""두 검증을 통과한 습도 이력 모형을 전체 학습·실제 추론 가능한 별도 묶음으로 만든다."""
from importlib.metadata import version
from pathlib import Path
import shutil
import sys

import nbformat as nb
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,verify_preserved
from scripts.retrain_weather_history import train
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from src.road_weather_runtime import INPUT_COLUMNS,predict_weather
from src.weather_history_runtime import predict_weather_history


def main():
    temporal=ROOT/'outputs/private/weather_humidity_stable_20261101_v1'
    spatial=temporal
    old=ROOT/'outputs/private/weather_observation_supplement_20261031_v1'
    study=read(temporal/'summary.json');joint=study['reports']['joint'];regional=study['reports']['spatial']
    for folder in [temporal]:
        audit=read(folder/'independent_verification.json')
        assert audit['status']=='passed' and audit['summary_sha256']==sha(folder/'summary.json')
    assert joint['primary_success'] and regional['primary_success']
    receipt=read(old/'receipt.json')
    for name,digest in receipt['files'].items():assert sha(old/name)==digest,name
    out=ROOT/'outputs/private/weather_history_supplement_20261101_v2'
    if out.exists():raise FileExistsError('Preserve history supplement')
    out.mkdir(parents=True)
    for name in ['data','src','scripts','validation','notebooks','model']:(out/name).mkdir()
    f=pd.read_parquet(ROOT/'outputs/private/road_weather_targets_20261031_v3/development.parquet')
    stations=sorted(f.loc[f.relative_humidity.notna(),'station'].unique())
    f=f.loc[f.station.isin(stations),['station','time','group','winter',*INPUT_COLUMNS,'relative_humidity']]
    f=f.sort_values(['station','time']).reset_index(drop=True)
    f.to_parquet(out/'data/training.parquet',index=False,compression='zstd')
    plan=read(ROOT/'config/weather_humidity_stable_20261101.json')
    assert not set(f.station)&set(plan['blocked_stations'])
    write(out/'settings.json',dict(target='relative_humidity',model=plan['model'],allowed_stations=stations,
        blocked_stations=plan['blocked_stations'],data_sha256=sha(out/'data/training.parquet'),
        temporal_summary_sha256=sha(temporal/'summary.json'),spatial_summary_sha256=sha(spatial/'summary.json'),
        scope='Repeated four-region development, separate region and region-plus-winter checks; no official target score'))
    shutil.copytree(old/'model',out/'model/weather_v1')
    for name in ['src/data_source.py','src/observation_io.py','src/road_weather_transfer.py',
        'src/road_weather_runtime.py','src/weather_temporal.py','src/weather_history_stable.py','src/weather_history_runtime.py','src/offline_runtime.py',
        'scripts/predict_weather_history.py','scripts/retrain_weather_history.py']:
        shutil.copy2(ROOT/name,out/name)
    (out/'src/__init__.py').write_text('','utf-8')
    packages=['numpy','pandas','scipy','scikit-learn','joblib','pyarrow','threadpoolctl','python-dateutil',
        'pytz','tzdata','six','nbformat','ipykernel','jupyter-client','ipython']
    (out/'requirements.txt').write_text('\n'.join(p+'=='+version(p) for p in packages)+'\n','utf-8')
    metadata=train(out,out/'model/humidity_history_v1')
    # 재현 예제는 실제 목표값을 입력하지 않는 고정 세 곳의 48시간 기상이다.
    example_stations=['12207','23205','33205'];start=pd.Timestamp('2024-12-14');finish=pd.Timestamp('2024-12-16')
    columns=['station','time',*INPUT_COLUMNS]
    context=f.loc[f.station.isin(example_stations)&f.time.ge(start)&f.time.lt(finish),columns].copy()
    context.to_csv(out/'data/weather_context_example.csv',index=False,encoding='utf-8-sig')
    context=pd.read_csv(out/'data/weather_context_example.csv',dtype={'station':str},float_precision='round_trip')
    with deny_network() as attempts:
        prediction=predict_weather_history(context,out/'model/weather_v1',out/'model/humidity_history_v1')
        legacy=predict_weather(context.assign(time=pd.to_datetime(context.time)),out/'model/weather_v1')
    assert not attempts
    for column in legacy:
        if column.startswith('estimated_humidity'):continue
        pd.testing.assert_series_equal(prediction[column],legacy[column],check_exact=True)
    example=prediction.loc[prediction.time.ge(pd.Timestamp('2024-12-15'))].reset_index(drop=True)
    assert len(example)==432 and example.humidity_history_status.eq('complete_24h').all()
    example.to_csv(out/'data/expected_predictions.csv',index=False,encoding='utf-8-sig')
    # 24시간보다 앞선 문맥을 더 줘도 선택된 하루의 결과가 같아야 한다.
    full=f.loc[f.station.isin(example_stations),columns]
    with deny_network() as attempts:full_prediction=predict_weather_history(full,out/'model/weather_v1',out/'model/humidity_history_v1')
    assert not attempts
    full_day=full_prediction.loc[full_prediction.time.ge(pd.Timestamp('2024-12-15'))&
        full_prediction.time.lt(finish)].reset_index(drop=True)
    difference=float(np.nanmax(np.abs(full_day.estimated_humidity_pct-example.estimated_humidity_pct)))
    np.testing.assert_array_equal(full_day.estimated_humidity_pct,example.estimated_humidity_pct)
    for name,folder in [('temporal',temporal),('spatial',spatial)]:
        for filename in ['summary.json','independent_verification.json']:
            shutil.copy2(folder/filename,out/'validation'/(name+'_'+filename))
    rows=[]
    for validation,reports,season in [('region_and_winter',joint['metrics'],'winters'),
        ('region_only',regional['metrics'],'winters')]:
        for method,report in reports.items():
            for scope,value in [('all',report['pooled']),('cold_input',report['cold']),
                *[('winter_'+k,v) for k,v in report[season].items()],*[('region_'+k,v) for k,v in report['regions'].items()]]:
                rows.append(dict(validation=validation,method=method,scope=scope,**value))
    pd.DataFrame(rows).to_csv(out/'validation/metrics.csv',index=False,encoding='utf-8-sig')
    a=regional['metrics']['instant_residual']['pooled']['mae'];b=regional['metrics']['stable_history']['pooled']['mae']
    ja=joint['metrics']['instant_residual']['pooled']['mae'];jb=joint['metrics']['stable_history']['pooled']['mae']
    worst=max((regional['metrics']['stable_history']['regions'][g]['mae']/m['mae']-1)*100
        for g,m in regional['metrics']['instant_residual']['regions'].items())
    description=f'지역 전체 제외 MAE {a:.6f}→{b:.6f}%p({(1-b/a)*100:.2f}% 감소), 지역·겨울 동시 제외 {ja:.6f}→{jb:.6f}%p({(1-jb/ja)*100:.2f}% 감소)입니다. 가장 큰 지역 악화는 {max(0,worst):.2f}%이며 지역별 결과를 함께 제공합니다.'
    readme='''# 과거 기상 이력을 사용한 도로 습도 추정

도로 기온·풍속의 기존 모형을 유지하고 습도에 과거 3시간·24시간 기상 이력을 추가한 비공개 실행 묶음입니다. {RESULTS} 반복 사용한 개발 4지역의 결과이며 공식 보호 지점 성적이나 새로운 독립 표본이 아닙니다. 결빙 성능 향상으로 해석하지 않습니다.

## 실행

Python 3.11·CPU 환경에서 검증합니다. 설치 후 학습·추론에는 인증정보·외부 AI 서비스·네트워크가 필요하지 않습니다. 포함 예제는 전체 적합 모형의 재현 검사이며 성능 평가가 아닙니다.

```powershell
python -m pip install -r requirements.txt
python scripts/predict_weather_history.py --input data/weather_context_example.csv --output my_prediction.csv --output-start 2024-12-15 --output-end 2024-12-16
python scripts/retrain_weather_history.py --bundle . --output my_history_model
```

출력 이름이 이미 있으면 새 이름을 사용합니다. 입력은 12월 14–15일의 48시간 기상이며 출력은 12월 15일의 432행입니다. 원하는 출력일 앞의 최소 24시간 기상을 함께 넣습니다. 추론 전에 입력을 출력일로 잘라 버리면 과거 이력을 잃습니다. `humidity_history_status`와 `humidity_history_input_slots_24h`는 제공된 과거 입력 행의 충실도를 표시하며 독립 관측 개수·신뢰구간이 아닙니다. 불완전한 이력에서도 모델은 추정할 수 있으나 `partial_24h`로 표시합니다.

각 18/144개 슬롯의 창을 독립적으로 합산해 창보다 오래된 자료를 더 붙여도 같은 특성과 예측을 제공합니다. 누적 연산의 부동소수점 상태를 잇는 초기 구현은 폐기했습니다. `humidity_history_outside_training_range`는 학습 특성의 최솟값·최댓값 범위 이탈이며 오차·신뢰도를 뜻하지 않습니다.

## 입력과 재현 범위

`data/training.parquet`은 허용 13지점의 순수 기상·습도 학습 목표이며 다른 노면·결빙 정답이 없습니다. 같은 도로의 과거 실제 습도도 입력하지 않습니다. ASOS는 엄격히 과거 60분, AWS는 엄격히 과거 15분까지 사용합니다. 습도는 0–100%로 제한하며 현재 입력이 부족하면 결측을 유지합니다. 기온·풍속의 저장 모형은 기존 묶음과 같은 바이트입니다. 실제 서비스 공개 지연까지 검증한 실시간 예보는 아닙니다.

`model/weather_v1`에는 기존 세 모형을 보존했고 새 추론 경로는 습도만 `model/humidity_history_v1`로 대체합니다. 버전 고정 환경·재학습 코드·노트북·제외 지역 지표와 독립 검산을 제공합니다. 실제 제외 지역 모델의 재검증은 원 비공개 작업 공간에서 수행했습니다. 원 관측자료의 제3자 재배포·대회 중 공개 허용을 가정하지 않습니다.

분석·코드·실험·검산·문서에 Codex를 사용했습니다. 참가자가 직접 수동 검토한 사실로 바꾸지 않으며 본체 `AI_USAGE.md`에 판단을 기록합니다.
'''
    (out/'README.md').write_text(readme.replace('{RESULTS}',description),'utf-8')
    book=nb.v4.new_notebook(metadata=dict(kernelspec=dict(display_name='Python 3',language='python',name='python3')))
    book.cells=[nb.v4.new_markdown_cell('# 과거 기상 이력을 사용한 습도 추정\n\n같은 과거 기상만 사용하며 실제 목표 습도·노면 정답을 추론에 넣지 않습니다. 예제는 학습 범위 내 재현 확인입니다.'),
        nb.v4.new_code_cell("from pathlib import Path\nimport sys,json\nimport pandas as pd\nBUNDLE=Path.cwd() if (Path.cwd()/'settings.json').is_file() else Path.cwd().parent\nsys.path.insert(0,str(BUNDLE))\nfrom src.weather_history_runtime import predict_weather_history\nfrom src.offline_runtime import deny_network\nfrom src.data_source import sha256_file as sha\nsettings=json.loads((BUNDLE/'settings.json').read_text('utf-8'))\nassert sha(BUNDLE/'data/training.parquet')==settings['data_sha256']\ndisplay(pd.read_csv(BUNDLE/'validation/metrics.csv').query(\"scope == 'all'\"))"),
        nb.v4.new_code_cell("context=pd.read_csv(BUNDLE/'data/weather_context_example.csv',dtype={'station':str},float_precision='round_trip')\nwith deny_network() as attempts:\n    result=predict_weather_history(context,BUNDLE/'model/weather_v1',BUNDLE/'model/humidity_history_v1')\nassert not attempts\nresult=result.loc[result.time.ge(pd.Timestamp('2024-12-15'))].reset_index(drop=True)\nexpected=pd.read_csv(BUNDLE/'data/expected_predictions.csv',dtype={'station':str},parse_dates=['time'],float_precision='round_trip')\npd.testing.assert_frame_equal(result,expected,check_exact=True)\nprint('과거 문맥 포함 추론 일치:',len(result),'행')"),
        nb.v4.new_code_cell("RUN_REFIT=False\nif RUN_REFIT:\n    import tempfile\n    from scripts.retrain_weather_history import train\n    with tempfile.TemporaryDirectory(prefix='humidity_history_refit_') as temporary:\n        new_model=Path(temporary)/'model'\n        train(BUNDLE,new_model)\n        with deny_network() as attempts:\n            replay=predict_weather_history(context,BUNDLE/'model/weather_v1',new_model)\n        assert not attempts\n        replay=replay.loc[replay.time.ge(pd.Timestamp('2024-12-15'))].reset_index(drop=True)\n        pd.testing.assert_frame_equal(result,replay,check_exact=True)\n    print('전체 습도 재학습 및 432행 추론 일치')\nelse:\n    print('전체 재학습은 RUN_REFIT=True로 실행합니다.')")]
    nb.write(book,out/'notebooks/weather_history_supplement.ipynb')
    assert verify_preserved()==study['preservation']
    write(out/'receipt.json',dict(status='weather_history_supplement_built',metadata=metadata,
        base_model_receipt_sha256=sha(old/'receipt.json'),example_input_rows=len(context),example_output_rows=len(example),
        maximum_extra_context_prediction_difference=difference,training_rows=len(f),training_stations=stations,
        production_road_temperature_changed=False,production_icing_changed=False,
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
    print('HISTORY SUPPLEMENT BUILT',len(example),'rows',difference,flush=True)


if __name__=='__main__':main()
