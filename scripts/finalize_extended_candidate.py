"""현재 확장 후보의 재학습·산출물·문서 검증을 모아 새 ZIP을 봉인한다."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.submission_archive import verify_archive
from scripts.build_extended_candidate import OUT,PRIVATE,OLD,read,write,copy,manifest
from scripts.evaluate_method_blending import preservation


def refit():
    destination=OUT/'validation/refit_comparison.json'
    if destination.exists():raise FileExistsError('Preserve refit comparison')
    original=read(OUT/'model/refit_receipt.json');repeat=read(OUT/'validation/extended_refit/refit_receipt.json')
    assert original==repeat;checks=[]
    for record in original['models']:
        name=record['name']+'.joblib';assert sha(OUT/'model'/name)==sha(OUT/'validation/extended_refit'/name)==record['sha256']
        checks.append(dict(name=name,sha256=record['sha256'],byte_identical=True))
    write(destination,dict(status='independent_fixed_plan_refit_matches',all_models_byte_identical=True,models=checks,
        training_plan_sha256=sha(OUT/'extended_training_plan.json'),protected_outcomes_used=False))


def assets():
    selected=read(OUT/'research/extended/selection.json');r=selected['temperature_report']['regression'];base=1.3268902851932995
    comparison=PRIVATE/'extended_completion_20261024_v1';summary=read(comparison/'summary.json');plan=read(OUT/'extended_training_plan.json')
    for source in comparison.iterdir():
        if source.is_file():copy(source,OUT/'research/extended/comparison'/source.name)
    for study in ['thermal_classification_20261024_v1','terrain_classification_20261024_v1']:
        for source in (PRIVATE/study).iterdir():
            if source.is_file() and source.suffix in ['.json','.csv','.parquet']:copy(source,OUT/'research/extended'/study/source.name)
    for name in ['terrain_classification_audit_20261024_v1','thermal_classification_audit_20261024_v1']:
        copy(PRIVATE/name/'receipt.json',OUT/'validation/research_audits'/name/'receipt.json')
    for audit in selected['saved_model_audits']:
        source=ROOT/audit;copy(source,OUT/'validation/research_audits'/source.parent.name/source.name)
    for directory in ['docs','config','scripts','tests']:
        for source in (ROOT/directory).rglob('*'):
            if source.is_file() and source.suffix in ['.md','.json','.py'] and '__pycache__' not in source.parts:copy(source,OUT/source.relative_to(ROOT))
    for name in ['AI_USAGE.md','requirements-notebook.txt']:copy(ROOT/name,OUT/name)
    report=PRIVATE/'extended_review_20261024_v1'
    for source in report.iterdir():
        if source.is_file():copy(source,OUT/'reports/current'/('current_report.pdf' if source.name=='extended_review.pdf' else source.name))
    write(OUT/'model/model_card.json',dict(candidate=selected['selected'],temperature_feature_kind=plan['temperature_feature_kind'],
        components=[s for s in plan['models'] if s['role']=='temperature'],weights=plan['temperature_weights'],
        training_rows=793149,raw_training_rows=794545,training_stations=plan['allowed_stations'],periods=plan['periods'],
        development_temperature=selected['temperature_report'],icing_policy=selected['icing_policy'],
        icing_reference_temperature_column='icing_reference_temperature_c',component_spread_is_calibrated_uncertainty=False,
        independent_performance_qualified=False,protected_outcomes_used=False,external_pretrained_weights=False))
    body=f'''# 기상·열 이력 기반 노면온도 추정 제출 검토 후보

2026년 10월 24일 v3입니다. 허용 23곳의 두 겨울에서 유효 온도 793,149쌍으로 최종 모델을 학습했습니다. 같은 공간 제외 개발 자료에서 온도 MAE가 1.326890 → {r['pooled']['mae']:.6f}°C로 {1-r['pooled']['mae']/base:.2%} 감소했습니다. 반복 개발 결과이며 새 독립 평가나 공식 성적이 아닙니다.

## 먼저 확인할 결과

- [8쪽 현재 보고서](reports/current/current_report.pdf): 접근·비교·한계·문헌과 규정 확인 범위.
- [현재 실행 노트북](notebooks/extended_submission_review.ipynb): 실제 포함 자료·모델·추론·지표·CSV 검산.
- [현재 실행 화면](demo/index.html) · [실제 출력 시각화 영상](demo/extended_inference.mp4).
- [CSV 규약](docs/delivery/CSV_CONTRACT.md) · [공개 문헌·오픈소스 이용 검토](docs/research/OPEN_SOURCE_REVIEW_20261024.md).
- `research/extended/comparison/regression_registry.csv`: 확장 회귀 {summary['regression_candidates']}개 설정의 실제 결과. `research/extended/selection.json`: 채택 기준과 근거.

기상·열 이력·ASOS 태양 위치의 63개 입력을 사용합니다. 새 결빙 분류기는 사전 기준을 모두 충족하지 못해 v2 판정을 유지했습니다. 현재 온도는 `estimated_road_temp_c`, 결빙 판정에 실제 사용하는 별도 온도는 `icing_reference_temperature_c`입니다. 온도 개선을 결빙 성능 향상으로 해석하지 않습니다. 두 겨울 결빙 일별 지점 F1은 0.026554입니다.

## 실행

Python 3.11에서 새 폴더에 압축을 풀고 실행합니다. 기존 출력 폴더는 덮어쓰지 않습니다.

```powershell
python -m pip install -r requirements-notebook.txt
python -X utf8 scripts/check_notebook.py notebooks/extended_submission_review.ipynb
python -X utf8 code/predict.py --input data/weather_example.csv --output validation/my_prediction.csv --output-start 2024-12-15 --output-end 2024-12-16
python -X utf8 code/train.py --output validation/my_refit
```

예제는 12시간 이력을 포함한 216행을 먼저 계산하고 하루 144행만 내보냅니다. 학습 범위 내 실행 예제이며 성능평가가 아닙니다. 기본 노트북은 재학습하지 않습니다. 추론·최종 재학습·노트북 검산은 포함 자료만으로 실행되며 인증정보·외부 API가 필요하지 않습니다. `validation/refit_comparison.json`은 독립 재학습 모델의 파일 해시 일치를 기록합니다.

## 자료와 해석

보호 3곳의 두 겨울 예측 103,680행 중 입력 부족 18행은 NA입니다. 보호 정답은 없습니다. 1,266구간의 전체 시계열은 `exports/point_prediction_index.csv`와 `exports/prediction_groups_10min.csv.gz`를 `prediction_group`, `winter`로 연결합니다. 138개 공유 기상 그룹과 겹치는 구간을 독립 표본으로 세지 않습니다. CSV 11종과 공간 파일의 추정 온도 속성을 갱신했습니다.

지도의 저온·수분 조건 노출은 관측 결빙률·사고확률과 다릅니다. 모델 구성 간 차이는 보정된 신뢰구간이 아니며 단일 모델의 차이 0은 오차 0을 뜻하지 않습니다. 학습·선택의 지역 분리, 날짜 블록 민감도와 반복 개발의 한계는 보고서에 설명했습니다.

## 현재 실행과 연구 기록

현재 실행 진입점은 위 노트북·`code/predict.py`·`code/train.py`입니다. `scripts/`, `config/`, `docs/`에는 과거 연구의 소스·설정·당시 보고도 보존했습니다. `research/environment/`에는 원 연구 공간의 추가 개발·라이브러리 환경을 기록했습니다. 전체 탐색 재실행은 원 비공개 작업 공간의 입력 경로가 필요하며 이 묶음만으로 모든 과거 연구를 재실행한다고 주장하지 않습니다. 이전 ZIP은 원 작업 공간에서 보존합니다.

## 규정·이용 조건

[AI 활용 기록](AI_USAGE.md), `licenses/`, [10월 24일 규정 확인 범위](config/official_requirements_20261024.json)를 포함합니다. 외부 사전학습 가중치·보호 노면 정답·외부 예측 API를 사용하지 않았습니다. 최신 상세 규정·참가서약의 완전 재확인일은 10월 16일이며 10월 24일에는 공개 소개·목록만 재확인했습니다. 결과물 실제 마감·접수 방식·최신 데모 답변은 미확인입니다. 11월 6일은 참가신청 종료일입니다. 대회 제출·외부 공개는 수행하지 않았습니다.
'''
    (OUT/'README.md').write_text(body,'utf-8');manifest()


def verify():
    destination=OUT/'validation/extended_delivery.json'
    if destination.exists():raise FileExistsError('Preserve delivery verification')
    environment=os.environ.copy();environment.update(OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2',GIT_CONFIG_COUNT='1',
        GIT_CONFIG_KEY_0='safe.directory',GIT_CONFIG_VALUE_0=str(ROOT).replace('\\','/'))
    logpath=PRIVATE/'extended_final_unit_tests_20261024.log';unit=logpath.read_text('utf-8');match=re.search(r'(\d+) passed',unit)
    assert match and int(match[1])>=325 and 'FAILED' not in unit and 'ERROR collecting' not in unit;copy(logpath,OUT/'validation/extended_unit_tests.log')
    checks=[dict(name='unit_tests',tests=int(match[1]),returncode=0,log_sha256=sha(logpath))]
    commands=[(ROOT,['scripts/check_repository.py','--include-untracked'],'repository'),(ROOT,['scripts/check_markdown.py','--include-untracked'],'markdown'),
        (OUT,['scripts/check_notebook.py','notebooks/extended_submission_review.ipynb'],'notebook'),
        (OUT,['code/export_predictions.py','--kind','protected','--output','validation/extended_protected_export'],'protected_export'),
        (OUT,['code/export_predictions.py','--kind','segment','--scale','500','--id','8eabed369e9c40e7','--output','validation/extended_segment_export'],'segment_export')]
    for cwd,args,name in commands:
        run=subprocess.run([sys.executable,'-X','utf8',*args],cwd=cwd,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600)
        text=run.stdout.decode('utf-8',errors='replace');path=OUT/f'validation/extended_{name}.log';path.write_text(text,'utf-8');print(name,run.returncode,text[-1000:],flush=True)
        assert run.returncode==0,name;checks.append(dict(name=name,returncode=0,log_sha256=sha(path)))
    exports=read(OUT/'exports/manifest.json');assert exports['development_scope']=='extended_two_winter' and len(exports['tables'])==11
    assert exports['generator_sha256']==sha(OUT/'scripts/export_extended_delivery_tables.py')
    assert exports['aggregation_module_sha256']==sha(OUT/'src/delivery_tables.py')
    assert sha(OUT/'exports'/exports['candidate_manifest_snapshot'])==exports['candidate_manifest_sha256']
    for table in exports['tables']:assert sha(OUT/'exports'/table['file'])==table['sha256']
    for name,record in exports['sources'].items():assert sha(OUT/name)==record['sha256'],name
    report=read(OUT/'reports/current/render_receipt.json');browser=read(OUT/'validation/extended_browser.json')
    assert report['visual_review_pending'] is False and report['pdf_sha256']==sha(OUT/'reports/current/current_report.pdf')
    assert browser['visual_review_pending'] is False and browser['html_sha256']==sha(OUT/'demo/index.html')
    assert read(OUT/'validation/extended_maps.json')['status']=='all_spatial_numeric_attributes_readback_passed'
    for page,pattern in [(OUT/'README.md',r'\]\(([^)]+)\)'),(OUT/'demo/index.html',r'href="([^"]+)"')]:
        for link in re.findall(pattern,page.read_text('utf-8')):
            if re.match(r'^[a-z]+:',link) or link.startswith('#'):continue
            assert (page.parent/link.split('#',1)[0]).exists(),link
    assert read(OUT/'validation/refit_comparison.json')['all_models_byte_identical'];frozen=preservation()
    assert sha(OLD.with_suffix('.zip'))=='9837e3c5357ed4a4a613d44b6722d5dcebfaa5ac925c52c0b182743f8c7632a2'
    write(destination,dict(status='extended_delivery_verified',checks=checks,export_tables=11,pdf_pages_visually_reviewed=8,
        old_frozen_files=frozen[0],reserved_frozen_files=frozen[1],previous_zip_preserved=True,protected_outcomes_used=False,
        new_independent_assessment=False,competition_submitted=False,created_at_utc=datetime.now(timezone.utc).isoformat()))
    manifest()


def package():
    assert read(OUT/'validation/extended_delivery.json')['status']=='extended_delivery_verified'
    target=OUT.with_suffix('.zip')
    if target.exists():raise FileExistsError('Preserve existing archive')
    manifest();m=read(OUT/'manifest.json')
    for name in m['files']:assert not name.endswith(('.key','.pem','.env')) and '/.git/' not in '/'+name
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name in sorted(m['files']):archive.write(OUT/name,name)
        archive.write(OUT/'manifest.json','manifest.json')
    verified=verify_archive(target);receipt=dict(status='extended_archive_verified',archive=target.name,bytes=target.stat().st_size,
        sha256=sha(target),files=len(verified['files']),manifest_sha256=sha(OUT/'manifest.json'),competition_submitted=False)
    write(target.with_suffix('.receipt.json'),receipt);print(json.dumps(receipt,ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['refit','assets','verify','package'],required=True);globals()[p.parse_args().stage]()
