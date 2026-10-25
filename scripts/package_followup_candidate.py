"""후속 연구가 v3 유지로 결론난 경우 검증된 탐색 화면·근거를 새 v4에 묶는다."""
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
from scripts.evaluate_method_blending import preservation

PRIVATE=ROOT/'outputs/private'
OLD=PRIVATE/'submission_candidate_20261024_v3'
OUT=PRIVATE/'submission_candidate_20261024_v4'
OLD_SHA='e0c14018feb46642cdb9bf62aad8d8c605dd9726315e32019e96335f21a65de5'
STUDIES=['followup_temperature_20261024_v1','followup_algorithm_20261024_v1',
         'followup_capacity_20261024_v1','followup_offset_20261024_v1',
         'followup_comparison_20261024_v1','icing_state_memory_20261024_v1',
         'followup_failure_diagnostics_20261024_v1']
AUDITS=['followup_temperature_audit_20261024_v1','followup_algorithm_audit_20261024_v1',
        'followup_offset_audit_20261024_v1','followup_long_memory_audit_20261024_v1',
        'icing_state_memory_audit_20261024_v1','followup_review_dashboard_audit_20261024_v2']


def read(p):return json.loads(p.read_text('utf-8'))
def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')


def copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)


def manifest():
    files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)
           for p in OUT.rglob('*') if p.is_file() and p!=OUT/'manifest.json'
           and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    write(OUT/'manifest.json',dict(version=8,status='private_followup_candidate',
        development_scope='extended_two_winter',created_at_utc=datetime.now(timezone.utc).isoformat(),
        files=files,production_model_version='v3',production_model_changed=False,
        independent_performance_qualified=False,competition_submitted=False))


def check_decision():
    comparison=read(PRIVATE/'followup_comparison_20261024_v1/summary.json')
    assert comparison['status']=='followup_comparison_complete'
    assert comparison['decision']=='preserve_v3_temperature' and not comparison['temperature_eligible']
    assert comparison['icing_decision']=='preserve_v3_icing' and not comparison['icing_eligible']
    assert sha(OLD.with_suffix('.zip'))==OLD_SHA==read(OLD.with_suffix('.receipt.json'))['sha256']
    return comparison


