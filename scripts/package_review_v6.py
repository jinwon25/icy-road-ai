"""이전 실행 자산을 보존하고 최신 검토 요약·연구·검사 도구를 v6에 묶는다."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.blind_icing_validation import DEFAULT,verify as verify_blind,read,write,now,old_freezes
from scripts.check_markdown import inspect_documents
from scripts.review_submission_bundle import verify_directory
from src.submission_archive import verify_archive
from src.data_source import sha256_file as sha

PRIVATE=ROOT/'outputs/private';OLD=PRIVATE/'submission_candidate_20261025_v5';OUT=PRIVATE/'submission_candidate_20261025_v6'
OLD_SHA='0dcc1f5e2984ec3544b320f2bcec95ee4054a557dd2b320832de981c9d63e8e4'
STUDIES=['residual_icing_20261025_v1','causal_trend_20261025_v1','weather_information_20261025_v1','additive_icing_20261025_v1','rwis_anomaly_diagnosis_20261025_v1']


def copy(a,b):
    b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(a,b)


def source_checks():
    assert sha(OLD.with_suffix('.zip'))==OLD_SHA
    for study in STUDIES:
        a=read(PRIVATE/study/'audit.json');assert a['status']=='passed' and a['summary_sha256']==sha(PRIVATE/study/'summary.json')
    assert not read(PRIVATE/STUDIES[0]/'summary.json')['primary_success'] and not read(PRIVATE/STUDIES[1]/'summary.json')['primary_success']
    verify_blind(DEFAULT);assert old_freezes()==(47,549)


def core_check():
    original=read(OUT/'provenance/v5_manifest.json')['files'];names=[]
    for name,record in original.items():
        if name.startswith(('model/','data/','exports/','figures/','code/','src/','notebooks/','reports/','demo/','licenses/')) or name in ['extended_training_plan.json','requirements.txt','requirements-notebook.txt']:
            assert sha(OUT/name)==record['sha256'],name;names.append(name)
    return names


def manifest():
    files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in OUT.rglob('*') if p.is_file() and p!=OUT/'manifest.json' and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.relative_to(OUT).parts[0]!='local_review'}
    write(OUT/'manifest.json',dict(version=10,package_label='v6',status='private_review_candidate',at_utc=now(),files=files,production_model_version='v3',icing_version='v2',
        production_model_changed=False,independent_performance_qualified=False,competition_submitted=False,source_zip_sha256=OLD_SHA))


def sync_index():
    git=['git','-c','safe.directory='+ROOT.as_posix()]
    names=subprocess.check_output(git+['ls-files','-z'],cwd=ROOT).decode('utf8').split('\0');original=read(OUT/'provenance/v5_manifest.json')['files'];copied={}
    for name in filter(None,names):
        allowed=name.startswith(('docs/','config/','scripts/','src/','tests/','.github/','notebooks/')) or name in ['AI_USAGE.md','requirements-research.txt','README.md']
        if not allowed:continue
        if name in original and not (name.startswith('docs/') or name.endswith('.md')):continue
        target=OUT/('README_repository.md' if name=='README.md' else name);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(subprocess.check_output(git+['show',':'+name],cwd=ROOT));copied[name]=sha(target)
    write(OUT/'provenance/source_index_snapshot.json',dict(at_utc=now(),source='Git index; pre-existing unstaged user edits excluded',files=copied))


def prepare():
    if OUT.exists():raise FileExistsError('Preserve prior bundle')
    source_checks();old=read(OLD/'manifest.json')
    for name,record in old['files'].items():
        assert sha(OLD/name)==record['sha256'],name;copy(OLD/name,OUT/name)
    copy(OLD/'manifest.json',OUT/'provenance/v5_manifest.json');copy(OLD.with_suffix('.receipt.json'),OUT/'provenance/v5_archive_receipt.json')
    copy(OLD/'README.md',OUT/'README_v5.md');copy(OLD/'AI_USAGE.md',OUT/'AI_USAGE_v5.md')
    sync_index()
    for study in STUDIES:
        for name in ['plan.json','summary.json','audit.json','selection.json','input_equivalence.csv']:
            if (PRIVATE/study/name).exists():copy(PRIVATE/study/name,OUT/'research/latest'/study/name)
    for name in ['summary.json','prediction_seal.json']:
        copy(DEFAULT/name,OUT/'research/latest/blind_icing_20261025_v2'/name)
    copy(PRIVATE/'official_updates_20261025_v9/summary.json',OUT/'provenance/official_20261025_2258.json')
    copy(PRIVATE/'residual_sources_20261025_v1/xgboost_3.0.1_LICENSE.txt',OUT/'licenses/research_xgboost_3.0.1_LICENSE.txt')
    brief=PRIVATE/'submission_review_v6_20261025';review=read(brief/'visual_review.json');assert review['status']=='passed' and review['pdf_sha256']==sha(brief/'review_brief.pdf')
    copy(brief/'review_brief.pdf',OUT/'reports/review_brief_v6.pdf');copy(brief/'receipt.json',OUT/'validation/v6_brief_source.json');copy(brief/'visual_review.json',OUT/'validation/v6_brief_visual.json')
    copy(PRIVATE/'residual_tests_20261025_v1.log',OUT/'validation/v6_tests.log')
    (OUT/'README.md').write_text('''# 도로 결빙 위험 추정 · 비공개 제출 검토 v6

관측 없는 도로의 온도 추정, 결빙 탐지의 한계, 구간별 결과 탐색과 재현 절차를 담았습니다. **온도 v3·결빙 v2 모델과 기존 예측은 보존합니다.** v6는 최신 연구·2쪽 핵심 요약·무결성 및 실행 검사 도구를 추가한 검토 묶음입니다.

## 5분 검토 순서

1. [2쪽 검토 요약](reports/review_brief_v6.pdf): 현재 성과·실패·자료 한계·실행 경로.
2. [현재 상태](docs/STATUS.md)와 [최신 연구](docs/research/RESIDUAL_AND_INFORMATION_20261025.md): 기존 기온 기준선을 안정적으로 넘지 못한 실험과 동일 입력의 정보 제한.
3. [구간 탐색 화면](demo/review/index.html)·[CSV 규약](docs/delivery/CSV_CONTRACT.md): 1,266개 구간의 결과·입력 가용 범위. 사고 확률·공식 위험등급은 아닙니다.
4. 아래 검사 명령과 [보존한 실행 안내](README_v4.md): 예측·노트북 실행.
5. [공식 규정·제출 일정](docs/competition/OFFICIAL_UPDATE_20261025.md): 결과물 날짜·경로는 별도 공지 예정. 이 묶음은 접수 완료본이 아닙니다.

## 실행과 검사

Python 3.11 환경에서 포함 의존성을 설치한 뒤 이 폴더를 작업 위치로 사용합니다. 설치에는 패키지 접근이 필요하고, 설치 이후 예측은 포함 자료를 사용합니다. 출력 파일은 새 경로를 사용하세요.

```powershell
python -m pip install -r requirements-notebook.txt
python scripts/review_submission_bundle.py
python scripts/review_submission_bundle.py --smoke --output local_review/smoke.json
```

첫 검사는 manifest에 선언된 모든 파일의 크기·SHA-256·경로·예상 밖 파일을 대조합니다. `--smoke`는 명령줄 예측 144행이 포함 기준 예측과 같은지 확인하고 노트북 5개 코드 셀도 실행합니다. 결과와 로그는 `local_review/`에 남으며 이 폴더는 원래 manifest의 대상이 아닙니다. 검증을 실패한 파일은 원본을 바꾸지 말고 로그와 함께 확인하세요.

## 성능을 읽는 범위

기존 개발 9곳·두 겨울에서 온도 MAE는 1.145698°C, 결빙 일별 지점 F1은 0.026554입니다. 같은 입력 가용 범위의 ASOS 기온 기준선 F1 0.036601에 못 미칩니다. 반복 개발 점수와 공식 점수·새 독립 평가를 구별합니다. 새 4지역 주 후보도 사건 손실과 자료 품질 조건에 실패해 미채택했습니다. 입력 부족 18행은 NA로 남습니다.

## 보존 자산과 최신 추가 자료

모델·입력·예측·CSV·8쪽 보고서·노트북·데모·실행 코드는 v5의 해시와 대조합니다. 2쪽 요약은 기존 보고서의 후속 검토 안내이며 과거 8쪽 보고서를 새로운 독립 성능 보고서로 바꾸지 않았습니다. `research/latest/`에는 최신 집계·선택·감사 기록을, `validation/v6_delivery.json`에는 실제 보존·실행 검사 결과를 넣었습니다.

최신 연구의 모든 원자료·미채택 모델은 원 비공개 작업 공간에 남아 있습니다. 이 묶음만으로 포함 모델의 추론·예제 노트북은 실행할 수 있으나 모든 연구 명령의 입력이 포함된 것은 아닙니다. `README_v5.md` 등 과거 안내와 이전 manifest는 출처 기록으로 보존합니다. [AI 활용 기록](AI_USAGE.md)은 AI의 실행·검산과 사용자·주최 측 승인을 구별합니다.

제공 자료의 승인받지 않은 제3자 열람·배포와 외부 공개를 금지합니다. GitHub에는 코드·설정·집계 문서만 반영하고 이 ZIP·원자료·모델·예측·인증정보는 올리지 않습니다.
''',encoding='utf8')
    core=core_check();manifest();print('PREPARED v6 core',len(core),flush=True)


def verify():
    destination=OUT/'validation/v6_delivery.json'
    if destination.exists():raise FileExistsError('Preserve verification')
    source_checks();sync_index();core=core_check();manifest()
    names=[p.relative_to(OUT).as_posix() for p in OUT.rglob('*.md') if '__pycache__' not in p.parts]
    errors=inspect_documents(OUT,names)
    if errors:raise ValueError('\n'.join(errors))
    env=os.environ.copy();env.update(OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2',TEMP=str(PRIVATE/'icing_test_tmp_20261025'),TMP=str(PRIVATE/'icing_test_tmp_20261025'))
    local=OUT/'local_review';local.mkdir(exist_ok=True);attempt=1
    while any(local.glob(f'v6_verification_{attempt:02d}*')):attempt+=1
    execution=local/f'v6_verification_{attempt:02d}.json'
    run=subprocess.run([sys.executable,'-X','utf8','scripts/review_submission_bundle.py','--smoke','--output',str(execution.relative_to(OUT))],cwd=OUT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
    execution.with_suffix('.driver.log').write_bytes(run.stdout);print(run.stdout.decode('utf8',errors='replace')[-1400:],flush=True)
    assert run.returncode==0,'Bundle execution check failed'
    result=read(execution);assert result['prediction_rows_identical']==144
    for check in result['checks']:
        log=OUT/'validation'/('v6_'+check['name']+'.log');copy(OUT/check['log'],log);check['log']=log.relative_to(OUT).as_posix()
    if (local/'v6_attempt_notes.json').exists():copy(local/'v6_attempt_notes.json',OUT/'validation/v6_execution_environment.json')
    core_check();source_checks()
    write(destination,dict(status='v6_delivery_verified',at_utc=now(),source_zip_sha256=OLD_SHA,core_files_unchanged=len(core),core_files=core,
        markdown_documents=len(names),execution=result,source_summary_sha256={name:sha(PRIVATE/name/'summary.json') for name in STUDIES},
        production_model_changed=False,protected_outcomes_used=False,competition_submitted=False))
    manifest();verify_directory(OUT);print('VERIFIED v6',flush=True)


def package():
    source_checks();core_check();assert read(OUT/'validation/v6_delivery.json')['status']=='v6_delivery_verified'
    target=OUT.with_suffix('.zip')
    if target.exists():raise FileExistsError('Preserve existing ZIP')
    verify_directory(OUT);records=read(OUT/'manifest.json')['files']
    from src.kma_rwis_download import load_auth_key
    key=load_auth_key(ROOT/'secret.env').encode()
    for name in records:
        assert not name.endswith(('.env','.pem','.key')) and '/.git/' not in '/'+name
        if (OUT/name).suffix in {'.py','.json','.md','.txt','.ipynb','.html','.js','.log'}:assert key not in (OUT/name).read_bytes(),name
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in sorted(records):z.write(OUT/name,name)
        z.write(OUT/'manifest.json','manifest.json')
    checked=verify_archive(target);receipt=dict(status='v6_archive_verified',at_utc=now(),archive=target.name,bytes=target.stat().st_size,sha256=sha(target),files=len(checked['files']),manifest_sha256=sha(OUT/'manifest.json'),model_version='v3',icing_version='v2',competition_submitted=False)
    write(target.with_suffix('.receipt.json'),receipt);print(receipt,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['prepare','verify','package'],required=True);globals()[parser.parse_args().stage]()
