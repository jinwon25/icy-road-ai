"""검토된 보고서와 별도 연구 재현 자료를 기존 실행 후보에 합쳐 새 비공개 묶음 생성."""
from datetime import datetime,timezone
from pathlib import Path
import json
import shutil
import subprocess
import sys
import zipfile
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write,preservation
from src.data_source import sha256_file as sha
from src.method_blending import domain,ALLOWED
from src.submission_runtime import FEATURES,WATER

PRIVATE=ROOT/'outputs/private'
BASE=PRIVATE/'submission_candidate_unpack_20261014_v1'
OUT=PRIVATE/'submission_candidate_20261014_v2'
REPORT=PRIVATE/'report_upgrade_20261014_v2'
QUALITY=PRIVATE/'model_report_quality_20261014_v1'
RESEARCH=PRIVATE/'freezing_weight_20261014_v1'
DIAG=PRIVATE/'submission_diagnostics_20261014_v1'


def main():
    if OUT.exists():raise FileExistsError('Preserve previous deliveries')
    assert BASE.exists()
    assert read(QUALITY/'quality_receipt.json')['status']=='model_report_quality_checks_passed'
    assert read(REPORT/'visual_review.json')['status']=='all_12_pages_visually_reviewed'
    frozen=preservation();OUT.mkdir()
    old_manifest=read(BASE/'candidate_manifest.json')
    for rel,item in old_manifest['files'].items():
        assert sha(BASE/rel)==item['sha256'],rel
    for name,args in [('repository_final',['scripts/check_repository.py','--include-untracked']),
                      ('markdown_final',['scripts/check_markdown.py','--include-untracked','--render-dir',str(QUALITY/'rendered')])]:
        result=subprocess.run([sys.executable,'-X','utf8',*args],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (QUALITY/(name+'.log')).write_bytes(result.stdout)
        print(name,result.returncode,result.stdout.decode('utf-8',errors='replace')[-500:],flush=True)
        if result.returncode:raise RuntimeError('Current source check failed: '+name)
    for path in BASE.rglob('*'):
        if not path.is_file():continue
        rel=path.relative_to(BASE)
        if rel.as_posix() in ['manifest.json','candidate_manifest.json','README.md']:continue
        if rel.parts[0] in ['src','scripts','config','tests','notebooks','docs','.github']:continue
        if rel.suffix=='.pdf' and rel.parts[0]=='reports':
            target=OUT/'reports/archive'/path.name
        else:target=OUT/rel
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    for folder in ['src','scripts','config','tests','notebooks','docs','.github']:
        for path in (ROOT/folder).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc':
                target=OUT/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    shutil.copy2(ROOT/'AI_USAGE.md',OUT/'AI_USAGE.md')
    shutil.copy2(ROOT/'requirements-delivery.txt',OUT/'requirements-delivery.txt')
    report_dest=OUT/'reports/current'
    report_dest.mkdir()
    for path in REPORT.rglob('*'):
        if path.is_file() and 'preview' not in path.relative_to(REPORT).parts and path.name!='extracted_text.txt':
            target=report_dest/path.relative_to(REPORT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    for source,dest in [(RESEARCH,OUT/'research/freezing_weight'),(DIAG,OUT/'research/diagnostics')]:
        for path in source.rglob('*'):
            if path.is_file():
                target=dest/path.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    columns=['station','time','road_temp',*FEATURES,*[c for c in WATER if c not in FEATURES]]
    input_path=PRIVATE/'weather_distance_20261010_v1/development_inputs.parquet'
    data=domain(pd.read_parquet(input_path,columns=columns));assert set(data.station)==ALLOWED
    input_copy=OUT/'data/research_weather_inputs.parquet'
    data.to_parquet(input_copy,index=True,compression='zstd')
    pd.testing.assert_frame_equal(pd.read_parquet(input_copy),data)
    write(OUT/'research/freezing_weight/delivery_inputs.json',dict(weather_input_sha256=sha(input_copy),
        original_input_sha256=sha(input_path),first_winter_only=True,allowed_station_count=23,
        excluded_outcomes_present=False,source_columns=columns))
    shutil.copy2(ROOT/'scripts/reproduce_freezing_delivery.py',OUT/'code/reproduce_freezing.py')
    (OUT/'README.md').write_text('''# 전북 고속도로 노면온도 추정과 결빙 조건 분석

공공 기상으로 미관측 도로의 노면온도를 추정하고 저온·수분 조건을 구간 지도에 연결한 비공개 대회 제출 후보입니다. 현재 모델과 새 가중 학습 연구를 함께 제공하되 실행 모델은 검증된 기존 2종 평균으로 유지합니다.

## 먼저 읽을 자료

- [최신 분석 보고서](reports/current/전북_고속도로_결빙_분석_보고서.pdf): 12쪽. 지점별 결과·실제 오판·가중 모델 비교·날짜와 지역 민감도·지도·문헌 13개·실행 방법
- [편집 가능한 원고](reports/current/전북_고속도로_결빙_분석_보고서.md)
- [모델·보고서 변경 근거](docs/MODEL_REPORT_UPGRADE_20261014.md)
- [AI 활용과 주요 선택](AI_USAGE.md)

이전 6쪽 보고서는 `reports/archive/`에 보존합니다. 이전 문서의 1.200531°C는 전체 행 MAE이며, 지점 균등 MAE는 1.200440°C입니다.

## 모델과 결과

`model/`에는 첫 겨울 허용 23곳의 397,126행으로 적합한 MSE·MAE 모델이 있습니다. 평균 추정온도와 수분 조건으로 판정하며 입력 부족은 null입니다. 보호 3곳 두 겨울 출력 103,680행 중 18행이 입력 부족입니다.

개발 9곳의 일별 지점 평균 F1은 0.030633입니다. 공식 보호 지점 점수가 아니며, Recall의 유효 지점은 8곳입니다. `research/freezing_weight/`의 새 20모델은 저온 오차를 줄였지만 기존 탐지 사건을 놓쳐 제출 모델로 채택하지 않았습니다.

## 실행 환경과 명령

Python 3.11, CPU, 최대 계산 스레드 2개를 사용합니다. GPU/CUDA는 필요하지 않습니다. `environment.json`과 버전이 고정된 `requirements.txt`를 참고하세요. 설치 이후 포함된 자료의 추론·학습·검산은 외부 접속 없이 실행합니다.

```powershell
python -m pip install -r requirements.txt
python -X utf8 code/predict.py --input data/weather_example.csv --output validation/new_example.csv
python -X utf8 code/train.py --output validation/new_models
python -X utf8 code/export_predictions.py --kind protected --output validation/target_csv
python -X utf8 code/reproduce_development.py --output validation/new_metrics
python -X utf8 code/reproduce_freezing.py --output validation/new_freezing_replay
```

기존 출력이 있으면 중단합니다. CSV는 무손실 부동소수점 파서로 읽습니다. 구간 CSV는 `code/export_predictions.py --kind segment --scale 500 --id 8eabed369e9c40e7 --output validation/segment_csv`로 만들 수 있습니다. 구간 전체를 펼치려면 `--id`를 생략합니다.

## 파일 구성

| 경로 | 내용 |
| --- | --- |
| `data/` | 대표 모델 학습 표, 예제 입력, 공통 기상·예측 그룹, 위치 색인, 보호 예측, 개발 검산 자료 |
| `data/research_weather_inputs.parquet` | 새 연구 재현용 허용 23곳 첫 겨울의 온도·기상 입력. 보호·개봉 평가·둘째 겨울 정답 없음 |
| `model/`, `code/` | 실행 모델과 로컬 추론·재학습·내보내기·개발/연구 재현 명령 |
| `research/freezing_weight/` | 새 가중 모델 20개, 제외 그룹별 예측, 선택·일별 지표·사건·검산 기록 |
| `research/diagnostics/` | 현재 후보 오류 분해, 6,000회 날짜 블록 민감도, 실제 하루 사례 |
| `reports/current/` | 최신 PDF와 편집 원고, 표·그림·문헌 적용·화면 검토 기록 |
| `figures/` | 두 겨울 500 m·1 km GPKG·Shapefile·JPG와 열 사전 |
| `src/`, `scripts/`, `config/`, `tests/`, `notebooks/` | 전체 분석 코드·설정·검사·노트북. 역사적 연구의 원본 GIS/기상 재구축은 기존 작업 공간 필요 |
| `demo/` | 로컬 HTML과 실제 브라우저 화면 녹화. 학습 영역 예제이며 독립 성능 사례 아님 |
| `validation/`, `manifest.json` | 검증 기록과 파일별 SHA-256 |

`code/reproduce_freezing.py`는 포함 자료만으로 20개 저장 모델, 예측 1,242,056값, 32개 지표 보고서를 다시 확인합니다. 최초 연구의 전체 내부 선택·재적합 감사는 연구 폴더 영수증에 보존하며 원래 스크립트는 원본 작업 공간 경로를 사용합니다.

## 제출 전에 남은 조건

최종 CSV의 열·행키·파일명·결측 표현과 결과 제출 날짜는 주최 측 추가 안내에 맞춰야 합니다. 참가신청 종료 11월 6일을 결과 제출 마감으로 사용하지 않습니다. 현재 지도는 추정 저온·수분 조건 노출이며 검증된 사고확률이나 공식 A/B/C 등급이 아닙니다.

대회 원본·파생 자료는 참가 권한 안에서 비공개로 취급합니다. 원본 ZIP·작성 신청서·서명·인증정보·Git 이력·보호 정답·이미 개봉한 평가 정답은 포함하지 않습니다. 이번 묶음 생성은 공식 제출이나 모델의 최종 승격이 아닙니다.
''',encoding='utf-8')
    # 실행 후보의 저장 모델·공통 기상·기존 예측을 바꾸지 않았는지 검증한다.
    immutable=[]
    for path in BASE.rglob('*'):
        if not path.is_file():continue
        rel=path.relative_to(BASE);name=rel.as_posix()
        if name.startswith(('model/','data/weather_groups/','data/prediction_groups/')) or name in ['data/protected_predictions_10min.csv.gz','data/point_prediction_index.csv','data/prediction_group_manifest.json']:
            assert sha(path)==sha(OUT/rel),name
            immutable.append(name)
    for name,args in [('research_replay',['code/reproduce_freezing.py','--output','validation/new_freezing_replay']),
                      ('candidate_replay',['code/predict.py','--input','data/weather_example.csv','--output','validation/report_upgrade_example.csv'])]:
        result=subprocess.run([sys.executable,'-X','utf8',*args],cwd=OUT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (QUALITY/(name+'.log')).write_bytes(result.stdout)
        print(name,result.returncode,result.stdout.decode('utf-8',errors='replace')[-400:],flush=True)
        if result.returncode:raise RuntimeError('Delivery replay failed: '+name)
    expected=pd.read_csv(OUT/'data/example_predictions.csv',float_precision='round_trip',dtype={'station':str})
    actual=pd.read_csv(OUT/'validation/report_upgrade_example.csv',float_precision='round_trip',dtype={'station':str})
    pd.testing.assert_frame_equal(actual,expected)
    shutil.copy2(QUALITY/'quality_receipt.json',OUT/'validation/model_report_quality.json')
    write(OUT/'validation/model_report_delivery.json',dict(status='revised_report_and_research_delivery_prepared',
        created_at_utc=datetime.now(timezone.utc).isoformat(),immutable_candidate_files=len(immutable),
        new_research_models=20,active_candidate_models=2,model_promoted=False,official_submission=False,
        original_package=str(BASE.relative_to(ROOT)),prior_manifest_sha256=sha(BASE/'candidate_manifest.json')))
    files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*'))
           if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    write(OUT/'manifest.json',dict(version=2,created_at_utc=datetime.now(timezone.utc).isoformat(),
        status='private_submission_candidate_with_research',files=files))
    archive=OUT.with_suffix('.zip')
    if archive.exists():raise FileExistsError('Preserve existing archive')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for rel in [*files,'manifest.json']:z.write(OUT/rel,rel)
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist())==set(files)|{'manifest.json'}
        for rel,item in files.items():
            import hashlib
            assert hashlib.sha256(z.read(rel)).hexdigest()==item['sha256'],rel
    assert preservation()==frozen
    write(QUALITY/'delivery_receipt.json',dict(status='model_report_upgrade_packaged_and_verified',
        completed_at_utc=datetime.now(timezone.utc).isoformat(),archive=str(archive.relative_to(ROOT)),
        archive_sha256=sha(archive),archive_bytes=archive.stat().st_size,files=len(files)+1,
        immutable_candidate_files=len(immutable),new_research_models=20,model_promoted=False,
        official_submission=False,public_release=False,old_frozen_files=frozen[0],reserved_frozen_files=frozen[1]))
    print('완료',archive.stat().st_size,len(files)+1,sha(archive),flush=True)


if __name__=='__main__':main()
