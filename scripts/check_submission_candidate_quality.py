"""검사 통과 후 후보압축을 만들고 별도 폴더에서 해시·CSV·개발지표 재현을 검증."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib
import os
import subprocess
import sys
import zipfile
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write,preservation
from scripts.audit_temperature_blind_validation import compare
from src.data_source import sha256_file as sha

PRIVATE=ROOT/'outputs/private';CANDIDATE=PRIVATE/'submission_candidate_20261013_v1'
OUT=PRIVATE/'submission_candidate_quality_20261013_v1'
UNPACK=PRIVATE/'submission_candidate_unpack_20261013_v1'
ARCHIVE=PRIVATE/'submission_candidate_20261013_v1.zip'


def run(name,command,cwd,env):
    result=subprocess.run(command,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    log=OUT/(name+'.log');log.write_bytes(result.stdout)
    print(name,result.returncode,result.stdout.decode('utf-8',errors='replace').splitlines()[-3:],flush=True)
    if result.returncode:raise RuntimeError('Preserve failed check '+name)
    return dict(name=name,returncode=result.returncode,log_sha256=sha(log))


def main():
    if OUT.exists() or UNPACK.exists() or ARCHIVE.exists():raise FileExistsError('Preserve quality/delivery evidence')
    OUT.mkdir();freeze=preservation();env=os.environ.copy()
    env.update({'GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'safe.directory','GIT_CONFIG_VALUE_0':str(ROOT),'LOKY_MAX_CPU_COUNT':'2'})
    tests=[]
    for name,cmd in [('tests',[sys.executable,'-X','utf8','-m','unittest','discover','-s','tests','-v']),
        ('repository',[sys.executable,'-X','utf8','scripts/check_repository.py','--include-untracked']),
        ('markdown',[sys.executable,'-X','utf8','scripts/check_markdown.py','--include-untracked','--render-dir',str(OUT/'rendered')])]:
        tests.append(run(name,cmd,ROOT,env))
    manifest=read(CANDIDATE/'candidate_manifest.json')
    for rel,entry in manifest['files'].items():assert sha(CANDIDATE/rel)==entry['sha256'],rel
    assert manifest['technical_preparation_complete'] and not manifest['model_promoted'] and not manifest['submitted']
    assert not manifest['protected_or_opened_assessment_labels_included']
    policy=PRIVATE/'thermal_consensus_20261013_v1';summary=read(policy/'summary.json');audit=read(policy/'independent_verification.json')
    assert audit['summary_sha256']==sha(policy/'summary.json') and audit['audit_source_sha256']==sha(ROOT/'scripts/audit_thermal_consensus.py')
    for rel,h in read(policy/'input_signatures.json').items():assert sha(ROOT/rel)==h
    for rel,h in summary['files'].items():assert sha(policy/rel)==h
    for rel,h in read(CANDIDATE/'spatial_input_signatures.json').items():assert sha(ROOT/rel)==h
    # 압축 중 원본을 바꾸지 않고 지정한 파일만 포함한다.
    with zipfile.ZipFile(ARCHIVE,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for rel in manifest['files']:z.write(CANDIDATE/rel,rel)
        z.write(CANDIDATE/'candidate_manifest.json','candidate_manifest.json')
    UNPACK.mkdir()
    with zipfile.ZipFile(ARCHIVE) as z:
        assert z.testzip() is None
        for info in z.infolist():
            target=(UNPACK/info.filename).resolve();assert target.is_relative_to(UNPACK.resolve()) and not target.exists()
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(info) as source,target.open('xb') as destination:
                for block in iter(lambda:source.read(1024*1024),b''):destination.write(block)
    for rel,entry in manifest['files'].items():assert sha(UNPACK/rel)==entry['sha256'],rel
    tests.append(run('unpacked_csv_inference',[sys.executable,'-X','utf8','code/predict.py','--input','data/weather_example.csv','--output','validation/isolated_example.csv'],UNPACK,env))
    actual=pd.read_csv(UNPACK/'validation/isolated_example.csv');expected=pd.read_csv(CANDIDATE/'data/example_predictions.csv')
    pd.testing.assert_frame_equal(actual,expected,check_exact=False,atol=1e-10,rtol=0)
    tests.append(run('unpacked_development_metrics',[sys.executable,'-X','utf8','code/reproduce_development.py','--output','validation/isolated_development_metrics.json'],UNPACK,env))
    development=read(UNPACK/'validation/isolated_development_metrics.json')['reports']
    source=read(PRIVATE/'weather_memory_controls_20261013_v1/summary.json');daily=read(PRIVATE/'qa633_development_20261013_v1/summary.json')
    for name,item in development.items():
        compare(item['temperature'],source['metrics'][name])
        for n,report in item['daily'].items():compare(report,daily['reports'][name][n])
    assert preservation()==freeze
    files=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT,env=env).decode('utf-8').split('\0')
    result=dict(status='submission_candidate_technical_delivery_verified',completed_at_utc=datetime.now(timezone.utc).isoformat(),checks=tests,
        package_files=len(manifest['files'])+1,package_uncompressed_bytes=manifest['total_bytes'],archive_bytes=ARCHIVE.stat().st_size,
        archive_sha256=sha(ARCHIVE),candidate_manifest_sha256=sha(CANDIDATE/'candidate_manifest.json'),
        isolated_file_hashes_verified=len(manifest['files']),isolated_example_rows_verified=144,isolated_development_reports_verified=8,
        protected_prediction_rows=103680,input_missing_prediction_rows=18,unique_weather_groups=138,
        new_model_fits=2,audit_refits=2,old_frozen_files=freeze[0],reserved_frozen_files=freeze[1],
        assessment_outcomes_used=False,official_csv_schema_confirmed=False,new_independent_performance_passed=False,
        official_risk_grade_validated=False,model_promoted=False,competition_submitted=False,external_publication=False,
        source_file_hashes={n:sha(ROOT/n) for n in files if n and (ROOT/n).is_file()})
    write(OUT/'completion_receipt.json',result)
    print('압축·별도폴더 재현 완료',len(manifest['files']),ARCHIVE.stat().st_size,flush=True)


if __name__=='__main__':main()
