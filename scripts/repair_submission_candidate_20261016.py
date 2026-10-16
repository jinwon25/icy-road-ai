"""검증한 기존 ZIP에서 후보를 복원하고 검토 정정·기준선·보고서를 새 묶음에 반영한다."""
from datetime import datetime,timezone
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write,preservation
from src.data_source import sha256_file as sha
from src.submission_archive import restore_archive,verify_archive
from src.submission_metadata import temperature_evidence

PRIVATE=ROOT/'outputs/private'; BASE_ZIP=PRIVATE/'submission_candidate_20261014_v3.zip'
OUT=PRIVATE/'submission_candidate_20261016_v1'
BENCH=PRIVATE/'baseline_benchmark_20261016_v1'
REPORT=PRIVATE/'review_report_20261016_v1'
DIRS={'src','scripts','config','tests','notebooks','docs','.github'}


def current_sources(out):
    names=subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),'ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode('utf-8').split('\0')
    for name in filter(None,names):
        if Path(name).parts[0] in DIRS or name in ['AI_USAGE.md','requirements-dev.txt','requirements-delivery.txt']:
            target=out/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)


def command(out, name, args):
    result=subprocess.run([sys.executable,'-X','utf8',*args],cwd=out,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=300)
    log=out/'validation'/('review_20261016_'+name+'.log');log.write_bytes(result.stdout)
    if result.returncode:raise RuntimeError(name+': '+result.stdout.decode('utf-8',errors='replace')[-1800:])
    return dict(name=name,exit_code=result.returncode,log_sha256=sha(log))