def prepare():
    if OUT.exists():raise FileExistsError('Preserve existing submission candidate')
    decision=check_decision();frozen=preservation();original=read(OLD/'manifest.json')
    for name,record in original['files'].items():
        assert sha(OLD/name)==record['sha256'],name
        copy(OLD/name,OUT/name)
    copy(OLD/'manifest.json',OUT/'provenance/v3_manifest.json')
    copy(OLD.with_suffix('.receipt.json'),OUT/'provenance/v3_archive_receipt.json')
    copy(OLD/'README.md',OUT/'README_v3.md')
    # v3 실행 코드는 바꾸지 않으며 이후 추가된 연구 파일만 더한다.
    new_files=[]
    for directory,suffixes in [('src',{'.py','.html'}),('scripts',{'.py'}),('config',{'.json'}),('tests',{'.py'})]:
        for source in (ROOT/directory).rglob('*'):
            if not source.is_file() or source.suffix not in suffixes or '__pycache__' in source.parts:continue
            name=source.relative_to(ROOT).as_posix()
            if name in original['files']:
                assert sha(source)==original['files'][name]['sha256'],f'Existing code changed: {name}'
                continue
            copy(source,OUT/name);new_files.append(name)
    for source in (ROOT/'docs').rglob('*.md'):copy(source,OUT/source.relative_to(ROOT))
    for name in ['AI_USAGE.md','scripts/README.md','config/README.md']:copy(ROOT/name,OUT/name)
    for study in STUDIES:
        for source in (PRIVATE/study).rglob('*'):
            if source.is_file() and source.suffix in {'.json','.csv','.parquet','.png'}:
                copy(source,OUT/'research/followup'/study/source.relative_to(PRIVATE/study))
    for audit in AUDITS:
        for source in (PRIVATE/audit).rglob('*'):
            if source.is_file() and source.suffix in {'.json','.csv','.png'}:
                copy(source,OUT/'validation/followup'/audit/source.relative_to(PRIVATE/audit))
    for source in (PRIVATE/'followup_review_dashboard_20261024_v2').iterdir():
        if source.is_file():copy(source,OUT/'demo/review'/source.name)
    recording=PRIVATE/'followup_review_walkthrough_20261024_v1'
    video_receipt=read(recording/'receipt.json')
    assert not video_receipt['visual_review_pending'] and video_receipt['browser_playback_passed']
    copy(recording/'review_walkthrough.webm',OUT/'demo/review_walkthrough.webm')
    for name in ['receipt.json','start.png','middle.png','end.png','video_start.png','video_middle.png','video_end.png','video_daily.png','selected_daily.csv']:
        copy(recording/name,OUT/'validation/followup/review_walkthrough'/name)
    for source in (PRIVATE/'followup_browser_license_20261024_v1').iterdir():
        if source.is_file():copy(source,OUT/'licenses/browser_qa'/source.name)
    copy(PRIVATE/'followup_sources_20261024_v1/review.json',OUT/'research/followup/source_review.json')
    copy(PRIVATE/'followup_unit_tests_20261024.log',OUT/'validation/followup/unit_tests.log')
    copy(PRIVATE/'followup_repository_snapshot_20261024_v1.receipt.json',OUT/'validation/followup/source_only_snapshot.json')
    copy(PRIVATE/'followup_repository_snapshot_20261024_v1.manifest.json',OUT/'validation/followup/source_only_snapshot_manifest.json')
    for name in ['unit_tests','repository','markdown']:
        copy(PRIVATE/f'followup_snapshot_{name}_20261024.log',OUT/f'validation/followup/source_only_{name}.log')
    write(OUT/'provenance/followup_preparation.json',dict(status='v3_core_and_followup_assets_prepared',
        source_archive_sha256=OLD_SHA,source_manifest_sha256=sha(OLD/'manifest.json'),
        new_code_files=new_files,model_changed=False,protected_labels_read=False,
        omitted_research_fit_weights=True,omission_reason='미채택 연구 모델 가중치는 원 비공개 작업 공간에 보존. 영수증·예측·설정·소스 포함.',
        comparison_sha256=sha(PRIVATE/'followup_comparison_20261024_v1/summary.json'),frozen_counts=list(frozen)))
    assert preservation()==frozen
    manifest();print('v4 prepared, original files',len(original['files']),'new source files',len(new_files),flush=True)


