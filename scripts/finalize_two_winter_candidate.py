"""두 겨울 후보의 현재 자료를 동기화하고 재현 검증 뒤 새 ZIP을 봉인한다."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.submission_archive import verify_archive
from scripts.upgrade_two_winter_candidate import OUT,EXPERIMENT,manifest
from scripts.evaluate_method_blending import preservation

def read(p):return json.loads(p.read_text('utf-8'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
def copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)

def assets():
    for name in ['award_ice','two_winter','runtime_metrics','delivery_tables']:
        copy(ROOT/f'src/{name}.py',OUT/f'src/{name}.py')
    names=['evaluate_award_ice','audit_award_ice','prepare_two_winter_development','evaluate_two_winter','audit_two_winter',
        'audit_two_winter_runtime','upgrade_two_winter_candidate','complete_two_winter_delivery','render_award_review',
        'export_delivery_tables','finalize_two_winter_candidate','check_notebook']
    for name in names:copy(ROOT/f'scripts/{name}.py',OUT/f'scripts/{name}.py')
    for name in ['award_ice','two_winter','runtime_metrics','delivery_tables']:
        copy(ROOT/f'tests/test_{name}.py',OUT/f'tests/test_{name}.py')
    for name in ['award_ice_experiment_20261024','two_winter_development_20261024','temperature_adoption_20261024']:
        copy(ROOT/f'config/{name}.json',OUT/f'config/{name}.json')
    for name in ['AI_USAGE.md','docs/STATUS.md','docs/README.md','docs/validation/VALIDATION_PROTOCOL.md',
        'docs/delivery/AWARD_UPGRADE_20261024.md','docs/delivery/CSV_CONTRACT.md','scripts/README.md','config/README.md']:
        copy(ROOT/name,OUT/name)
    copy(EXPERIMENT/'audit.json',OUT/'research/two_winter/audit_before_runtime_correction.json')
    copy(EXPERIMENT/'audit_runtime.json',OUT/'research/two_winter/audit.json')
    copy(EXPERIMENT/'runtime_predictions.parquet',OUT/'research/two_winter/audited_predictions.parquet')
    for name in ['receipt.json','training_inventory.csv']:
        copy(ROOT/'outputs/private/two_winter_development_20261024_v1'/name,OUT/'research/two_winter'/name)
    for name in ['summary.json','independent_audit.json','decisions.json']:
        source=ROOT/'outputs/private/award_ice_20261024_v1'/name
        if source.exists():copy(source,OUT/'research/award_ice'/name)
    old=OUT/'reports/history/report_before_two_winter.pdf'
    if not old.exists():copy(OUT/'reports/current/current_report.pdf',old)
    report=ROOT/'outputs/private/award_review_20261024_v4'
    if (report/'award_review.pdf').exists():
        copy(report/'award_review.pdf',OUT/'reports/current/current_report.pdf')
        copy(report/'render_receipt.json',OUT/'reports/current/render_receipt.json')
    card=read(OUT/'model/model_card.json');audit=read(EXPERIMENT/'audit_runtime.json')
    card['ice_validation']=audit['physical']['both'];card['physical_runtime_replay']=True
    card['missing_development_ice_predictions']=654
    write(OUT/'model/model_card.json',card)
    if not (OUT/'reports/history/README_before_two_winter.txt').exists():
        copy(OUT/'README.md',OUT/'reports/history/README_before_two_winter.txt')
    (OUT/'README.md').write_text('''# 두 겨울 노면온도·결빙 추정 제출 검토 후보

현재 검토 대상은 2026년 10월 24일 v2입니다. 비보호 23곳의 두 겨울로 최종 모델을 적합하고 전체 예측·지도·CSV·보고서·데모를 같은 모델로 갱신했습니다. 대회 제출·외부 공개는 하지 않았습니다.

## 먼저 확인할 결과

- [현재 6쪽 보고서](reports/current/current_report.pdf): 모델 비교, 온도 개선과 결빙 한계, 자료·검증 범위.
- [실험·결과·재현 설명](docs/delivery/AWARD_UPGRADE_20261024.md): 56건 비교와 최종 모델 2건 적합.
- [현재 검토 노트북](notebooks/two_winter_submission_review.ipynb): 학습 범위·모델 해시·실제 추론·개발 지표·CSV 검산.
- [현재 실행 예제](demo/index.html) · [실제 출력 시각화 영상](demo/two_winter_inference.mp4).
- [CSV 규약](docs/delivery/CSV_CONTRACT.md), `exports/manifest.json`, `figures/`의 500m·1km 지도.

동일 공간 제외 개발 온도 MAE는 두 겨울 통합 1.412816 → 1.326890°C로 6.08% 개선했습니다. 첫 겨울은 3.88% 악화했고 네 지역 통합 오차는 모두 개선했습니다. 결빙 F1은 0.026554로 기온 기준선 0.036392보다 낮고 Recall도 하락했습니다. 온도 개선을 결빙 탐지 우위나 입상 보장으로 표현하지 않습니다. 비보호 둘째 겨울을 개발에 편입했으므로 새 독립 평가가 아닙니다. 보호 3곳 정답은 사용하지 않았습니다.

## 실행

Python 3.11에서 압축을 새 폴더에 풀고 다음을 실행합니다. 출력 경로가 이미 있으면 보존을 위해 중단합니다.

```powershell
python -m pip install -r requirements-notebook.txt
python -X utf8 scripts/check_notebook.py notebooks/two_winter_submission_review.ipynb
python -X utf8 code/predict.py --input data/weather_example.csv --output validation/my_prediction.csv
python -X utf8 code/train.py --output validation/my_refit
```

기본 노트북은 재학습하지 않습니다. `code/train.py`는 포함된 793,149개 유효 온도 행으로 두 모델을 새 폴더에 재적합합니다. 추론·검산·최종 재학습에 인증정보·외부 API는 필요하지 않습니다. 전체 탐색 재실행은 원 비공개 작업 공간의 입력 경로가 필요합니다.

보호 103,680행 중 입력 부족 18행은 NA입니다. 1,266구간의 두 겨울 10분 결과는 `exports/point_prediction_index.csv`와 `exports/prediction_groups_10min.csv.gz`를 연결해 복원합니다. 공유 기상 그룹을 독립 검증 표본으로 세지 않습니다. 지도는 추정 저온·수분 조건 노출이며 관측 결빙률·사고확률이 아닙니다.

## 이전 자료와 현재 자료의 구분

`research/two_winter/audit.json`과 `audited_predictions.parquet`는 제출 runtime의 결측 처리까지 검산한 현재 결과입니다. `audit_before_runtime_correction.json`은 정정 전 감사이며 현재 지표에 사용하지 않습니다. 원 연구 결과·원본 해시는 보존합니다.

기존 `notebooks/submission_review.ipynb`, `analysis_review.ipynb`, `code/reproduce_baselines.py`, `code/reproduce_development.py`, 이전 PDF와 `demo/inference_demo.webm`, 이름에 two_winter가 없는 과거 검증 영수증은 이전 모델·연구의 기록입니다. 현재 실행·지표 진입점은 위 노트북입니다. 이전 README는 `reports/history/README_before_two_winter.txt`에 보존했습니다.

결과물 접수 날짜·방식과 최신 데모 요구는 확인이 남았습니다. 11월 6일은 확인한 참가신청 종료일입니다. 모델·자료·보고서의 검토와 실제 제출은 참가자가 수행합니다. [AI 활용 기록](AI_USAGE.md)
''','utf-8')
    manifest()

def verify():
    destination=OUT/'validation/two_winter_delivery.json'
    if destination.exists():raise FileExistsError('Preserve completed delivery verification')
    environment=os.environ.copy();environment.update(OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2',
        GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='safe.directory',GIT_CONFIG_VALUE_0=str(ROOT).replace('\\','/'))
    unit_log=OUT/'validation/two_winter_unit_tests.log'
    unit_text=unit_log.read_text('utf-8')
    assert 'Ran 300 tests' in unit_text and unit_text.rstrip().endswith('OK')
    checks=[dict(name='unit_tests',returncode=0,tests=300,log_sha256=sha(unit_log),command='python -X utf8 -m unittest discover -s tests -q')]
    commands=[(ROOT,['scripts/check_repository.py','--include-untracked'],'repository'),
        (ROOT,['scripts/check_markdown.py','--include-untracked'],'markdown'),
        (OUT,['scripts/check_notebook.py','notebooks/two_winter_submission_review.ipynb'],'notebook'),
        (OUT,['code/export_predictions.py','--kind','protected','--output','validation/two_winter_protected_export'],'protected_export'),
        (OUT,['code/export_predictions.py','--kind','segment','--scale','500','--id','8eabed369e9c40e7','--output','validation/two_winter_segment_export'],'segment_export')]
    for cwd,args,name in commands:
        run=subprocess.run([sys.executable,'-X','utf8',*args],cwd=cwd,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600)
        log=run.stdout.decode('utf-8',errors='replace');(OUT/f'validation/two_winter_{name}.log').write_text(log,'utf-8')
        print(name,run.returncode,log[-1200:],flush=True)
        assert run.returncode==0,name
        checks.append(dict(name=name,returncode=run.returncode,log_sha256=sha(OUT/f'validation/two_winter_{name}.log')))
    receipts=read(OUT/'model/fit_receipts.json')
    refits=[]
    for receipt in receipts:
        name=receipt['name']+'.joblib'
        assert sha(OUT/'model'/name)==sha(OUT/'validation/two_winter_refit'/name)==receipt['model_sha256']
        refits.append(dict(name=name,sha256=receipt['model_sha256'],byte_identical=True))
    exports=read(OUT/'exports/manifest.json');assert exports['development_scope']=='two_winter'
    for table in exports['tables']:assert sha(OUT/'exports'/table['file'])==table['sha256']
    report=read(OUT/'reports/current/render_receipt.json')
    assert report['visual_review_pending'] is False and report['pdf_sha256']==sha(OUT/'reports/current/current_report.pdf')
    frozen=preservation()
    write(destination,dict(status='two_winter_delivery_verified',checks=checks,standalone_refit=refits,
        export_tables=11,old_frozen_files=frozen[0],reserved_frozen_files=frozen[1],pdf_pages_visually_reviewed=6,
        protected_outcomes_used=False,new_independent_performance=False,competition_submitted=False,
        created_at_utc=datetime.now(timezone.utc).isoformat()))

def package():
    assert read(OUT/'validation/two_winter_delivery.json')['status']=='two_winter_delivery_verified'
    browser=read(OUT/'validation/two_winter_browser.json')
    assert browser['visual_review_pending'] is False and browser['html_sha256']==sha(OUT/'demo/index.html')
    archive=OUT.with_suffix('.zip')
    if archive.exists():raise FileExistsError('Preserve existing final archive')
    manifest();m=read(OUT/'manifest.json')
    for name in m['files']:
        assert not name.endswith(('.key','.pem','.env')) and '/.git/' not in '/'+name
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in sorted(m['files']):z.write(OUT/name,name)
        z.write(OUT/'manifest.json','manifest.json')
    verified=verify_archive(archive)
    receipt=dict(status='two_winter_archive_verified',archive=archive.name,bytes=archive.stat().st_size,
        sha256=sha(archive),files=len(verified['files']),manifest_sha256=sha(OUT/'manifest.json'),competition_submitted=False)
    write(archive.with_suffix('.receipt.json'),receipt);print(json.dumps(receipt,ensure_ascii=False),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['assets','verify','package'],required=True)
    globals()[parser.parse_args().stage]()
