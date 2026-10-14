"""14일 공식현황·입력공백 감사를 기존 검증후보에 덧붙이고 모델 불변·실행을 확인."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import zipfile
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write,preservation
from src.data_source import sha256_file as sha

PRIVATE=ROOT/'outputs/private';OUT=PRIVATE/'current_candidate_review_quality_20261014_v1'
ARCHIVE=PRIVATE/'submission_candidate_20261014_v1.zip';UNPACK=PRIVATE/'submission_candidate_unpack_20261014_v1'


def main():
    if OUT.exists() or ARCHIVE.exists() or UNPACK.exists():raise FileExistsError('Preserve current review delivery')
    OUT.mkdir();freeze=preservation();prior=read(PRIVATE/'submission_candidate_quality_20261013_v2/completion_receipt.json')
    old=PRIVATE/'submission_candidate_20261013_v2.zip';assert sha(old)==prior['archive_sha256']
    official=PRIVATE/'official_updates_20261014_v1';req=read(official/'requirements_receipt.json');review=read(official/'summary.json');changes=read(official/'change_interpretation.json')
    assert req['config_sha256']==sha(ROOT/'config/official_requirements_20261014.json')
    assert changes['current_problem_question_count']==6 and changes['current_general_question_count']==17
    assert changes['problem_questions_all_completed'] and changes['general_2026_questions_all_completed']
    assert changes['faq_images']['current']==changes['faq_images']['previous']
    current_tabs=read(official/'problem_tabs.bin');old_tabs=read(PRIVATE/'official_updates_20261013_v2/problem_tabs.bin')
    assert len(current_tabs['overviewList'])==len(old_tabs['overviewList'])
    assert all(a['title']==b['title'] and a['content']==b['content'] for a,b in zip(current_tabs['overviewList'],old_tabs['overviewList']))
    for receipt in read(official/'fetch_receipts.json'):assert sha(official/receipt['file'])==receipt['sha256']
    coverage=PRIVATE/'candidate_coverage_review_20261014_v1';coverage_summary=read(coverage/'summary.json')
    for rel,digest in coverage_summary['input_signatures'].items():assert sha(ROOT/rel)==digest
    assert coverage_summary['missing_prediction_rows']==21 and coverage_summary['labelled_ice_on_missing_inputs']==0 and not coverage_summary['protected_ground_truth_read']
    env=os.environ.copy();env.update({'GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'safe.directory','GIT_CONFIG_VALUE_0':str(ROOT),'LOKY_MAX_CPU_COUNT':'2'})
    checks=[]
    for name,cmd in [('repository',[sys.executable,'-X','utf8','scripts/check_repository.py','--include-untracked']),
        ('markdown',[sys.executable,'-X','utf8','scripts/check_markdown.py','--include-untracked','--render-dir',str(OUT/'rendered')])]:
        r=subprocess.run(cmd,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
        (OUT/(name+'.log')).write_bytes(r.stdout);assert r.returncode==0,r.stdout.decode('utf-8',errors='replace')[-1000:]
        checks.append(dict(name=name,returncode=r.returncode,log_sha256=sha(OUT/(name+'.log'))));print(name,r.stdout.decode('utf-8',errors='replace').strip(),flush=True)
    replacements={}
    for directory in ['src','scripts','config','tests','notebooks','docs','.github']:
        for p in (ROOT/directory).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':replacements[p.relative_to(ROOT).as_posix()]=p.read_bytes()
    replacements['AI_USAGE.md']=(ROOT/'AI_USAGE.md').read_bytes()
    replacements['requirements-delivery.txt']=(ROOT/'requirements-delivery.txt').read_bytes()
    supplemental=dict(checked_date_kst='2026-10-14',problem_questions=6,general_2026_questions=17,all_answered=True,
        latest_notice_post_date='2026-10-12',faq_body_changed=True,handwriting_font_signature_rejected=True,
        multiple_project_applications_allowed=True,multiple_awards_allowed=False,result_deadline_date=None,official_csv_schema_confirmed=False,
        application_bytes_unchanged=True,application_or_registration_modified=False,account_approval_verified=False,
        protected_outcomes_read=False,full_data_zip_redownloaded=False,source_config_sha256=req['config_sha256'])
    replacements['reports/current_competition_review_20261014.json']=(json.dumps(supplemental,ensure_ascii=False,indent=2)+'\n').encode()
    replacements['reports/prediction_coverage_20261014.json']=(coverage/'summary.json').read_bytes()
    replacements['reports/development_prediction_coverage_20261014.csv']=(coverage/'development_station_coverage.csv').read_bytes()
    replacements['reports/protected_prediction_missing_slots_20261014.csv']=(coverage/'protected_prediction_missing_slots.csv').read_bytes()
    with zipfile.ZipFile(old) as z:
        manifest=json.loads(z.read('candidate_manifest.json'));old_files=manifest['files'].copy()
        root_readme=z.read('README.md').decode('utf-8')
    root_readme='''# 10월14일 제출 후보 검토

이 압축본은 기존 대표 모델·데이터·예측을 유지하고 최신 공식현황과 입력공백 감사를 추가한 비공개 후보입니다. `docs/COMPETITION_STATUS_20261014.md`에서 새Q&A653·FAQ서명/중복신청 조건, 결과물 일정·규격 미정, 가용성 감사를 먼저 확인합니다. 최종 모델 승격·독립 성능 통과·공식 제출 상태는 아닙니다.

허용개발의입력부족21행에는실제Ice가없지만 보호18공백의 실제정답은 확인하지않았습니다. 이 공백을0으로채우거나 기존 평가분모를유리하게바꾸지 않습니다. 최신설정은 `config/official_requirements_20261014.json`, 감사요약은 `reports/prediction_coverage_20261014.json`입니다. 기존 공식/평가 설정은 당시 기록으로 보존합니다.

## 대표 모델과 실행

'''+root_readme
    replacements['README.md']=root_readme.encode('utf-8')
    for rel,data in replacements.items():manifest['files'][rel]=dict(sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
    manifest.update(created_at_utc=datetime.now(timezone.utc).isoformat(),delivery_version='20261014_v1',previous_delivery_sha256=prior['archive_sha256'],
        official_review_date_kst='2026-10-14',model_and_prediction_values_changed=False,source_data_and_model_history_preserved=True,
        total_bytes=sum(v['bytes'] for v in manifest['files'].values()))
    with zipfile.ZipFile(old) as source,zipfile.ZipFile(ARCHIVE,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as target:
        for rel in manifest['files']:
            target.writestr(rel,replacements[rel] if rel in replacements else source.read(rel))
        target.writestr('candidate_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    UNPACK.mkdir()
    with zipfile.ZipFile(ARCHIVE) as z:
        assert z.testzip() is None
        for info in z.infolist():
            path=(UNPACK/info.filename).resolve();assert path.is_relative_to(UNPACK.resolve()) and not path.exists()
            path.parent.mkdir(parents=True,exist_ok=True)
            with z.open(info) as source,path.open('xb') as target:
                for block in iter(lambda:source.read(1024*1024),b''):target.write(block)
    for rel,entry in manifest['files'].items():assert sha(UNPACK/rel)==entry['sha256'],rel
    immutable=[n for n in old_files if n.startswith(('model/','data/prediction_groups/','data/weather_groups/')) or n=='data/protected_predictions_10min.csv.gz']
    assert all(manifest['files'][n]==old_files[n] for n in immutable)
    r=subprocess.run([sys.executable,'-X','utf8','code/predict.py','--input','data/weather_example.csv','--output','validation/current_review_example.csv'],cwd=UNPACK,
        env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
    (OUT/'isolated_inference.log').write_bytes(r.stdout);assert r.returncode==0
    pd.testing.assert_frame_equal(pd.read_csv(UNPACK/'validation/current_review_example.csv'),pd.read_csv(UNPACK/'data/example_predictions.csv'),check_exact=False,atol=1e-10,rtol=0)
    assert preservation()==freeze
    write(OUT/'completion_receipt.json',dict(status='current_competition_review_and_candidate_delivery_complete',completed_at_utc=datetime.now(timezone.utc).isoformat(),checks=checks,
        unchanged_core_unit_tests_previously_passed=252,official_raw_responses_verified=len(read(official/'fetch_receipts.json')),
        problem_questions=6,general_questions=17,latest_config_sha256=req['config_sha256'],coverage_summary_sha256=sha(coverage/'summary.json'),
        archive_sha256=sha(ARCHIVE),archive_bytes=ARCHIVE.stat().st_size,package_files=len(manifest['files'])+1,
        package_uncompressed_bytes=manifest['total_bytes'],all_package_file_hashes_verified=len(manifest['files']),immutable_model_weather_prediction_files_verified=len(immutable),
        isolated_example_rows_verified=144,new_model_fits=0,assessment_outcomes_used=False,model_promoted=False,competition_submitted=False,external_publication=False,
        official_csv_schema_confirmed=False,official_risk_grade_validated=False,old_frozen_files=freeze[0],reserved_frozen_files=freeze[1]))
    print(json.dumps(read(OUT/'completion_receipt.json'),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