def prepare(out):
    if out.exists():raise FileExistsError('Existing candidate is preserved')
    receipt=read(PRIVATE/'model_report_quality_20261014_v1/final_delivery_receipt.json')
    assert sha(BASE_ZIP)==receipt['archive_sha256']
    base=out.parent/(out.name+'_restored_base')
    manifest=restore_archive(BASE_ZIP,base,receipt['archive_sha256']);out.mkdir()
    for rel in manifest['files']:
        p=Path(rel)
        if p.parts[0] in DIRS:continue
        target=out/rel
        if p.parts[:2]==('reports','current'):
            target=out/'reports/archive/analysis_20261014'/Path(*p.parts[2:])
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(base/rel,target)
    current_sources(out)
    shutil.copy2(ROOT/'src/submission_runtime.py',out/'code/runtime.py')
    shutil.copy2(ROOT/'src/submission_io.py',out/'code/submission_io.py')
    shutil.copytree(BENCH,out/'research/baselines')
    shutil.copy2(ROOT/'scripts/reproduce_baseline_delivery.py',out/'code/reproduce_baselines.py')
    card=read(out/'model/model_card.json');old_card=dict(card)
    temp=pd.read_parquet(out/'data/development_temperature_oof.parquet')
    card['source_development'].update(temperature_evidence(temp))
    benchmark=read(BENCH/'summary.json')
    card['source_development']['constant_and_simple_baselines']={name:{
        'daily_f1':item['coverage']['144']['f1_available_station_mean'],
        'f1_days':item['coverage']['144']['f1_days'],
        'f1_stations':item['coverage']['144']['f1_stations'],
        'fp':item['counts']['fp'],'fn':item['counts']['fn']} for name,item in benchmark['reports'].items()}
    card.update(performance_qualified=False,independent_current_candidate_validation_passed=False,
        corrected_on='2026-10-16',positive_share_33408=benchmark['positive_share_33408'])
    card['limitations']+=[
        '현재 후보 일별 F1은 항상 결빙·단순 기온 기준선보다 낮음',
        'Ice 95.9%가 33408에 집중되어 지점별·지역별 진단 필요']
    (out/'validation/model_card_before_20261016.json').write_text(json.dumps(old_card,ensure_ascii=False,indent=2)+'\n','utf-8')
    (out/'model/model_card.json').write_text(json.dumps(card,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
    commands=[]
    for name,args in [
        ('code_csv',['code/predict.py','--input','data/weather_example.csv','--output','validation/review_20261016_code.csv']),
        ('repository_csv',['-m','src.submission_runtime','--input','data/weather_example.csv','--models','model','--output','validation/review_20261016_repository.csv']),
        ('baselines',['code/reproduce_baselines.py','--output','validation/review_20261016_baselines.json'])]:
        commands.append(command(out,name,args))
    # 같은 CSV·Parquet 입력과 기존 기대값을 저장 모델만으로 비교한다.
    from src.submission_io import read_weather
    data=read_weather(out/'data/weather_example.csv');data.to_parquet(out/'validation/review_20261016_weather.parquet',index=False)
    commands.append(command(out,'repository_parquet',['-m','src.submission_runtime','--input','validation/review_20261016_weather.parquet','--models','model','--output','validation/review_20261016_parquet.parquet']))
    expected=read_weather(out/'data/example_predictions.csv')
    expected.time=pd.to_datetime(expected.time)
    for name in ['code.csv','repository.csv','parquet.parquet']:
        actual=read_weather(out/('validation/review_20261016_'+name))
        actual.time=pd.to_datetime(actual.time)
        pd.testing.assert_frame_equal(actual,expected,check_dtype=False,check_exact=True)
    immutable={}
    for rel,record in manifest['files'].items():
        if rel.startswith(('data/','research/freezing_weight/')) or (rel.startswith('model/') and rel.endswith('.joblib')):
            assert sha(out/rel)==record['sha256'],rel;immutable[rel]=record['sha256']
    write(out/'validation/review_20261016_prepare.json',dict(status='review_repairs_and_replays_passed',
        created_at_utc=datetime.now(timezone.utc).isoformat(),base_archive=str(BASE_ZIP.relative_to(ROOT)),base_archive_sha256=sha(BASE_ZIP),
        verified_base_files=len(manifest['files']),immutable_candidate_files=len(immutable),immutable_files=immutable,
        csv_parquet_temperature_different_rows=0,csv_parquet_binary_different_rows=0,example_rows=len(expected),
        original_expected_predictions_exact=True,baseline_reports_replayed=24,commands=commands,
        old_temperature_mae_station_mean=old_card['source_development']['temperature_mae_station_mean'],
        corrected_temperature=temperature_evidence(temp),model_fits=0,protected_or_opened_outcomes_read=False))
    print('Prepared repaired candidate; CSV/Parquet and original expected predictions agree exactly.',flush=True)


def finalize(out):
    prepared=read(out/'validation/review_20261016_prepare.json')
    assert prepared['status']=='review_repairs_and_replays_passed'
    assert read(REPORT/'visual_review.json')['status']=='all_pages_visually_reviewed'
    assert sha(REPORT/'current_report.pdf')==read(REPORT/'visual_review.json')['pdf_sha256']
    current_sources(out)
    card=read(out/'model/model_card.json')
    current=read(BENCH/'summary.json')['reports']['current']['coverage']['144']
    for metric in ['precision','recall','f1']:
        card['source_development']['daily_'+metric+'_defined_station_mean']=current[metric+'_available_station_mean']
    (out/'model/model_card.json').write_text(json.dumps(card,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
    destination=out/'reports/current';destination.mkdir()
    for name in ['current_report.pdf','supplement.md','report_receipt.json','visual_review.json']:
        shutil.copy2(REPORT/name,destination/name)
    shutil.copy2(PRIVATE/'official_updates_20261016_v1/completion_receipt.json',out/'reports/official_review_20261016.json')
    (out/'README.md').write_text('''# 전북 고속도로 결빙 분석 제출 후보

2026년 10월 16일 검토를 반영한 비공개 후보입니다. 실행 모델·보호 예측을 유지하고 CSV 추론·모델 카드·기준선 비교·복원 경로를 정정했습니다.

## 먼저 읽기

- [최신 보고서](reports/current/current_report.pdf): 앞 4쪽의 기준선·지점 편중·재현성 정정을 먼저 읽습니다. 뒤 12쪽은 10월 14일 분석 원문이며 당시 쪽번호를 유지합니다.
- [기준선·재현성 후속 검토](docs/delivery/REVIEW_RESPONSE_20261016.md)
- [오늘 공식 사이트 확인](docs/competition/OFFICIAL_UPDATE_20261016.md)
- [모델 카드](model/model_card.json) · [AI 활용 기록](AI_USAGE.md)

## 성능 판단

현재 후보의 개발 일별 F1은 0.030633, 항상 결빙은 0.055216, 단순 ASOS 기온 기준은 0.071122입니다. FP는 각각 20,255·148,507·57,912건입니다. 평균에 포함되는 날짜·지점 분모와 FP/FN을 함께 비교해야 합니다. 성능 적합 판정과 새 지점 독립 검증은 완료하지 않았습니다.

전체 행 MAE는 1.200531°C, 지점 균등 MAE는 1.200440°C입니다. 원 모델·학습·예측 파일을 보존했고 새 학습이나 임계값 최적화를 수행하지 않았습니다. 포함 자료는 허용된 첫 겨울 개발 정답과 두 겨울 기상·보호 예측이며 보호·개봉 평가 정답은 없습니다.

## 실행

Python 3.11과 requirements.txt의 고정 환경을 사용합니다. 결과 경로가 존재하면 중단합니다.

```powershell
python -X utf8 code/predict.py --input data/weather_example.csv --output validation/new_code.csv
python -X utf8 -m src.submission_runtime --input data/weather_example.csv --models model --output validation/new_repository.csv
python -X utf8 code/reproduce_baselines.py --output validation/new_baselines.json
python -X utf8 code/reproduce_development.py --output validation/new_development.json
```

CSV는 무손실 부동소수점 파서로 읽으며 두 추론 경로와 Parquet 결과를 같은 예제 144행에서 정확히 대조했습니다. 추론·기준선 검산은 저장 모델·포함 자료만 사용합니다. 기존 학습 코드는 필요 시 재현을 위한 자료이며 이번 정정에서는 실행하지 않았습니다.

## 재생성과 무결성

원본 작업 공간의 scripts/repair_submission_candidate_20261016.py는 보존된 10월 14일 ZIP을 검증·복원해 새 폴더를 만듭니다. 삭제된 임시 해제 폴더는 필요하지 않습니다. 이 ZIP 자체는 src.submission_archive 모듈로 검증·복원할 수 있습니다. manifest.json이 모든 포함 파일의 크기와 SHA-256을 기록합니다.

최종 CSV 규격·제출 일정은 운영진 안내에 맞춰야 합니다. 11월 6일은 참가신청 종료일입니다. 현재 묶음 생성은 공식 제출이나 모델 최종 승격이 아닙니다. 지도는 저온·수분 조건 노출이며 검증된 결빙 확률·사고확률·위험등급이 아닙니다.
''','utf-8')
    records=[]
    # 문서 검사에는 Git 인덱스가 있는 원본 작업 공간을 사용한다.
    for name,args in [('unit_tests',['-m','unittest','discover','-s','tests','-v']),
                      ('repository',['scripts/check_repository.py','--include-untracked']),
                      ('markdown',['scripts/check_markdown.py','--include-untracked'])]:
        result=subprocess.run([sys.executable,'-X','utf8',*args],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=300)
        log=out/'validation'/('review_20261016_'+name+'.log');log.write_bytes(result.stdout)
        print(name,result.returncode,result.stdout.decode('utf-8',errors='replace')[-180:],flush=True)
        if result.returncode:raise RuntimeError('Final check failed: '+name)
        records.append(dict(name=name,exit_code=result.returncode,sha256=sha(log)))
    for rel,digest in prepared['immutable_files'].items():assert sha(out/rel)==digest,rel
    write(out/'validation/review_20261016_final.json',dict(status='review_repairs_verified',checks=records,
        created_at_utc=datetime.now(timezone.utc).isoformat(),model_promoted=False,performance_qualified=False,
        official_submission=False,base_archive_sha256=prepared['base_archive_sha256']))
    files={p.relative_to(out).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(out.rglob('*'))
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    write(out/'manifest.json',dict(version=3,status='private_submission_candidate_performance_not_qualified',
        created_at_utc=datetime.now(timezone.utc).isoformat(),files=files))
    archive=out.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for rel in [*files,'manifest.json']:z.write(out/rel,rel)
    verify_archive(archive)
    receipt=dict(status='review_repair_candidate_packaged',archive=str(archive.relative_to(ROOT)),archive_sha256=sha(archive),
        archive_bytes=archive.stat().st_size,verified_hashes=len(files),entries=len(files)+1,
        old_archive_sha256=prepared['base_archive_sha256'],immutable_candidate_files=prepared['immutable_candidate_files'],
        model_fits=0,model_promoted=False,performance_qualified=False,official_submission=False)
    write(PRIVATE/'review_repair_delivery_20261016.json',receipt);print(json.dumps(receipt,indent=2),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['prepare','finalize'],required=True)
    parser.add_argument('--output',type=Path,default=OUT);args=parser.parse_args()
    assert args.output.resolve().is_relative_to(PRIVATE.resolve())
    frozen=preservation()
    (prepare if args.stage=='prepare' else finalize)(args.output)
    assert preservation()==frozen


if __name__=='__main__':main()
