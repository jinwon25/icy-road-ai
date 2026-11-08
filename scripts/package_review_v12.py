"""v11 실행 자산을 보존하고 관측망 비교·입력 점검·24쪽 보고서를 두 채널로 묶는다."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,now,verify_preserved
from scripts.review_submission_bundle import verify_directory
from scripts.package_review_v8 import copy,archive
from scripts.check_markdown import inspect_documents
from src.data_source import sha256_file as sha


def compare_browser_content(original,relocated):
    from PIL import Image,ImageChops,ImageDraw
    for name in ['desktop.png','mobile.png']:
        a=Image.open(original/name).convert('RGB');b=Image.open(relocated/name).convert('RGB')
        assert a.size==b.size
        # OS의 native select 화살표/내재 폭은 실행마다 달라질 수 있다.
        # 선택 값·1840개 동작은 별도 DOM/수치 검사로 확인한다.
        rectangle=(0,130,a.width,228) if name=='desktop.png' else (0,205,a.width,500)
        ImageDraw.Draw(a).rectangle(rectangle,fill='white');ImageDraw.Draw(b).rectangle(rectangle,fill='white')
        assert ImageChops.difference(a,b).getbbox() is None,'Non-control content pixels changed: '+name
    return True

P=ROOT/'outputs/private';OLD=P/'submission_candidate_20261101_v11';OUT=P/'submission_candidate_20261101_v12'
CHANNELS=P/'submission_channels_20261101_v12';REPORT=P/'report_update_20261101_v12'
UPDATED={'README.md','README_repository.md','AI_USAGE.md','docs/STATUS.md','docs/README.md','docs/START_HERE.md',
    'docs/delivery/REVIEWER_GUIDE.md','scripts/README.md','config/README.md','.github/PUBLICATION.md'}
STUDIES=['weather_network_20261101_v1','weather_network_viewer_20261101_v2','weather_network_viewer_qa_20261101_v3',
    'network_followup_review_20261101_v1','network_references_20261101_v1']


def checks():
    frozen=verify_preserved();verify_directory(OLD)
    a=read(P/STUDIES[0]/'independent_verification.json');s=read(P/STUDIES[0]/'summary.json')
    assert a['status']=='passed' and a['summary_sha256']==sha(P/STUDIES[0]/'summary.json') and s['accepted_targets']==['wind_speed']
    wind=read(P/'wind_network_supplement_validation_20261101_v1/receipt.json')
    assert wind['status']=='wind_network_supplement_verified' and wind['refit_rows_exact']==432
    report=read(REPORT/'build_receipt.json');visual=read(REPORT/'visual_review.json')
    assert visual['status']=='passed' and visual['pdf_sha256']==report['pdf_sha256']==sha(REPORT/'analysis_report_v12.pdf')
    assert visual['pages']==24 and report['previous_pages_pixel_identical']==21
    for name,digest in report['sources'].items():assert sha(ROOT/name)==digest,name
    assert read(P/STUDIES[2]/'visual_review.json')['status']=='passed'
    return frozen


def preserved():
    records=read(OLD/'manifest.json')['files'];names=[n for n in records if n not in UPDATED]
    for name in names:assert sha(OUT/name)==records[name]['sha256'],name
    return names


def manifest(folder,channel):
    records={}
    for path in folder.rglob('*'):
        if not path.is_file():continue
        name=path.relative_to(folder).as_posix()
        if name=='manifest.json' or name.startswith('local_review/') or '__pycache__' in path.parts or path.suffix=='.pyc':continue
        records[name]=dict(bytes=path.stat().st_size,sha256=sha(path))
    path=folder/'manifest.json'
    if path.exists():path.unlink()
    value=dict(package_label='v12',channel=channel,status='private_review_candidate',at_utc=now(),files=records,
        current_report='reports/analysis_report_v12.pdf',competition_submitted=False)
    if channel=='model':value.update(current_notebook='notebooks/submission_review_v11.ipynb',
        latest_notebook='notebooks/weather_network_review_20261101.ipynb',production_model_version='v3',icing_version='v2',production_model_changed=False,wind_network_supplement_added=True)
    write(path,value)


def prepare():
    if OUT.exists():raise FileExistsError('Preserve previous bundle')
    frozen=checks()
    for name in read(OLD/'manifest.json')['files']:copy(OLD/name,OUT/name)
    copy(OLD/'manifest.json',OUT/'provenance/v11_manifest.json');copy(OLD/'README.md',OUT/'README_v11.md')
    git=['git','-c','safe.directory='+ROOT.as_posix(),'ls-files','--cached','--others','--exclude-standard','-z']
    sources={}
    for name in sorted(set(filter(None,subprocess.check_output(git,cwd=ROOT).decode('utf8').split('\0')))):
        if not name.startswith(('src/','scripts/','tests/','config/','docs/','notebooks/','.github/')):continue
        path=ROOT/name;dest=OUT/name
        if not path.is_file() or path.suffix not in ['.py','.md','.json','.ipynb','.png','.jpg','.html','.txt','.yml','.yaml']:continue
        if dest.exists() and name not in UPDATED:continue
        copy(path,dest);sources[name]=sha(path)
    copy(ROOT/'AI_USAGE.md',OUT/'AI_USAGE.md');copy(ROOT/'README.md',OUT/'README_repository.md')
    for name in STUDIES:
        for path in (P/name).iterdir():
            if path.is_file() and path.suffix in ['.json','.csv','.png','.html','.txt','.xml','.log']:
                copy(path,OUT/'research/latest'/name/path.name)
    wind=P/'wind_network_supplement_20261101_v2';wind_receipt=read(wind/'receipt.json')
    for name in [*wind_receipt['files'],'receipt.json']:copy(wind/name,OUT/'research/wind_network_supplement'/name)
    copy(P/'wind_network_supplement_validation_20261101_v1/receipt.json',OUT/'validation/wind_network_full_refit.json')
    copy(REPORT/'analysis_report_v12.pdf',OUT/'reports/analysis_report_v12.pdf')
    for name in ['build_receipt.json','visual_review.json']:copy(REPORT/name,OUT/'validation'/('v12_report_'+name))
    (OUT/'README.md').write_text('''# 미관측 고속도로의 기상·노면온도 추정과 결빙 조건 · v12

주변 AWS 관측망을 추가한 풍속의 지역 제외 MAE는0.563455→0.499955m/s로11.27%, 지역·겨울 동시 제외는0.567465→0.508379m/s로10.41% 감소했습니다. 별도 위치 API·실제CLI·전체 재학습을 검증했습니다. 기온·습도·노면온도·결빙과 기존 지도는 보존합니다. 대회 업로드 완료본이 아닙니다.

1. [24쪽 통합 보고서](reports/analysis_report_v12.pdf): 초록을 갱신하고 기존21쪽과 공간 관측망 비교·입력 점검2쪽을 통합했습니다.
2. [관측망 점검](research/latest/weather_network_viewer_20261101_v2/index.html): 23도로·34AWS·16고정 예시·5변수·원천 CSV. Chrome·Edge에서 엽니다.
3. [843구간·240일 기상 탐색](research/latest/weather_explorer_20261101_v2/index.html), [새 비교·출처·한계](docs/research/WEATHER_NETWORK_20261101.md).
4. [최신 검토 노트북](notebooks/weather_network_review_20261101.ipynb), [현재 구성과 검증](docs/delivery/REVIEW_BUNDLE_V12_20261101.md).
5. [새 풍속 실행·전체 재학습](research/wind_network_supplement/README.md), [기존 실행 방법](README_v11.md): 온도 v3·결빙 v2·안정화 습도와 명시적 F1 후보.

온도 MAE1.145698°C와 기온·습도의 AWS 대비 MAE감소22.10·12.91%는 이전 개발 결과이고 새 풍속은 AWS 대비49.13% 감소입니다. 알려진 ASOS0°C 후보는 기존 v2보다 평균 F1이 높지만 정밀도와 둘째 겨울이 낮습니다. 반복 개발 결과·공식 성적·현장 안전성은 구별합니다. 기존843구간의 풍속 지도는 이전 모형으로 보존했으며 새 모형 적용 지도로 표시하지 않습니다.

```powershell
python -m pip install -r requirements-notebook.txt
python scripts/review_submission_bundle.py --smoke --output local_review/my_v12.json
python scripts/check_notebook.py notebooks/weather_network_review_20261101.ipynb
```

기본 검사는 기존 예측144행과5코드셀을 확인하고, 최신 노트북은 새 비교·감사·화면3코드셀을 확인합니다. 새 풍속은research/wind_network_supplement에서 노트북3셀·전체 학습·CLI를 별도로 실행합니다. 원래 v11의 실행·모형·학습 자료·예측·데모·검산을 해시로 보존합니다. 전체 연구36제외모형의 재학습에는 원 비공개 작업공간의 추가 입력이 필요합니다. 미채택 모형·전체10분 공간 캐시는 넣지 않았습니다.

새 화면은16예시 원천과 전체 입력 품질 집계를 포함하며 도로 정답을 포함하지 않습니다. 관측소 간 차이는 오차·예측구간·결빙 확률이 아닙니다. 보호3+기개봉4지역 정답·인증정보는 새 연구에서 읽지 않았습니다. 원자료·모형·행단위예측은 GitHub 공유 대상에서 제외합니다. 현재 진입점은 이 README와 최상위 manifest이며 과거 안내는 각 시점의 이력입니다.
''','utf8')
    names=preserved();write(OUT/'provenance/v12_preparation.json',dict(at_utc=now(),sources=sources,preserved_v11_files=len(names),preservation=frozen))
    manifest(OUT,'model');verify_directory(OUT);print('PREPARED',len(names),'v11 files preserved',flush=True)


def verify():
    checks();names=preserved();verify_directory(OUT)
    target=OUT/'validation/v12_delivery.json'
    if target.exists():raise FileExistsError('Preserve verification')
    local=OUT/'local_review';local.mkdir(exist_ok=True)
    env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2')
    for label,command in [('core',[sys.executable,'scripts/review_submission_bundle.py','--smoke','--output','local_review/v12_core.json']),
        ('network_notebook',[sys.executable,'scripts/check_notebook.py','notebooks/weather_network_review_20261101.ipynb'])]:
        run=subprocess.run(command,cwd=OUT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
        log=local/(label+'.log');log.write_bytes(run.stdout);assert run.returncode==0,str(log)
        copy(log,OUT/'validation'/('v12_'+label+'.log'));print('PASSED',label,flush=True)
    wind=OUT/'research/wind_network_supplement'
    wind_command=[sys.executable,str(wind/'scripts/predict_wind_network.py'),'--bundle',str(wind),'--input',str(wind/'data/weather_example.csv'),
        '--aws-input',str(wind/'data/aws_example.parquet'),'--points',str(wind/'data/points_example.csv'),'--output',str(local/'wind.csv')]
    run=subprocess.run(wind_command,cwd=OUT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=300)
    (local/'wind.log').write_bytes(run.stdout);assert run.returncode==0,str(local/'wind.log')
    import pandas as pd
    read_csv=lambda p:pd.read_csv(p,dtype={'station':str},parse_dates=['time'],float_precision='round_trip')
    pd.testing.assert_frame_equal(read_csv(local/'wind.csv'),read_csv(wind/'data/reference_predictions.csv'),check_exact=True)
    browser=P/'weather_network_viewer_bundle_qa_20261101_v12';gui=env.copy()
    gui.update(PYTHONPATH=str(P/'browser_runtime_20261024'),PLAYWRIGHT_NODEJS_PATH='C:/Program Files/nodejs/node.exe')
    run=subprocess.run([sys.executable,str(ROOT/'scripts/audit_weather_network_viewer_20261101.py'),'--viewer',str(OUT/'research/latest/weather_network_viewer_20261101_v2'),
        '--output',str(browser)],cwd=ROOT,env=gui,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600)
    (local/'browser.log').write_bytes(run.stdout);assert run.returncode==0,'Copied browser check failed'
    for path in browser.iterdir():
        if path.is_file():copy(path,OUT/'validation/v12_browser'/path.name)
    qa=read(browser/'summary.json');original=read(P/STUDIES[2]/'summary.json')
    assert qa['html_sha256']==original['html_sha256']
    compare_browser_content(P/STUDIES[2],browser)
    errors=inspect_documents(OUT,[p.relative_to(OUT).as_posix() for p in OUT.rglob('*.md')]);assert not errors,'\n'.join(errors)
    assert read(local/'v12_core.json')['prediction_rows_identical']==144
    checks();preserved();write(target,dict(status='v12_delivery_verified',at_utc=now(),preserved_v11_files=len(names),
        basic_notebook_code_cells=5,latest_notebook_code_cells=3,example_prediction_rows_identical=144,
        relocated_browser=qa,relocated_browser_content_pixels_identical=True,native_form_controls_compared_semantically=True,
        wind_cli_rows_exact=432,production_model_changed=False,wind_network_supplement_added=True,competition_submitted=False))
    manifest(OUT,'model');verify_directory(OUT);print('VERIFIED v12',flush=True)


def package():
    checks();preserved();verify_directory(OUT);assert read(OUT/'validation/v12_delivery.json')['status']=='v12_delivery_verified'
    if CHANNELS.exists():raise FileExistsError('Preserve archives')
    CHANNELS.mkdir();documents=CHANNELS/'icy_road_documents';documents.mkdir()
    copy(REPORT/'analysis_report_v12.pdf',documents/'reports/analysis_report_v12.pdf')
    for name in ['weather_network_comparison_20261101.png','weather_network_audit_20261101.png']:
        copy(ROOT/'docs/images'/name,documents/'figures'/name)
    copy(P/'network_followup_review_20261101_v1/comparison_metrics.csv',documents/'data/network_comparison_metrics.csv')
    for name in ['RISK_CRITERIA.md','data/condition_evidence_criteria.csv']:
        copy(P/'submission_channels_20261101_v11/icy_road_documents'/name,documents/name)
    (documents/'README.md').write_text('''# 문서자료 · v12

[24쪽 통합 보고서](reports/analysis_report_v12.pdf)는 기존 기상·노면온도·결빙 평가와 주변 AWS 추가36적합, 입력 점검 화면을 담았습니다. 풍속 지역MAE를11.27%, 지역·겨울MAE를10.41% 추가 개선하고 별도 전체학습·CLI를 검증했습니다. 기온·습도·노면온도·결빙과 기존 지도는 보존합니다. 원자료·상태·제설 이력과 새 지역 일반화의 한계는 남아 있습니다.

[추가 비교 수치](data/network_comparison_metrics.csv), [관측망 비교 그림](figures/weather_network_comparison_20261101.png), [실제 입력 점검 화면](figures/weather_network_audit_20261101.png), [조건 기준표](RISK_CRITERIA.md)를 제공합니다. 실행 코드·모형·기존 포함 학습 자료·환경·노트북·오프라인 탐색·검산 근거는 별도 모델자료 ZIP에 있습니다. 실제 대회 제출 완료본이 아닙니다.
''','utf8')
    (documents/'AI_USAGE.md').write_text('''# AI 지원과 참가자 검토

Codex가 최신 공식 공개 안내·논문·공개 구현을 검토하고 주변 AWS 정보의36적합·독립 검산·입력 점검 화면·24쪽 보고서·로컬 검토 묶음을 지원했습니다. 사용자는 목표·지속 개선·예상 마감·비공개 저장소 커밋과 푸시 범위를 지시했습니다.

풍속만 사전조건을 통과해 독립 실행 묶음으로 개선했고, 실패한 기온·습도 후보는 채택하지 않았습니다. 기존 온도v3·결빙v2·안정화습도·보호평가를 보존했습니다. 원자료 없는 저장소 사본과 원천·화면·이력·인증정보 검사를 실제 실행했습니다. AI의 실행·시각 검토를 참가자의 직접 확인으로 기재하지 않습니다. 참가자 최종 판단은 실제 수행 후 추가해야 합니다. 전체 이력·실패·기여 구분은 모델자료의 AI_USAGE.md에 있습니다. 실제 대회 업로드나 외부 공개 전환은 수행하지 않았습니다.
''','utf8');manifest(documents,'documents')
    from src.kma_rwis_download import load_auth_key
    key=load_auth_key(ROOT/'secret.env').encode()
    for folder in [OUT,documents]:
        for name in read(folder/'manifest.json')['files']:
            path=folder/name;assert not name.endswith(('.env','.pem','.key','.hwp')) and '/.git/' not in '/'+name
            if path.suffix in ['.py','.md','.json','.txt','.html','.js','.yml','.log','.csv','.ipynb']:
                content=path.read_bytes();assert key not in content and not re.search(rb'(?:github_pat_[A-Za-z0-9_]{40,}|RGAPI-[A-Za-z0-9-]{30,}|sk-[A-Za-z0-9_-]{30,})',content),name
        errors=inspect_documents(folder,[n for n in read(folder/'manifest.json')['files'] if n.endswith('.md')]);assert not errors,'\n'.join(errors)
    archives={k:archive(folder,CHANNELS/('icy_road_'+k+'.zip'),'icy_road_'+k) for k,folder in [('documents',documents),('model',OUT)]}
    write(CHANNELS/'submission_receipt.json',dict(status='two_channel_archives_verified',at_utc=now(),archives=archives,
        model_source=OUT.relative_to(ROOT).as_posix(),preserved_v11_files=len(preserved()),production_model_changed=False,
        execution=read(OUT/'validation/v12_delivery.json'),competition_submitted=False))
    print(json.dumps(archives,ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',required=True,choices=['prepare','verify','package']);globals()[p.parse_args().stage]()
