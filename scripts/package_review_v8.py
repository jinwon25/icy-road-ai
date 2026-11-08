"""기존 실행 자산을 보존한 v8과 문서·모델 단일 폴더 ZIP을 생성·검증한다."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile
import nbformat as nb

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,now,verify_preserved
from scripts.review_submission_bundle import verify_directory
from scripts.package_submission_channels import verify_channel_archive
from scripts.check_markdown import inspect_documents
from src.data_source import sha256_file as sha

P=ROOT/'outputs/private'
OLD=P/'submission_candidate_20261026_v7'
OUT=P/'submission_candidate_20261031_v8'
CHANNELS=P/'submission_channels_20261031_v8'
REPORT=P/'report_update_20261031_v3'
CORE=('model/','data/','exports/','figures/','code/','src/','notebooks/','reports/','demo/','licenses/')
USER_DOCUMENT='docs/research/ICING_GAP_AND_SYNOPTIC_20261025.md'
STUDIES=['objective_icing_20261031_v2','reanalysis_temperature_20261031_v1',
    'reanalysis_icing_20261031_v1','antecedent_forcing_20261031_v2']
SPATIAL=['vulnerability_inventory_review_20261031_v1','official_culvert_anchors_20261031_v2',
    'official_chainage_alignment_20261031_v1','vulnerability_map_comparison_20261031_v1',
    'official_inventory_viewer_20261031_v1','official_inventory_viewer_qa_20261031_v2']


def copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)


def source_checks():
    frozen=verify_preserved()
    assert sha(OLD.with_suffix('.zip'))=='b24329dca5b79862603f324eb15541e0bfe1e45fbd26fcc95c5ae4abb5f77c76'
    visual=read(REPORT/'visual_review.json');receipt=read(REPORT/'build_receipt.json')
    assert visual['status']=='passed' and visual['pages']==13
    assert visual['pdf_sha256']==receipt['pdf_sha256']==sha(REPORT/'analysis_report_v8.pdf')
    assert (REPORT/'analysis_report_v8.md').read_text(encoding='utf8')==(ROOT/'docs/delivery/ANALYSIS_REPORT_20261031.md').read_text(encoding='utf8')
    for name,digest in receipt['sources'].items():assert sha(ROOT/name)==digest,name
    for name in STUDIES:
        audit=read(P/name/'independent_verification.json')
        assert audit['status']=='passed' and audit['summary_sha256']==sha(P/name/'summary.json')
    return frozen


def core_check():
    old=read(OLD/'manifest.json')['files'];names=[n for n in old if n.startswith(CORE)
        or n in ['extended_training_plan.json','requirements.txt','requirements-notebook.txt']]
    for name in names:assert sha(OUT/name)==old[name]['sha256'],name
    return names


def sync_source():
    git=['git','-c','safe.directory='+ROOT.as_posix()]
    names=subprocess.check_output(git+['ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode('utf8').split('\0')
    old=read(OLD/'manifest.json')['files'];records={}
    for name in sorted(set(filter(None,names))):
        if name==USER_DOCUMENT:continue
        if not (name.startswith(('docs/','scripts/','src/','tests/','config/','notebooks/')) or name in ['README.md','AI_USAGE.md','requirements-research.txt']):continue
        if name in old and name.startswith(CORE):continue
        path=ROOT/name
        if not path.is_file() or path.suffix not in ['.md','.py','.json','.yml','.yaml','.ipynb','.png','.jpg','.txt']:continue
        if name in ['docs/images/inventory_comparison_20261031.png','docs/images/inventory_comparison_20261031_v2.png']:continue
        target=OUT/('README_repository.md' if name=='README.md' else name);copy(path,target);records[name]=sha(path)
    return records


def manifest(folder,channel):
    path=folder/'manifest.json'
    if path.exists():
        i=1
        while (folder/f'provenance/v8_previous_manifest_{i:02d}.json').exists():i+=1
        target=folder/f'provenance/v8_previous_manifest_{i:02d}.json';target.parent.mkdir(exist_ok=True);path.rename(target)
    records={p.relative_to(folder).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p))
        for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'
        and p.relative_to(folder).parts[0]!='local_review'}
    value=dict(package_label='v8',channel=channel,status='private_review_candidate',at_utc=now(),files=records,
        current_report='reports/analysis_report_v8.pdf',competition_submitted=False)
    if channel=='model':value.update(current_notebook='notebooks/submission_review_v8.ipynb',production_model_version='v3',icing_version='v2',production_model_changed=False)
    write(path,value)


MODEL_README='''# 미관측 도로의 온도·결빙 조건과 공식 취약구간 비교 · v8

기상 이력으로 도로 노면온도를 추정하고, 결빙 판별의 한계와 공식 취약구간의 공간적 비교를 제공하는 비공개 검토 결과물입니다. 온도 모델 v3·결빙 판정 v2는 유지합니다. 후속 98적합은 안정적인 개선을 확인하지 못해 미채택했고, 최신 도로 자료로 공식 목록과 현장 확인 범위를 비교하는 기능을 추가했습니다.

## 읽고 실행하기

1. [13쪽 통합 보고서](reports/analysis_report_v8.pdf): 온도 개선, 결빙 한계, 추가 입력 비교, 공식 목록·위치 오차·두 겨울 노출.
2. [공식 목록 비교 화면](research/latest/official_inventory_viewer_20261031_v1/index.html): 인터넷 없이 노선·방향·목록 버전·구간 상세를 확인합니다.
3. [최종 학습·추론 노트북](notebooks/submission_review_v8.ipynb), [후속 연구·공간 비교 노트북](notebooks/latest_research_review_v8.ipynb).
4. [결빙 조건 기준표](docs/delivery/RISK_CRITERIA_20261031.md), [CSV 규약](docs/delivery/CSV_CONTRACT.md), [AI 활용 기록](AI_USAGE.md).

Windows·Python 3.11·CPU에서 확인합니다. 주요 라이브러리는 버전을 고정한 `requirements.txt`·`requirements-notebook.txt`에 있습니다. GPU·CUDA·외부 AI 서비스나 인증키가 필요하지 않습니다. 최초 패키지 설치 후 포함 자료의 추론·재학습은 로컬에서 실행합니다.

```powershell
python -m pip install -r requirements-notebook.txt
$env:OMP_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
python scripts/review_submission_bundle.py --smoke --output local_review/my_review.json
python scripts/check_notebook.py notebooks/latest_research_review_v8.ipynb
python -X utf8 code/train.py --output local_review/my_refit
python -X utf8 code/predict.py --input data/weather_example.csv --output local_review/my_prediction.csv --output-start 2024-12-15 --output-end 2024-12-16
```

기존 출력 이름을 재사용하지 않습니다. 첫 명령은 전체 파일 해시와 예측 144행의 정확한 일치, 현재 노트북의 5코드 셀을 검사합니다. 재학습은 허용 23곳·두 겨울의 포함 자료와 고정 계획을 사용합니다. 예제는 실행 확인이며 독립 성능평가가 아닙니다.

## 결과를 해석하는 범위

동일 개발 9곳·두 겨울·310,091유효쌍에서 온도 MAE는 1.145698°C로 기존 대비 13.66% 감소했습니다. 결빙 일별 평균 F1은 현재 0.026554로 같은 입력 기온 기준선 0.036601보다 낮습니다. 반복 개발 점수이며 공식 성적이 아닙니다. 온도 개선을 결빙 개선으로 표현하지 않습니다.

500m 843개와 1km 423개는 같은 도로의 서로 다른 분할입니다. 공식 암거로 500m 821구간의 이정을 제한적으로 보간했고 22구간은 미확정입니다. 두 겨울의 노출·최신 목록 관계를 기준으로 얻은 318개 보고 구간은 방향별 8개 넓은 연속 확인 구간이며 독립적인 신규 위험 발견이 아닙니다. 위치 오차, 기상자료 공유와 동률을 화면·CSV에 표시합니다. 사고확률·공식 A/B/C 등급·측량 위치를 새로 검증한 결과가 아닙니다.

## 폴더와 보존

| 경로 | 구성 |
| --- | --- |
| data/ · model/ | 최종 모델 학습·예제 자료, 저장 모델·기존 예측 |
| src/ · code/ · scripts/ | 처리·학습·평가·추론·후속 연구 코드 |
| notebooks/ | 최종 실행과 후속 결과 검토. 날짜별 연구 노트북은 원 작업 공간 입력이 필요한 경우를 본문에 명시 |
| demo/ | 기존 오프라인 구간 탐색·실제 화면 영상·추론 출력 시각화 영상 |
| figures/ · exports/ | 기존 지도·Shapefile·구간별 CSV와 10분 출력 |
| research/latest/ | 후속 비교 집계·선택·검산·공식 목록 GIS·CSV·새 오프라인 화면 |
| reports/ · docs/ | 현재 13쪽 보고서, 과거 보고서와 자세한 방법·이용조건 |
| licenses/ · provenance/ · validation/ | 출처·보존·검산·실행 기록 |

후속 실패 실험의 모든 원자료·예측 캐시는 포함하지 않았습니다. 해당 연구의 전체 학습·입력 구축 스크립트는 원 비공개 작업 공간을 대상으로 하며, 이 묶음의 기본 실행 경로와 구별합니다. 후속 결과 검토 노트북은 묶음 내부 자료만 사용합니다. 기존 모델·데이터·코드·데모·보고서는 해시로 보존하고, 최신 보고서는 최상위 manifest의 `current_report`로 지정했습니다.

10월 27일 접수 개시 공지와 제출 화면에 따라 문서자료·모델자료를 각각 단일 폴더 ZIP으로 준비합니다. 마감일은 제공 본문에 없어 미확인입니다. 이 묶음은 로컬 검토 후보로 실제 접수 완료가 아닙니다. 대회 자료·모델·예측은 승인받은 비공개 심사 범위에서 사용하고 인증정보와 보호 정답은 포함하지 않습니다.
'''


def notebooks():
    previous=nb.read(OLD/'notebooks/submission_review_v7.ipynb',as_version=4)
    original=[c for c in previous.cells if c.cell_type=='code']
    for cell in previous.cells:
        if cell.cell_type=='markdown':cell.source=cell.source.replace(' · v7',' · v8').replace('analysis_report_v7.pdf','analysis_report_v8.pdf')
    previous.cells.append(nb.v4.new_markdown_cell('''## 후속 연구와 공식 목록 비교

새 보고서 6–8절에서 후속 98적합의 미채택 근거와 공식 목록·두 겨울 노출·추정 이정의 한계를 확인합니다.
`notebooks/latest_research_review_v8.ipynb`는 포함 집계와 새 공간 자료를 검토합니다.
화면은 `research/latest/official_inventory_viewer_20261031_v1/index.html`입니다. 기존 실행 모델과 이 노트북의 5개 코드 셀은 보존합니다.'''))
    assert original==[c for c in previous.cells if c.cell_type=='code']
    nb.write(previous,OUT/'notebooks/submission_review_v8.ipynb')
    new=nb.v4.new_notebook(cells=[nb.v4.new_markdown_cell('''# 후속 연구와 공식 취약구간 비교

이 노트북은 제출 묶음 내부 집계만 읽습니다. 새 학습·독립 평가·외부 API 호출을 수행하지 않습니다.
최종 학습·추론은 `submission_review_v8.ipynb`에서 확인합니다. 위에서 아래로 실행합니다.'''),
        nb.v4.new_code_cell('''from pathlib import Path
import json, hashlib
import pandas as pd
from IPython.display import display
ROOT=next(p for p in [Path.cwd(),*Path.cwd().parents] if (p/'extended_training_plan.json').exists())
P=ROOT/'research/latest'
read=lambda p: json.loads(p.read_text(encoding='utf8'))
studies=['objective_icing_20261031_v2','reanalysis_temperature_20261031_v1','reanalysis_icing_20261031_v1','antecedent_forcing_20261031_v2']
rows=[]
for name in studies:
    summary=read(P/name/'summary.json');audit=read(P/name/'independent_verification.json')
    assert audit['status']=='passed' and audit['summary_sha256']==hashlib.sha256((P/name/'summary.json').read_bytes()).hexdigest()
    if name.startswith('reanalysis_temperature'):
        value=summary['reports']['era5_raw']['regression']['pooled']['mae'];metric='MAE (C)'
    else:
        key='selected_mean_f1' if name.startswith('reanalysis_icing') else 'mean_f1'
        value=summary['reports'][key]['all']['f1_fixed_population'];metric='Daily F1'
    rows.append({'study':name,'metric':metric,'primary':value,'audit':audit['status']})
display(pd.DataFrame(rows))'''),
        nb.v4.new_markdown_cell('''## 목록과 현장 확인 범위

75백분위 이상에 동률을 모두 포함하므로 정확히 상위 25%가 아닙니다. 방향별 8개 연속 구간은 실제 결빙 확률이나
공식 위험등급을 검증한 결과가 아닙니다. 2026년 목록을 2024·2025년 당시 지정 현황으로 소급하지 않습니다.'''),
        nb.v4.new_code_cell('''viewer=P/'official_inventory_viewer_20261031_v1'
meta=read(viewer/'summary.json')
for name in ['corridors.csv','threshold_ties.csv','index.html','viewer_data.json']:
    assert hashlib.sha256((viewer/name).read_bytes()).hexdigest()==meta['files'][name]
corridors=pd.read_csv(viewer/'corridors.csv');ties=pd.read_csv(viewer/'threshold_ties.csv')
assert len(corridors)==8 and not corridors.official_chainage_verified.any()
display(corridors);display(ties)
alignment=read(P/'official_chainage_alignment_20261031_v1/summary.json')
display(pd.DataFrame(alignment['validation']).T)
display(pd.Series(alignment['cctv_diagnostic'],name='Separate CCTV diagnostic'))
print(viewer/'index.html')''')],metadata=previous.metadata)
    nb.validate(new);nb.write(new,OUT/'notebooks/latest_research_review_v8.ipynb')


def prepare():
    if OUT.exists():raise FileExistsError('Preserve previous bundle')
    frozen=source_checks();verify_directory(OLD)
    for name in read(OLD/'manifest.json')['files']:copy(OLD/name,OUT/name)
    copy(OLD/'manifest.json',OUT/'provenance/v7_manifest.json');copy(OLD/'README.md',OUT/'README_v7.md')
    sources=sync_source()
    for name in STUDIES+SPATIAL:
        for path in (P/name).rglob('*'):
            if not path.is_file() or path.suffix not in ['.json','.csv','.npz','.gpkg','.html']:continue
            if path.name=='cctv_independent_diagnostic.csv':continue
            copy(path,OUT/'research/latest'/name/path.relative_to(P/name))
    copy(REPORT/'analysis_report_v8.pdf',OUT/'reports/analysis_report_v8.pdf')
    copy(REPORT/'build_receipt.json',OUT/'validation/v8_report_build.json')
    copy(REPORT/'visual_review.json',OUT/'validation/v8_report_visual.json')
    (OUT/'README.md').write_text(MODEL_README,encoding='utf8')
    notebooks();preserved=core_check()
    write(OUT/'provenance/v8_preparation.json',dict(at_utc=now(),source_files=sources,preservation=frozen,
        preserved_core_files=preserved,excluded_original_user_document=USER_DOCUMENT,
        copied_research_inputs='aggregates, receipts and selected small models; not all historical input caches'))
    manifest(OUT,'model');verify_directory(OUT);print('PREPARED',len(preserved),'preserved core files',flush=True)


def verify():
    source_checks();core=core_check();verify_directory(OUT)
    target=OUT/'validation/v8_delivery.json'
    if target.exists():raise FileExistsError('Preserve completed verification')
    local=OUT/'local_review';local.mkdir(exist_ok=True)
    attempt=1
    while any(local.glob(f'v8_{attempt:02d}*')):attempt+=1
    prefix=f'v8_{attempt:02d}'
    env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
    commands=[('execution',[sys.executable,'scripts/review_submission_bundle.py','--smoke','--output',f'local_review/{prefix}.json']),
        ('latest_notebook',[sys.executable,'scripts/check_notebook.py','notebooks/latest_research_review_v8.ipynb'])]
    for name,command in commands:
        run=subprocess.run(command,cwd=OUT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
        log=local/(prefix+'_'+name+'.driver.log');log.write_bytes(run.stdout)
        assert run.returncode==0,str(log)
    result=read(local/(prefix+'.json'));assert result['prediction_rows_identical']==144
    assert result['notebook']=='notebooks/submission_review_v8.ipynb'
    for path in local.glob(prefix+'*'):copy(path,OUT/'validation/v8_execution'/path.name)
    errors=inspect_documents(OUT,[p.relative_to(OUT).as_posix() for p in OUT.rglob('*.md')])
    assert not errors,'\n'.join(errors)
    source_checks();core_check()
    write(target,dict(status='v8_delivery_verified',at_utc=now(),core_files_preserved=len(core),execution=result,
        current_notebook_code_cells=5,latest_notebook_code_cells=2,production_model_changed=False,competition_submitted=False))
    manifest(OUT,'model');verify_directory(OUT);print('VERIFIED v8',flush=True)


def archive(folder,path,root_name):
    verify_directory(folder);records=read(folder/'manifest.json')['files']
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in sorted(records):z.write(folder/name,root_name+'/'+name)
        z.write(folder/'manifest.json',root_name+'/manifest.json')
    return verify_channel_archive(path,root_name)


def package():
    source_checks();core_check();verify_directory(OUT)
    assert read(OUT/'validation/v8_delivery.json')['status']=='v8_delivery_verified'
    if CHANNELS.exists():raise FileExistsError('Preserve previous archives')
    CHANNELS.mkdir();documents=CHANNELS/'icy_road_documents';documents.mkdir()
    copy(REPORT/'analysis_report_v8.pdf',documents/'reports/analysis_report_v8.pdf')
    copy(ROOT/'docs/images/inventory_comparison_20261031_v3.png',documents/'figures/official_inventory_comparison.png')
    copy(ROOT/'docs/delivery/RISK_CRITERIA_20261031.md',documents/'RISK_CRITERIA.md')
    copy(OUT/'data/condition_evidence_criteria.csv',documents/'data/condition_evidence_criteria.csv')
    (documents/'README.md').write_text('''# 문서자료 · 전북 고속도로 노면온도·결빙 조건 분석

[13쪽 통합 보고서](reports/analysis_report_v8.pdf)는 개요·활용 데이터·모델 개발·실험·평가·기대 활용과 한계를 설명합니다. 분석 기준일은 2026년 10월 31일입니다. [공식 목록 비교 그림](figures/official_inventory_comparison.png)과 [조건 기준표](RISK_CRITERIA.md)를 함께 제공합니다.

동일 개발 9곳·두 겨울에서 온도 MAE는 1.145698°C로 기존 대비 13.66% 감소했습니다. 현재 결빙 F1 0.026554는 기온 기준선 0.036601보다 낮습니다. 후속 98적합도 안정적 개선을 확인하지 못해 실행 모델은 유지합니다. 반복 개발 점수이며 공식 대회 점수가 아닙니다.

최신 공식 자료로 만든 지도는 추정 이정과 조건 노출의 비교입니다. 318개 보고 구간을 방향별 8개 연속 현장 확인 범위로 묶었으며 실제 결빙확률·사고확률·공식 위험등급을 검증한 결과는 아닙니다. 동률과 기상자료 공유 범위를 표시합니다.

실행 코드·모델·학습 자료·환경·노트북·데모·GIS·CSV는 별도 모델자료 ZIP에 있습니다. 이 문서 ZIP만으로 모델을 실행하는 것은 아닙니다. AI 지원과 참가자 기여의 구분은 보고서 마지막 쪽 및 모델자료의 AI_USAGE.md에 기록합니다. 참가자가 직접 수행하지 않은 검산을 직접 기여로 기재하지 않았습니다.

단일 폴더로 압축한 비공개 로컬 검토 후보이며 실제 접수 완료본이 아닙니다. 접수 개시는 확인했지만 제공 공지 본문에 마감 날짜는 없습니다.
''',encoding='utf8')
    manifest(documents,'documents')
    secret_values=[]
    for line in (ROOT/'secret.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            value=line.split('=',1)[1].strip().strip('\"\x27')
            if len(value)>=12:secret_values.append(value.encode())
    for folder in [OUT,documents]:
        records=read(folder/'manifest.json')['files']
        assert not inspect_documents(folder,[n for n in records if n.endswith('.md')])
        for name in records:
            path=folder/name
            assert path.suffix not in ['.env','.pem','.key','.hwp'] and '/.git/' not in '/'+name
            if path.suffix in ['.py','.json','.md','.txt','.ipynb','.html','.js','.log','.yml','.csv']:
                data=path.read_bytes();assert not any(value in data for value in secret_values),name
                assert not re.search(rb'(?:github_pat_[A-Za-z0-9_]{40,}|RGAPI-[A-Za-z0-9-]{30,}|sk-[A-Za-z0-9_-]{30,})',data),name
    results={'documents':archive(documents,CHANNELS/'icy_road_documents.zip','icy_road_documents'),
        'model':archive(OUT,CHANNELS/'icy_road_model.zip','icy_road_model')}
    verify_directory(OLD);source_checks()
    write(CHANNELS/'submission_receipt.json',dict(status='two_channel_archives_verified',at_utc=now(),archives=results,
        model_source=OUT.relative_to(ROOT).as_posix(),preserved_core_files=len(core_check()),
        execution=read(OUT/'validation/v8_delivery.json'),competition_submitted=False,production_model_changed=False))
    print(json.dumps(results,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',required=True,choices=['prepare','verify','package'])
    globals()[parser.parse_args().stage]()