def assets():
    result=check_decision()
    # 문서는 결과 확정 후 갱신하고 기존 계산 산출물은 그대로 둔다.
    for source in (ROOT/'docs').rglob('*.md'):copy(source,OUT/source.relative_to(ROOT))
    for name in ['AI_USAGE.md','scripts/README.md','config/README.md']:copy(ROOT/name,OUT/name)
    for name in read(OUT/'provenance/followup_preparation.json')['new_code_files']:copy(ROOT/name,OUT/name)
    body=f'''# 노면온도 추정 · 구간 탐색 제출 검토 후보

v4는 추가 온도 대조 {len(result['reports'])}개와 결빙 상태 정책 14개를 검토한 뒤, 검증된 v3 모델·예측을 유지하고 오프라인 구간 탐색 화면과 후속 검증 근거를 통합한 묶음입니다. 같은 공간 제외 개발 자료의 온도 MAE는 **1.145698°C**, 두 겨울 결빙 일별 지점 F1은 **0.026554**입니다. 반복 개발 결과이며 새 독립 평가나 공식 성적이 아닙니다.

## 먼저 확인할 결과

1. [오프라인 구간 탐색](demo/review/index.html) · [실제 브라우저 조작 영상](demo/review_walkthrough.webm): 500m·1km, 두 겨울, 세 노선, 1,266개 구간. 지도 선택·일별 추정 온도·조건 노출·입력 범위·CSV 다운로드.
2. [후속 비교와 채택 결론](docs/delivery/FOLLOWUP_UPGRADE_20261024.md): 추가 실험, 미채택 이유, 규정 확인 범위.
3. [8쪽 모델 보고서](reports/current/current_report.pdf) · [실행 노트북](notebooks/extended_submission_review.ipynb) · [기존 추론 화면](demo/index.html) · [실제 출력 영상](demo/extended_inference.mp4).
4. [문헌·오픈소스 검토](docs/research/OPEN_SOURCE_REVIEW_20261024.md) · [AI 활용 기록](AI_USAGE.md) · [CSV 규약](docs/delivery/CSV_CONTRACT.md).

보고서·노트북·기존 추론 화면의 v3 표시는 유지한 모델 버전입니다. v4는 포장·탐색·검증 버전이며 새 모델 성능 향상을 주장하지 않습니다. 탐색 화면은 통신 없이 실행됩니다. 표시하는 저온·수분 조건 노출은 관측 결빙률·사고확률·검증된 위험등급이 아닙니다.

새 WebM은 실제 Chromium 화면의 필터·날짜·다운로드 조작을 녹화했으며 모델을 새로 학습하거나 추론하는 영상은 아닙니다. Chromium에서 재생을 확인했습니다. 기존 MP4는 실제 추론 출력의 시각화입니다. 선택적인 화면 검사는 `licenses/browser_qa/requirements-browser-qa.txt`의 Playwright와 Chromium을 설치한 뒤 실행할 수 있습니다. 화면 탐색 자체에는 이 도구가 필요하지 않습니다.

## 실행

Python 3.11에서 새 폴더에 압축을 풀고 실행합니다. 기본 노트북은 재학습하지 않습니다.

```powershell
python -m pip install -r requirements-notebook.txt
python -X utf8 scripts/check_notebook.py notebooks/extended_submission_review.ipynb
python -X utf8 code/predict.py --input data/weather_example.csv --output validation/my_prediction.csv --output-start 2024-12-15 --output-end 2024-12-16
python -X utf8 code/train.py --output validation/my_refit
```

216행의 이력 포함 예제로 하루 144행을 출력합니다. 학습 범위 내 실행 예제이며 성능평가가 아닙니다. 추론·최종 재학습·노트북 검산은 포함 자료만으로 실행됩니다. 현재 온도 `estimated_road_temp_c`와 기존 결빙 판정에 사용하는 `icing_reference_temperature_c`를 구분합니다.

## 자료·검증 범위

허용 23곳·두 겨울 유효 온도 793,149쌍으로 학습한 63개 입력 HGB MAE 1,200회 모델을 유지합니다. 보호 3곳 정답은 없으며 보호 예측 103,680행 중 입력 부족 18행은 NA입니다. 138개 기상 그룹을 공유하는 구간을 독립 평가 표본으로 세지 않습니다. CSV 11종·지도·모델·예측의 v3 대비 파일 해시 일치는 `validation/followup_delivery.json`에 기록합니다.

`research/followup/`에는 고정 계획·예측·지표·적합 영수증을, `validation/followup/`에는 저장 모델 재실행·수치 재계산·브라우저 검사를 담았습니다. 미채택 연구 모델 가중치는 원 비공개 작업 공간에 보존합니다. 전체 탐색 재실행은 그 작업 공간의 입력 경로가 필요합니다. 이전 v3의 파일 목록은 `provenance/v3_manifest.json`, 실행 모델의 두 번 독립 재학습 해시 일치는 `validation/refit_comparison.json`입니다.

## 규정과 남은 확인

외부 사전학습 가중치·보호 노면 정답·새 외부 관측 자료를 추가하지 않았습니다. 최신 상세 규정·참가서약 완전 재확인일은 10월 16일이며, 10월 24일에는 공개 소개·공지·Q&A 목록을 재확인했습니다. 최신 상세 답변·실제 결과물 마감·접수 방식은 미확인입니다. **11월 6일은 참가신청 종료일**이며 결과물 마감으로 사용하지 않습니다. 대회 제출·외부 공개는 수행하지 않았습니다.
'''
    (OUT/'README.md').write_text(body,'utf-8');manifest()


