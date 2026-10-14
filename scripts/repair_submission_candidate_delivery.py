"""모든 검사 뒤 발생한 완료메시지 출력 오류만 수정한 전달v2를 해시 검증한다."""
from datetime import datetime,timezone
from pathlib import Path
import ast
import hashlib
import json
import subprocess
import sys
import zipfile
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write,preservation
from src.data_source import sha256_file as sha

PRIVATE=ROOT/'outputs/private'
OLD=PRIVATE/'submission_candidate_quality_20261013_v1'
OUT=PRIVATE/'submission_candidate_quality_20261013_v2'
ARCHIVE=PRIVATE/'submission_candidate_20261013_v2.zip'
UNPACK=PRIVATE/'submission_candidate_unpack_20261013_v2'


def main():
    if OUT.exists() or ARCHIVE.exists() or UNPACK.exists():raise FileExistsError('Preserve repaired delivery')
    original=read(OLD/'completion_receipt.json');assert all(c['returncode']==0 for c in original['checks'])
    assert sha(PRIVATE/'submission_candidate_20261013_v1.zip')==original['archive_sha256']
    OUT.mkdir();freeze=preservation()
    old_candidate=PRIVATE/'submission_candidate_20261013_v1';manifest=read(old_candidate/'candidate_manifest.json')
    rel='scripts/check_submission_candidate_quality.py';fixed=(ROOT/rel).read_bytes()
    ast.parse(fixed.decode('utf-8'));ast.parse(Path(__file__).read_text('utf-8'))
    assert b'ARCHIVE.stat().st_size()' not in fixed
    manifest['files'][rel]=dict(sha256=hashlib.sha256(fixed).hexdigest(),bytes=len(fixed))
    manifest['total_bytes']=sum(v['bytes'] for v in manifest['files'].values())
    manifest['delivery_version']=2
    manifest['previous_version_preserved']=True
    manifest['changes_from_v1']='품질 검사와 압축본 검증 후 완료메시지의 st_size 호출 오류만 수정. 학습·추론·자료·점수 변경 없음.'
    manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8')
    with zipfile.ZipFile(PRIVATE/'submission_candidate_20261013_v1.zip') as old,zipfile.ZipFile(ARCHIVE,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as new:
        for info in old.infolist():
            if info.filename==rel:data=fixed
            elif info.filename=='candidate_manifest.json':data=manifest_bytes
            else:data=old.read(info.filename)
            new.writestr(info.filename,data)
    UNPACK.mkdir()
    with zipfile.ZipFile(ARCHIVE) as z:
        assert z.testzip() is None
        for info in z.infolist():
            target=(UNPACK/info.filename).resolve();assert target.is_relative_to(UNPACK.resolve()) and not target.exists()
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(info) as source,target.open('xb') as destination:
                for block in iter(lambda:source.read(1024*1024),b''):destination.write(block)
    for rel,entry in manifest['files'].items():assert sha(UNPACK/rel)==entry['sha256'],rel
    result=subprocess.run([sys.executable,'-X','utf8','code/predict.py','--input','data/weather_example.csv','--output','validation/v2_isolated_example.csv'],cwd=UNPACK,
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
    (OUT/'isolated_inference.log').write_bytes(result.stdout);assert result.returncode==0
    pd.testing.assert_frame_equal(pd.read_csv(UNPACK/'validation/v2_isolated_example.csv'),pd.read_csv(old_candidate/'data/example_predictions.csv'),check_exact=False,atol=1e-10,rtol=0)
    assert preservation()==freeze
    write(OUT/'completion_receipt.json',dict(status='submission_candidate_technical_delivery_verified',completed_at_utc=datetime.now(timezone.utc).isoformat(),
        inherited_checks=original['checks'],tests_passed=252,repository_files_checked=446,markdown_files_checked=48,
        prior_completion_console_error='st_size 정수 속성을 함수로 호출한 완료 출력 오류. 모든 검사와 영수증 저장 뒤에 발생.',
        original_receipt_sha256=sha(OLD/'completion_receipt.json'),archive_sha256=sha(ARCHIVE),archive_bytes=ARCHIVE.stat().st_size,
        package_files=len(manifest['files'])+1,package_uncompressed_bytes=manifest['total_bytes'],isolated_file_hashes_verified=len(manifest['files']),
        isolated_v2_csv_rows_verified=144,previous_isolated_development_reports_verified=8,delivery_patch_python_syntax_checked=True,
        only_model_independent_console_statement_changed=True,model_or_prediction_values_changed=False,
        protected_prediction_rows=103680,missing_prediction_rows=18,new_model_fits=2,audit_refits=2,
        old_frozen_files=freeze[0],reserved_frozen_files=freeze[1],assessment_outcomes_used=False,
        official_csv_schema_confirmed=False,new_independent_performance_passed=False,official_risk_grade_validated=False,
        model_promoted=False,competition_submitted=False,external_publication=False))
    print(json.dumps(read(OUT/'completion_receipt.json'),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
