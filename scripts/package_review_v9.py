"""검증된 기상 보완을 v8에 추가해 v9 문서·모델 ZIP과 실행 영수증을 만든다."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import nbformat as nb
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,now,verify_preserved
from scripts.review_submission_bundle import verify_directory
from scripts.package_review_v8 import copy,archive
from scripts.check_markdown import inspect_documents
from src.data_source import sha256_file as sha

P=ROOT/'outputs/private'
OLD=P/'submission_candidate_20261031_v8'
OUT=P/'submission_candidate_20261031_v9'
CHANNELS=P/'submission_channels_20261031_v9'
REPORT=P/'report_update_20261031_v9_final'
SUPPLEMENT=P/'weather_observation_supplement_20261031_v1'
UPDATED={'README.md','README_repository.md','AI_USAGE.md','docs/STATUS.md','docs/README.md','docs/START_HERE.md',
         'docs/delivery/WEATHER_SUPPLEMENT_20261031.md','docs/delivery/REVIEWER_GUIDE.md'}
STUDIES=['road_weather_transfer_20261031_v1','weather_calibration_controls_20261031_v1',
         'transferred_air_icing_20261031_v1','road_weather_review_20261031_v1',
         'weather_segment_projection_20261031_v1','weather_projection_review_20261031_v2']

MODEL_README='''# 미관측 고속도로 기상·노면온도 추정과 결빙 조건 · v9

노면온도 추정, 도로 기온·습도·풍속 보완 모형, 두 겨울 구간 지도와 최신 공식 취약구간 비교를 제공하는 비공개 검토 결과물입니다. 새 기상 추정기는 지역 제외 검증을 거쳐 별도 기능으로 추가했습니다. 기존 노면온도 v3·결빙 판정 v2·보호 평가 기록은 유지했습니다.

## 결과와 읽는 순서

1. [17쪽 통합 보고서](reports/analysis_report_v9.pdf): 개요·자료·개발·검증·효과·한계.
2. [도로 기상 보완 모형](research/weather_observation_supplement/README.md): 기온·습도·풍속의 전체 재학습·추론.
3. [전체 학습·추론 노트북](notebooks/submission_review_v9.ipynb), [새 기상·지도 검토](notebooks/weather_review_v9.ipynb).
4. [공식 목록 탐색](research/latest/official_inventory_viewer_20261031_v1/index.html), [두 겨울 기상 지도](research/latest/weather_projection_review_20261031_v2/weather_projection_two_winters.png).
5. [조건 기준표](docs/delivery/RISK_CRITERIA_20261031.md), [CSV 규약](docs/delivery/CSV_CONTRACT.md), [AI 활용 기록](AI_USAGE.md).

| 검증 대상 | 주요 결과 | 해석 범위 |
| --- | --- | --- |
| 노면온도 | MAE 1.145698°C, 기존 대비 13.66% 감소 | 개발 9곳·두 겨울·310,091유효쌍 |
| 도로 기온 | MAE 1.323764°C, AWS 우선 대비 22.10% 감소 | 기상 정답이 있는 개발 4곳·지역 제외 |
| 도로 상대습도 | MAE 5.875898%p, 10.02% 감소 | 같은 개발 범위, 유효 쌍은 목표마다 다름 |
| 도로 1분 풍속 | MAE 0.563455m/s, 42.67% 감소 | 학습 중앙값 대조 대비 감소는 16.94% |
| 결빙 판정 | 현재 F1 0.026554 < 기온 기준선 0.036601 | 기상·온도 개선을 결빙 개선으로 해석하지 않음 |

도로 기상은 두 겨울 각각에서도 개선했고 학습 상수 기준선도 넘었습니다. 그러나 풍속 R²는 0.268789이며 일부 지역·지표는 악화했습니다. 모두 반복 개발 결과로 공식 점수·신규 독립 성능이 아닙니다. 추정 기온을 0°C 기준 결빙 판정에 사용한 고정 정책은 F1이 0.035825로 낮아지고 기존 탐지 38사건을 잃어 채택하지 않았습니다.

## 실행 환경

검증 환경: Windows 빌드 10.0.26200, x64 Intel CPU, 물리 메모리 약 15.6GiB, Python 3.11.2. GPU·NVIDIA Driver·CUDA는 사용하지 않았습니다. NumPy 2.2.6, pandas 2.2.3, scikit-learn 1.6.1, SciPy 1.15.3, PyArrow 20.0.0, joblib 1.5.1입니다. 버전 고정 파일을 함께 제공합니다. 설치 후 기본 재학습·추론에 외부 AI 서비스·API·인증정보가 필요하지 않습니다. 전체 구간 입력을 원천에서 다시 수집하는 연구 단계는 별도입니다.

ZIP을 해제한 `icy_road_model` 폴더에서 실행합니다. 기존 출력 이름은 새 이름으로 바꿉니다.

```powershell
python -m pip install -r requirements-notebook.txt
$env:OMP_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
python scripts/review_submission_bundle.py --smoke --output local_review/my_review.json
python scripts/check_notebook.py notebooks/weather_review_v9.ipynb
python -X utf8 code/train.py --output local_review/my_refit
python -X utf8 code/predict.py --input data/weather_example.csv --output local_review/my_prediction.csv --output-start 2024-12-15 --output-end 2024-12-16
```

첫 검사는 전체 파일 해시, 기존 모델의 144행 정확한 예측 일치와 기본 5코드 셀을 확인합니다. 기본 노트북은 재학습을 생략합니다. 위 학습 명령은 포함된 허용 23곳의 두 겨울 자료를 사용합니다.

```powershell
cd research/weather_observation_supplement
python -m pip install -r requirements.txt
python scripts/predict_weather_supplement.py --model model --input data/inference_example.csv --output my_weather_prediction.csv
python scripts/retrain_weather_supplement.py --bundle . --output my_weather_refit
```

보완 모형의 노트북 `notebooks/weather_observation_supplement.ipynb`도 위에서 아래로 실행합니다. `RUN_REFIT=True`로 전체 13곳·세 목표를 재학습할 수 있습니다. 별도 경로에 복제해 세 모델 재학습과 예측의 정확한 일치를 확인했습니다. 포함 예제는 실행 검증이며 독립 평가가 아닙니다.

## 폴더와 자료

| 경로 | 내용 |
| --- | --- |
| data/ · model/ · code/ | 기존 최종 학습 자료·모델·학습 및 추론 진입점 |
| src/ · scripts/ · notebooks/ | 처리·개발·검산 소스와 실행 노트북 |
| research/weather_observation_supplement/ | 새 세 기상 모형·학습 448,298행·예제·환경·노트북·검산 |
| research/latest/road_weather_review_20261031_v1/ | BIAS·MAE·RMSE·상관 126행 CSV와 목표별 지역 제외 10분 예측 |
| research/latest/weather_segment_projection_20261031_v1/ | 843구간·두 겨울 요약, 202,320행 일별 추정, GIS·검산 |
| research/latest/weather_projection_review_20261031_v2/ | 동일 변수에 같은 색 범위를 쓴 지도·노선별 요약 |
| exports/ · figures/ | 기존 500m·1km 추정·10분 결빙 예측·일별 성능·지도·Shapefile |
| demo/ | 실제 화면 조작 영상·추론 확인 영상·오프라인 탐색 |
| reports/ · docs/ · validation/ · provenance/ · licenses/ | 보고서·설명·실행 검증·이력·자료 이용조건 |

500m 구간 기상 29,134,080개 10분 행은 원 작업 공간에 보존하고 ZIP에는 일별·겨울별 집계와 GIS를 포함했습니다. 기상 미관측 평가 4곳의 10분 예측은 포함합니다. 전체 구간 입력 재구축은 원 비공개 작업 공간이 필요하지만 세 최종 기상 모형 재학습·예제 추론은 이 묶음만으로 가능합니다.

구간 분할은 독립 관측 수가 아닙니다. 새 출처 ASOS 172 사용 구간과 학습 범위 밖 입력을 표시했습니다. 기존 저온·수분 조건 노출과 공식 목록 비교는 보존했습니다. 추정 기상값·상관을 결빙확률·사고확률·인과효과·공식 위험등급으로 해석하지 않습니다. 318개 기존 현장 확인 후보는 방향별 8개 넓은 연속 구간입니다.

최상위 manifest가 현재 보고서·노트북을 지정합니다. 날짜별 문서·과거 README는 당시 이력입니다. 대회 제출 안내에 따라 문서자료·모델자료를 각각 단일 폴더 ZIP으로 준비했습니다. 실제 접수는 하지 않았으며 마감일은 제공 공지 본문에서 확인되지 않았습니다. 대회 자료·모델은 허용된 비공개 심사 범위에서 사용합니다. AI의 검산과 참가자의 직접 판단은 구별해 기록했습니다.
'''


def source_checks():
    frozen=verify_preserved();verify_directory(OLD)
    report=read(REPORT/'build_receipt.json');visual=read(REPORT/'visual_review.json')
    assert visual['status']=='passed' and visual['pdf_sha256']==report['pdf_sha256']==sha(REPORT/'analysis_report_v9.pdf')
    for name,h in report['sources'].items():assert sha(ROOT/name)==h,name
    runtime=read(P/'weather_supplement_validation_20261031_v1/receipt.json')
    assert runtime['status']=='weather_supplement_verified' and runtime['source_receipt_sha256']==sha(SUPPLEMENT/'receipt.json')
    for name,h in read(SUPPLEMENT/'receipt.json')['files'].items():assert sha(SUPPLEMENT/name)==h,name
    for name in STUDIES[:3]+[STUDIES[4]]:
        audit=read(P/name/'independent_verification.json')
        assert audit['status']=='passed' and audit['summary_sha256']==sha(P/name/'summary.json'),name
    return frozen


def preserved():
    records=read(OLD/'manifest.json')['files'];names=[]
    for name,record in records.items():
        if name in UPDATED:continue
        assert sha(OUT/name)==record['sha256'],name;names.append(name)
    return names


def manifest(folder,channel):
    path=folder/'manifest.json'
    if path.exists():
        i=1
        while (folder/f'provenance/v9_previous_manifest_{i:02d}.json').exists():i+=1
        destination=folder/f'provenance/v9_previous_manifest_{i:02d}.json';destination.parent.mkdir(exist_ok=True);path.rename(destination)
    records={p.relative_to(folder).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in folder.rglob('*')
             if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.relative_to(folder).parts[0]!='local_review'}
    value=dict(package_label='v9',channel=channel,status='private_review_candidate',at_utc=now(),files=records,
               current_report='reports/analysis_report_v9.pdf',competition_submitted=False)
    if channel=='model':value.update(current_notebook='notebooks/submission_review_v9.ipynb',production_model_version='v3',
        icing_version='v2',production_model_changed=False,weather_supplement='research/weather_observation_supplement')
    write(path,value)


def notebooks():
    prior=nb.read(OLD/'notebooks/submission_review_v8.ipynb',as_version=4)
    original=[c for c in prior.cells if c.cell_type=='code']
    for cell in prior.cells:
        if cell.cell_type=='markdown':cell.source=cell.source.replace(' · v8',' · v9').replace('analysis_report_v8.pdf','analysis_report_v9.pdf')
    prior.cells.append(nb.v4.new_markdown_cell('''## 세 도로 기상 모형과 구간 지도

`weather_review_v9.ipynb`는 포함된 개발 지표·구간 기상 집계·GIS 출처를 검토합니다.
새 세 모형의 학습·추론은 `../research/weather_observation_supplement/README.md`와 해당 폴더의 노트북을 실행합니다.
기존 노면온도·결빙 판정과 이 노트북의 5코드 셀은 보존합니다.'''))
    assert original==[c for c in prior.cells if c.cell_type=='code'];nb.write(prior,OUT/'notebooks/submission_review_v9.ipynb')
    new=nb.v4.new_notebook(metadata=prior.metadata,cells=[nb.v4.new_markdown_cell('''# 도로 기상 보완과 500m 구간 결과

위에서 아래로 실행합니다. 포함 집계의 해시·지표·지도와 범위 표시를 확인하며 API·보호 정답을 사용하지 않습니다.
전체 세 기상 모형 재학습은 별도 보완 폴더 노트북에서 수행합니다. 개발 지역 재사용 결과를 새 독립 성능으로 해석하지 않습니다.'''),
        nb.v4.new_code_cell('''from pathlib import Path
import hashlib, json
import pandas as pd
from IPython.display import display, Image
ROOT=next(p for p in [Path.cwd(),*Path.cwd().parents] if (p/'extended_training_plan.json').exists())
P=ROOT/'research/latest'
read=lambda p: json.loads(p.read_text(encoding='utf8'))
for name in ['road_weather_transfer_20261031_v1','weather_calibration_controls_20261031_v1','transferred_air_icing_20261031_v1','weather_segment_projection_20261031_v1']:
    audit=read(P/name/'independent_verification.json')
    assert audit['status']=='passed' and audit['summary_sha256']==hashlib.sha256((P/name/'summary.json').read_bytes()).hexdigest()
metrics=pd.read_csv(P/'road_weather_review_20261031_v1/observation_estimation_metrics.csv')
assert len(metrics)==126
display(metrics)
display(Image(filename=str(P/'road_weather_review_20261031_v1/mae_comparison.png')))'''),
        nb.v4.new_markdown_cell('''## 기상 추정 지도와 가용 범위

각 변수의 두 겨울은 같은 색 범위입니다. 검은 점은 학습에 등장하지 않은 ASOS 172 출처입니다.
학습 입력 범위 이탈은 예측오차나 신뢰도를 뜻하지 않습니다. 기존 결빙 판정·노면온도·조건 노출은 보존했습니다.'''),
        nb.v4.new_code_cell('''directory=P/'weather_segment_projection_20261031_v1'
summary=read(directory/'summary.json')
for name in ['weather_segments_500m.csv','weather_segment_daily.csv.gz','weather_and_preserved_road_estimates.csv','weather_segments.gpkg']:
    assert hashlib.sha256((directory/name).read_bytes()).hexdigest()==summary['files'][name]
segments=pd.read_csv(directory/'weather_segments_500m.csv')
days=pd.read_csv(directory/'weather_segment_daily.csv.gz')
assert len(segments)==1686 and segments.seg_id.nunique()==843 and len(days)==202320
assert not summary['classification_changed'] and not summary['risk_threshold_changed']
display(pd.read_csv(P/'weather_projection_review_20261031_v2/route_weather_summary.csv'))
display(segments[['seg_id','winter','new_asos_source_domain','input_range_outside_fraction']].head())
display(Image(filename=str(P/'weather_projection_review_20261031_v2/weather_projection_two_winters.png')))
print('Two winter GIS:',directory/'weather_segments.gpkg')''')])
    nb.validate(new);nb.write(new,OUT/'notebooks/weather_review_v9.ipynb')


def prepare():
    if OUT.exists():raise FileExistsError('Preserve previous candidate')
    frozen=source_checks()
    for name in read(OLD/'manifest.json')['files']:copy(OLD/name,OUT/name)
    copy(OLD/'manifest.json',OUT/'provenance/v8_manifest.json');copy(OLD/'README.md',OUT/'README_v8.md')
    command=['git','-c','safe.directory='+ROOT.as_posix(),'ls-files','--cached','--others','--exclude-standard','-z']
    sources={}
    for name in sorted(set(filter(None,subprocess.check_output(command,cwd=ROOT).decode('utf8').split('\0')))):
        if not name.startswith(('src/','scripts/','tests/','config/','docs/','notebooks/')):continue
        path=ROOT/name;target=OUT/name
        if not path.is_file() or path.suffix not in ['.py','.md','.json','.ipynb','.png','.jpg','.txt','.yml','.yaml']:continue
        if target.exists() and name not in UPDATED:continue
        copy(path,target);sources[name]=sha(path)
    for name in ['AI_USAGE.md','README.md']:
        copy(ROOT/name,OUT/('README_repository.md' if name=='README.md' else name))
    for path in SUPPLEMENT.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:copy(path,OUT/'research/weather_observation_supplement'/path.relative_to(SUPPLEMENT))
    for name in STUDIES:
        for path in (P/name).iterdir():
            if not path.is_file() or path.suffix not in ['.json','.csv','.gz','.gpkg','.png']:continue
            copy(path,OUT/'research/latest'/name/path.name)
    copy(P/'weather_supplement_validation_20261031_v1/receipt.json',OUT/'validation/weather_supplement_full_refit.json')
    for name in ['cli.log','notebook_full_refit.log']:
        copy(P/'weather_supplement_validation_20261031_v1'/name,OUT/'validation/weather_supplement'/name)
    copy(REPORT/'analysis_report_v9.pdf',OUT/'reports/analysis_report_v9.pdf')
    copy(REPORT/'build_receipt.json',OUT/'validation/v9_report_build.json');copy(REPORT/'visual_review.json',OUT/'validation/v9_report_visual.json')
    (OUT/'README.md').write_text(MODEL_README,encoding='utf8');notebooks();old=preserved()
    write(OUT/'provenance/v9_preparation.json',dict(at_utc=now(),source_files=sources,preservation=frozen,
        preserved_v8_files=old,supplement_receipt_sha256=sha(SUPPLEMENT/'receipt.json'),
        point_ten_minute_caches_included=False,production_model_changed=False))
    manifest(OUT,'model');verify_directory(OUT);print('V9 PREPARED',len(old),'v8 files preserved',flush=True)


def verify():
    source_checks();old=preserved();verify_directory(OUT)
    target=OUT/'validation/v9_delivery.json'
    if target.exists():raise FileExistsError('Preserve verification')
    local=OUT/'local_review';local.mkdir(exist_ok=True)
    i=1
    while any(local.glob(f'v9_{i:02d}*')):i+=1
    prefix=f'v9_{i:02d}';weather=OUT/'research/weather_observation_supplement'
    env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
    commands=[('core',OUT,[sys.executable,'scripts/review_submission_bundle.py','--smoke','--output',f'local_review/{prefix}.json']),
        ('weather_review',OUT,[sys.executable,'scripts/check_notebook.py','notebooks/weather_review_v9.ipynb']),
        ('weather_cli',weather,[sys.executable,'scripts/predict_weather_supplement.py','--model','model','--input','data/inference_example.csv','--output',str(local/(prefix+'_weather.csv'))]),
        ('weather_notebook',OUT,[sys.executable,'scripts/check_notebook.py',str(weather/'notebooks/weather_observation_supplement.ipynb')])]
    for name,cwd,command in commands:
        run=subprocess.run(command,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
        log=local/(prefix+'_'+name+'.driver.log');log.write_bytes(run.stdout);assert run.returncode==0,str(log)
    result=read(local/(prefix+'.json'));assert result['prediction_rows_identical']==144
    assert result['notebook']=='notebooks/submission_review_v9.ipynb'
    a=pd.read_csv(local/(prefix+'_weather.csv'),float_precision='round_trip')
    b=pd.read_csv(weather/'data/expected_predictions.csv',float_precision='round_trip')
    pd.testing.assert_frame_equal(a,b,check_exact=True)
    for path in local.glob(prefix+'*'):copy(path,OUT/'validation/v9_execution'/path.name)
    errors=inspect_documents(OUT,[p.relative_to(OUT).as_posix() for p in OUT.rglob('*.md')]);assert not errors,'\n'.join(errors)
    source_checks();preserved()
    write(target,dict(status='v9_delivery_verified',at_utc=now(),preserved_v8_files=len(old),execution=result,
        weather_prediction_rows_identical=len(a),current_notebook_code_cells=5,weather_review_code_cells=2,
        weather_supplement_notebook_code_cells=3,weather_full_refit_previously_verified=True,
        production_model_changed=False,competition_submitted=False))
    manifest(OUT,'model');verify_directory(OUT);print('V9 VERIFIED',flush=True)


def package():
    source_checks();preserved();verify_directory(OUT)
    assert read(OUT/'validation/v9_delivery.json')['status']=='v9_delivery_verified'
    if CHANNELS.exists():raise FileExistsError('Preserve archives')
    CHANNELS.mkdir();documents=CHANNELS/'icy_road_documents';documents.mkdir()
    copy(REPORT/'analysis_report_v9.pdf',documents/'reports/analysis_report_v9.pdf')
    for source,target in [('weather_transfer_20261031.png','weather_accuracy.png'),('weather_projection_20261031.png','weather_maps.png'),
                          ('inventory_comparison_20261031_v3.png','official_inventory_comparison.png')]:
        copy(ROOT/'docs/images'/source,documents/'figures'/target)
    copy(ROOT/'docs/delivery/RISK_CRITERIA_20261031.md',documents/'RISK_CRITERIA.md')
    copy(OUT/'data/condition_evidence_criteria.csv',documents/'data/condition_evidence_criteria.csv')
    copy(P/'road_weather_review_20261031_v1/observation_estimation_metrics.csv',documents/'data/observation_estimation_metrics.csv')
    (documents/'README.md').write_text('''# 문서자료 · 도로 기상·노면온도 추정과 결빙 조건

[17쪽 통합 보고서](reports/analysis_report_v9.pdf)에 문제·자료·모형·실험·평가·기대 활용·한계를 설명합니다.
[기상 추정 오차](figures/weather_accuracy.png), [두 겨울 기상 지도](figures/weather_maps.png),
[공식 취약구간 비교](figures/official_inventory_comparison.png), [조건 기준표](RISK_CRITERIA.md)와 세 기상 목표의 평가 CSV를 포함합니다.

기온·습도·풍속 MAE는 개발 4지역 제외 비교에서 AWS 우선보다 22.10·10.02·42.67% 감소했습니다.
기존 노면온도 MAE 개선은 13.66%입니다. 기상·온도 개선은 결빙 개선을 뜻하지 않으며 현재 결빙 F1 0.026554는 기온 기준선 0.036601보다 낮습니다. 반복 개발 점수로 공식 성적이 아닙니다.

지도는 추정 기상·조건 노출·최신 공식 목록의 비교입니다. 사고확률·공식 위험등급·측량 위치를 검증한 결과는 아닙니다.
실행 코드·학습 자료·모델·환경·노트북·데모·GIS·10분 평가 예측은 별도 모델자료 ZIP에 있습니다.
AI 지원·참가자 기여·검토한 대안은 보고서와 모델자료 AI_USAGE.md에 기록했습니다.

이 ZIP은 단일 최상위 폴더의 비공개 로컬 검토본입니다. 대회 접수는 하지 않았으며 제공 공지 본문에서 마감일은 확인되지 않았습니다.
''',encoding='utf8')
    manifest(documents,'documents')
    secret_values=[]
    for line in (ROOT/'secret.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            value=line.split('=',1)[1].strip().strip('\"\x27')
            if len(value)>=12:secret_values.append(value.encode())
    for folder in [OUT,documents]:
        records=read(folder/'manifest.json')['files']
        errors=inspect_documents(folder,[n for n in records if n.endswith('.md')]);assert not errors,'\n'.join(errors)
        for name in records:
            path=folder/name
            assert path.suffix not in ['.env','.pem','.key','.hwp'] and '/.git/' not in '/'+name
            if path.suffix in ['.py','.json','.md','.txt','.ipynb','.html','.js','.log','.yml','.csv']:
                data=path.read_bytes();assert not any(value in data for value in secret_values),name
                assert not re.search(rb'(?:github_pat_[A-Za-z0-9_]{40,}|RGAPI-[A-Za-z0-9-]{30,}|sk-[A-Za-z0-9_-]{30,})',data),name
    results={'documents':archive(documents,CHANNELS/'icy_road_documents.zip','icy_road_documents'),
             'model':archive(OUT,CHANNELS/'icy_road_model.zip','icy_road_model')}
    source_checks()
    write(CHANNELS/'submission_receipt.json',dict(status='two_channel_archives_verified',at_utc=now(),archives=results,
        model_source=OUT.relative_to(ROOT).as_posix(),preserved_v8_files=len(preserved()),
        execution=read(OUT/'validation/v9_delivery.json'),competition_submitted=False,production_model_changed=False))
    print(json.dumps(results,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',required=True,choices=['prepare','verify','package'])
    globals()[parser.parse_args().stage]()