def verify():
    destination=OUT/'validation/followup_delivery.json'
    if destination.exists():raise FileExistsError('Preserve completed verification')
    check_decision();frozen=preservation();original=read(OUT/'provenance/v3_manifest.json')['files']
    core=[name for name in original if name.startswith(('model/','data/','exports/','figures/','code/','src/','notebooks/','reports/','demo/'))
          or name in ['extended_training_plan.json','requirements.txt','requirements-notebook.txt']]
    for name in core:assert sha(OUT/name)==original[name]['sha256'],name
    snapshot=read(OUT/'demo/review/source_snapshot.json')
    browser=read(OUT/'validation/followup/followup_review_dashboard_audit_20261024_v2/receipt.json')
    assert snapshot['candidate_manifest_sha256']==sha(OUT/'provenance/v3_manifest.json')
    assert not snapshot['visual_review_pending'] and not browser['visual_review_pending']
    assert snapshot['html_sha256']==browser['html_sha256']==sha(OUT/'demo/review/index.html')
    assert snapshot['template_sha256']==sha(OUT/'src/review_dashboard_template.html')
    assert snapshot['generator_sha256']==sha(OUT/'scripts/build_review_dashboard.py')
    assert browser['segment_checks']==48 and browser['date_checks']==144 and not browser['errors'] and not browser['external_requests']
    for name,expected in snapshot['sources'].items():assert sha(OUT/name)==expected
    for name in ['segment_estimates.csv','prediction_group_daily.csv']:
        assert sha(OUT/'demo/review'/name)==sha(OUT/'exports'/name)
    for name,expected in browser['screenshot_sha256'].items():
        assert sha(OUT/'validation/followup/followup_review_dashboard_audit_20261024_v2'/name)==expected
    video=read(OUT/'validation/followup/review_walkthrough/receipt.json')
    assert not video['visual_review_pending'] and video['actual_browser_recording'] and video['browser_playback_passed']
    assert video['html_sha256']==sha(OUT/'demo/review/index.html')
    assert video['video_sha256']==sha(OUT/'demo/review_walkthrough.webm')
    assert video['code_sha256']==sha(OUT/'scripts/record_review_dashboard.py')
    for name,expected in video['screenshots'].items():assert sha(OUT/'validation/followup/review_walkthrough'/name)==expected
    for name,expected in video['decoded_frame_sha256'].items():assert sha(OUT/'validation/followup/review_walkthrough'/name)==expected
    checks=[];environment=os.environ.copy()
    environment.update(OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2',GIT_CONFIG_COUNT='1',
        GIT_CONFIG_KEY_0='safe.directory',GIT_CONFIG_VALUE_0=ROOT.as_posix())
    commands=[(ROOT,['scripts/check_repository.py','--include-untracked'],'repository'),
              (ROOT,['scripts/check_markdown.py','--include-untracked'],'markdown'),
              (OUT,['scripts/check_notebook.py','notebooks/extended_submission_review.ipynb'],'notebook'),
              (OUT,['code/predict.py','--input','data/weather_example.csv','--output','validation/followup_cli_prediction.csv',
                    '--output-start','2024-12-15','--output-end','2024-12-16'],'prediction_cli')]
    journal=OUT/'validation/followup/command_checks.json'
    completed=read(journal) if journal.exists() else {}
    for cwd,args,name in commands:
        if name in completed:
            previous=completed[name]
            assert previous['returncode']==0 and sha(OUT/previous['log_file'])==previous['log_sha256']
            checks.append(previous);print('Previously verified command preserved',name,flush=True);continue
        run=subprocess.run([sys.executable,'-X','utf8',*args],cwd=cwd,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600)
        text=run.stdout.decode('utf-8',errors='replace');log=OUT/f'validation/followup/{name}.log';attempt=1
        while log.exists():log=OUT/f'validation/followup/{name}_retry{attempt}.log';attempt+=1
        log.write_text(text,'utf-8')
        print(name,run.returncode,text[-800:],flush=True)
        assert run.returncode==0,name
        check=dict(name=name,returncode=0,log_file=log.relative_to(OUT).as_posix(),log_sha256=sha(log))
        completed[name]=check;write(journal,completed);checks.append(check)
    import pandas as pd
    args=dict(dtype={'station':str,'predicted_ice':'Int64'},parse_dates=['time'],float_precision='round_trip')
    pd.testing.assert_frame_equal(pd.read_csv(OUT/'validation/followup_cli_prediction.csv',**args),
                                 pd.read_csv(OUT/'data/example_predictions.csv',**args),check_exact=True)
    raw=(OUT/'validation/followup/unit_tests.log').read_bytes()
    unit=raw.decode('utf-16') if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else raw.decode('utf-8-sig')
    match=re.search(r'(\d+) passed',unit);assert match and int(match[1])>=334 and 'FAILED' not in unit
    isolated=read(OUT/'validation/followup/source_only_snapshot.json')
    assert isolated['status']=='source_only_repository_snapshot_verified' and not isolated['private_assets_copied']
    assert isolated['manifest_sha256']==sha(OUT/'validation/followup/source_only_snapshot_manifest.json')
    for name,expected in isolated['log_sha256'].items():
        assert sha(OUT/f'validation/followup/source_only_{name}.log')==expected
    for page in [OUT/'README.md',OUT/'demo/review/index.html']:
        pattern=r'\]\(([^)]+)\)' if page.suffix=='.md' else r'href="([^"]+)"'
        for link in re.findall(pattern,page.read_text('utf-8')):
            if re.match(r'^[a-z]+:',link) or link.startswith('#'):continue
            assert (page.parent/link.split('#',1)[0]).exists(),link
    assert read(OUT/'validation/refit_comparison.json')['all_models_byte_identical']
    assert preservation()==frozen
    write(destination,dict(status='followup_delivery_verified',checks=checks,unit_tests=int(match[1]),
        original_core_files_unchanged=len(core),core_files=core,source_zip_sha256=OLD_SHA,
        dashboard_segment_checks=48,dashboard_date_checks=144,browser_errors=0,external_requests=0,
        actual_browser_video_frames=video['frames'],actual_browser_video_seconds=video['seconds'],
        protected_labels_read=False,new_independent_assessment=False,production_model_changed=False,
        frozen_counts=list(frozen),competition_submitted=False,created_at_utc=datetime.now(timezone.utc).isoformat()))
    manifest()


def package():
    assert read(OUT/'validation/followup_delivery.json')['status']=='followup_delivery_verified'
    check_decision();target=OUT.with_suffix('.zip')
    if target.exists():raise FileExistsError('Preserve completed ZIP')
    manifest();m=read(OUT/'manifest.json')
    for name in m['files']:assert not name.endswith(('.key','.pem','.env')) and '/.git/' not in '/'+name
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name in sorted(m['files']):archive.write(OUT/name,name)
        archive.write(OUT/'manifest.json','manifest.json')
    verified=verify_archive(target)
    receipt=dict(status='followup_archive_verified',archive=target.name,bytes=target.stat().st_size,
        sha256=sha(target),files=len(verified['files']),manifest_sha256=sha(OUT/'manifest.json'),
        production_model_version='v3',production_model_changed=False,competition_submitted=False)
    write(target.with_suffix('.receipt.json'),receipt);print(json.dumps(receipt,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['prepare','assets','verify','package'],required=True)
    globals()[parser.parse_args().stage]()
