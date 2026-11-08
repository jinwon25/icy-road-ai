"""검산된 풍속 구간 결과·탐색·26쪽 보고서를 기존 v12와 분리된 두 ZIP으로 만든다."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import nbformat as nb

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import read,write,copy,sha,verify_channel_archive
from scripts.package_review_v8 import archive
from scripts.review_submission_bundle import verify_directory
from scripts.check_markdown import inspect_documents
from scripts.evaluate_objective_icing import verify_preserved

P=ROOT/'outputs/private'
OLD=P/'submission_candidate_20261101_v12'
OUT=P/'submission_candidate_20261106_v13'
CHANNELS=P/'submission_channels_20261106_v13'
REPORT=P/'report_update_20261106_v13'
SPATIAL=P/'wind_network_segment_projection_20261102_v1'
VIEWER=P/'weather_explorer_20261106_v13'
QA=P/'weather_explorer_validation_20261106_v13'
SYNC=['AI_USAGE.md','docs/STATUS.md','docs/START_HERE.md','docs/README.md',
      'docs/delivery/CSV_CONTRACT.md','docs/delivery/FOLLOWUP_REVIEW_20261102.md',
      'docs/delivery/SUBMISSION_READINESS_20261106.md','docs/competition/OFFICIAL_UPDATE_20261106.md',
      'docs/research/NETWORK_HISTORY_PLAN_20261102.md','docs/images/wind_network_projection_20261102.png',
      'docs/images/weather_network_history_20261102.png','scripts/build_weather_explorer_20261101.py',
      'scripts/build_submission_report_v13.py','scripts/package_review_v13.py']
UPDATED=set(SYNC)|{'README.md','README_repository.md'}


def now():return datetime.now(timezone.utc).isoformat()


def checks():
    verify_directory(OLD)
    prior=read(P/'submission_channels_20261101_v12/submission_receipt.json')
    for channel in ['documents','model']:
        path=P/'submission_channels_20261101_v12'/f'icy_road_{channel}.zip'
        assert sha(path)==prior['archives'][channel]['sha256']
    summary=read(SPATIAL/'summary.json');audit=read(SPATIAL/'independent_verification.json')
    assert audit['status']=='passed' and audit['summary_sha256']==sha(SPATIAL/'summary.json')
    for name,digest in summary['files'].items():assert sha(SPATIAL/name)==digest,name
    supplement=read(OLD/'research/wind_network_supplement/model/metadata.json')
    assert summary['applied_wind_model_sha256']==supplement['sha256']
    report=read(REPORT/'build_receipt.json');visual=read(REPORT/'visual_review.json')
    assert visual['status']=='passed' and report['pdf_sha256']==visual['pdf_sha256']==sha(REPORT/'analysis_report_v13.pdf')
    assert report['previous_pages_pixel_identical']==24 and report['pages']==26
    assert sha(OLD/'reports/analysis_report_v12.pdf')==report['source_pdf_sha256']
    for name,digest in report['sources'].items():assert sha(ROOT/name)==digest,name
    qa=read(QA/'summary.json');visual=read(QA/'visual_review.json')
    assert qa['status']=='passed' and visual['status']=='passed'
    assert qa['html_sha256']==visual['html_sha256']==sha(VIEWER/'index.html')
    assert read(VIEWER/'summary.json')['source_summary_sha256']==sha(SPATIAL/'summary.json')
    for name,digest in read(VIEWER/'summary.json')['files'].items():assert sha(VIEWER/name)==digest,name
    return verify_preserved()


def preserved():
    records=read(OLD/'manifest.json')['files']
    names=[name for name in records if name not in UPDATED]
    for name in names:assert sha(OUT/name)==records[name]['sha256'],name
    return names


def manifest(folder,channel):
    files={p.relative_to(folder).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p))
        for p in folder.rglob('*') if p.is_file() and p!=folder/'manifest.json'
        and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.relative_to(folder).parts[0]!='local_review'}
    value=dict(package_label='v13',channel=channel,status='local_submission_candidate',at_utc=now(),
        files=files,current_report='reports/analysis_report_v13.pdf',competition_submitted=False)
    if channel=='model':value.update(current_notebook='notebooks/submission_review_v11.ipynb',
        latest_notebook='notebooks/spatial_wind_review_v13.ipynb',production_model_version='v3',icing_version='v2',
        production_model_changed=False,current_weather_explorer='research/latest/weather_explorer_20261106_v13/index.html',
        current_weather_projection='research/latest/wind_network_segment_projection_20261102_v1',
        current_wind_model_sha256=read(SPATIAL/'summary.json')['applied_wind_model_sha256'])
    path=folder/'manifest.json'
    if path.exists():path.unlink()
    write(path,value)


def notebook():
    n=nb.v4.new_notebook();n.metadata.kernelspec=dict(display_name='Python 3',language='python',name='python3')
    n.cells=[nb.v4.new_markdown_cell('# 풍속 구간 결과 검토 · v13\n\n843구간·240일의 집계 CSV·GIS와 오프라인 화면을 검토합니다. 모델은 재학습하지 않으며 보호 정답을 읽지 않습니다. 기존 학습·추론 진입점은 `submission_review_v11.ipynb`입니다.'),
        nb.v4.new_code_cell("from pathlib import Path\nimport hashlib, json, gzip\nimport pandas as pd\nroot=Path.cwd().resolve()\nif root.name=='notebooks': root=root.parent\nread=lambda p:json.loads(p.read_text(encoding='utf8'))\nsha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()\nm=read(root/'manifest.json')\nfor name,r in m['files'].items():\n    p=root/name\n    assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],name\nprint(m['package_label'],len(m['files']),'files verified')"),
        nb.v4.new_code_cell("projection=root/m['current_weather_projection']\nsummary=read(projection/'summary.json')\naudit=read(projection/'independent_verification.json')\nassert audit['status']=='passed' and audit['summary_sha256']==sha(projection/'summary.json')\nassert summary['applied_wind_model_sha256']==m['current_wind_model_sha256']\nfor name,digest in summary['files'].items(): assert sha(projection/name)==digest,name\ndaily=pd.read_csv(projection/'weather_segment_daily.csv.gz')\nwinter=pd.read_csv(projection/'weather_segments_500m.csv')\nassert len(daily)==202320 and len(winter)==1686 and daily.seg_id.nunique()==843\nassert not daily.duplicated(['seg_id','date']).any()\nassert daily.groupby('seg_id').size().eq(240).all()\nprint('843 segments; 240 dates; 202320 daily rows')\ndisplay(winter[['seg_id','winter','wind_speed_mean','wind_network_outside_fraction']].head())"),
        nb.v4.new_code_cell("from IPython.display import display, HTML\nviewer=root/'research/latest/weather_explorer_20261106_v13'\nv=read(viewer/'summary.json')\nassert v['wind_network_projection'] and v['source_summary_sha256']==sha(projection/'summary.json')\nfor name,digest in v['files'].items(): assert sha(viewer/name)==digest,name\npayload=json.loads(gzip.decompress((viewer/'viewer_data.json.gz').read_bytes()))\nassert len(payload['rows'])==843 and all(len(r['days'])==240 for r in payload['rows'])\nprint(payload['model_note'])\ndisplay(HTML('<a href=\"../research/latest/weather_explorer_20261106_v13/index.html\">현재 기상 지도 열기</a>'))"),
        nb.v4.new_markdown_cell('실측 구간 정확도를 새로 확인한 자료가 아닙니다. 입력 범위 이탈은 오차·확률이 아니며, 결빙 v2 F1 0.026554는 기온 기준선 0.036601보다 낮습니다. 미채택 147특성 후보와 기존 결과는 보존합니다.')]
    nb.write(n,OUT/'notebooks/spatial_wind_review_v13.ipynb')


def prepare():
    if OUT.exists():raise FileExistsError('Preserve previous candidate')
    frozen=checks()
    for name in read(OLD/'manifest.json')['files']:copy(OLD/name,OUT/name)
    copy(OLD/'manifest.json',OUT/'provenance/v12_manifest.json')
    copy(OLD/'README.md',OUT/'README_v12.md')
    for name in SYNC:copy(ROOT/name,OUT/name)
    copy(ROOT/'README.md',OUT/'README_repository.md')
    for source in [SPATIAL,VIEWER,P/'wind_network_projection_review_20261102_v2',P/'network_history_review_20261102_v1']:
        for path in source.iterdir():
            if path.is_file() and path.suffix in {'.json','.csv','.gz','.gpkg','.parquet','.html','.png'}:
                copy(path,OUT/'research/latest'/source.name/path.name)
    for path in QA.iterdir():
        if path.is_file():copy(path,OUT/'validation/v13_weather_explorer'/path.name)
    for name in ['build_receipt.json','visual_review.json']:copy(REPORT/name,OUT/'validation'/('v13_report_'+name))
    copy(REPORT/'analysis_report_v13.pdf',OUT/'reports/analysis_report_v13.pdf')
    notebook()
    (OUT/'README.md').write_text('''# 전북 고속도로 기상·노면온도·결빙 분석 · v13

채택된 69특성 풍속의 843구간·두 겨울 결과를 CSV·GIS·오프라인 탐색에 통합했습니다. 기존 노면온도 v3·결빙 v2·기온·습도와 과거 자산을 보존합니다. 이 묶음은 로컬 제출 후보입니다.

1. [26쪽 분석 보고서](reports/analysis_report_v13.pdf): 기존 24쪽과 새 풍속 구간 적용·제출 검토 2쪽.
2. [현재 843구간·240일 기상 지도](research/latest/weather_explorer_20261106_v13/index.html): Chrome·Edge에서 열고 풍속·겨울·노선·구간을 선택합니다. 현재 풍속은 11월 2일 관측망 적용 결과입니다.
3. [최신 공간 결과 검토 노트북](notebooks/spatial_wind_review_v13.ipynb), [CSV 규약](docs/delivery/CSV_CONTRACT.md), [제출 준비 현황](docs/delivery/SUBMISSION_READINESS_20261106.md).
4. [학습·추론·F1 대안·풍속 CLI 실행](README_v12.md): 기존 실행 방법을 따릅니다. 기본 실행 모델과 F1 대안은 별도 선택입니다.

현재 집계 자료는 `research/latest/wind_network_segment_projection_20261102_v1/`의 일별 202,320행 CSV·Parquet, 겨울별 1,686행 CSV·GIS입니다. 각 10분 시점의 대용량 공간 캐시는 원 작업공간에 별도 보관합니다. 이전 화면과 PDF는 당시 결과를 보존한 이력이며, 현재 풍속은 위의 새 화면·집계를 사용합니다. 1km 온도·조건 지도는 기존 결과입니다.

```powershell
python -m pip install -r requirements-notebook.txt
python -X utf8 scripts/review_submission_bundle.py --smoke --output local_review/my_v13.json
python -X utf8 scripts/check_notebook.py notebooks/spatial_wind_review_v13.ipynb
```

기본 검사는 기존 예제 144행과 실행 노트북을 확인합니다. 최신 노트북은 집계 자료·화면의 해시와 843구간·240일을 별도로 확인합니다. 포함 모델은 인증키·외부 예측 API 없이 실행합니다. 설치에는 패키지 다운로드가 필요합니다.

노면온도 개발 MAE 1.145698°C, 풍속 지역 제외 MAE 0.499955m/s는 반복 개발 결과입니다. 결빙 F1 0.026554는 ASOS 0°C 기준선 0.036601보다 낮습니다. 풍속 개선을 결빙 향상으로 해석하지 않습니다. 새 풍속 입력 범위 이탈은 두 겨울 길이 가중 26.40%·30.39%이며 오차나 확률이 아닙니다. 147특성 후보는 악화해 미채택했습니다.

문서자료·모델자료 ZIP을 별도로 제출하는 형식입니다. 결과물 마감 날짜·시각·용량 제한·계정 승인·참가자 최종 검토는 확인이 필요합니다. 실제 대회 업로드 이력을 확인한 자료가 아닙니다. 원자료·인증정보의 이용조건과 AI 지원 범위는 포함된 AI_USAGE.md를 따릅니다.
''','utf8')
    write(OUT/'provenance/v13_preparation.json',dict(at_utc=now(),preservation=frozen,preserved_v12_files=len(preserved()),
        source_manifest_sha256=sha(OLD/'manifest.json'),new_projection_sha256=sha(SPATIAL/'summary.json'),
        existing_models_or_outcomes_changed=False,protected_outcomes_read=False,competition_submitted=False))
    manifest(OUT,'model');verify_directory(OUT)
    print('PREPARED v13',len(preserved()),'v12 files preserved',flush=True)


def run(label,command,cwd=OUT,environment=None):
    env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
    if environment:env.update(environment)
    result=subprocess.run(command,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
    target=OUT/'local_review'/(label+'.log');target.parent.mkdir(exist_ok=True);target.write_bytes(result.stdout)
    if result.returncode:raise RuntimeError('Check '+str(target))
    print('PASSED',label,flush=True)


def verify():
    checks();preserved();verify_directory(OUT)
    target=OUT/'validation/v13_delivery.json'
    if target.exists():raise FileExistsError('Preserve completed verification')
    run('v13_core',[sys.executable,'-X','utf8','scripts/review_submission_bundle.py','--smoke','--output','local_review/v13_core.json'])
    run('v13_notebook',[sys.executable,'-X','utf8','scripts/check_notebook.py','notebooks/spatial_wind_review_v13.ipynb'])
    wind=OUT/'research/wind_network_supplement'
    run('v13_wind',[sys.executable,str(wind/'scripts/predict_wind_network.py'),'--bundle',str(wind),
        '--input',str(wind/'data/weather_example.csv'),'--aws-input',str(wind/'data/aws_example.parquet'),
        '--points',str(wind/'data/points_example.csv'),'--output',str(OUT/'local_review/v13_wind.csv')])
    import pandas as pd
    load=lambda p:pd.read_csv(p,dtype={'station':str},parse_dates=['time'],float_precision='round_trip')
    actual=load(OUT/'local_review/v13_wind.csv');expected=load(wind/'data/reference_predictions.csv')
    pd.testing.assert_frame_equal(actual,expected,check_exact=True)
    assert len(actual)==432
    # 새 화면의 상대 다운로드와 수치를 실제 배포 위치에서도 다시 확인한다.
    viewer_qa=P/'weather_explorer_bundle_qa_20261106_v13'
    run('v13_relocated_browser',[sys.executable,str(ROOT/'scripts/audit_weather_explorer_20261101.py'),
        '--viewer',str(OUT/'research/latest'/VIEWER.name),'--output',str(viewer_qa)],cwd=ROOT,
        environment={'PYTHONPATH':str(P/'browser_runtime_20261024'),'PLAYWRIGHT_NODEJS_PATH':'C:/Program Files/nodejs/node.exe'})
    browser=read(viewer_qa/'summary.json');assert browser['html_sha256']==sha(VIEWER/'index.html')
    for path in viewer_qa.iterdir():
        if path.is_file():copy(path,OUT/'validation/v13_relocated_browser'/path.name)
    for path in (OUT/'local_review').glob('v13*.log'):copy(path,OUT/'validation/v13_execution'/path.name)
    copy(OUT/'local_review/v13_core.json',OUT/'validation/v13_execution/core.json')
    errors=inspect_documents(OUT,[p.relative_to(OUT).as_posix() for p in OUT.rglob('*.md')])
    assert not errors,'\n'.join(errors)
    core=read(OUT/'local_review/v13_core.json');assert core['prediction_rows_identical']==144
    assert '3 code cells' in (OUT/'local_review/v13_notebook.log').read_text(encoding='utf8')
    checks();preserved()
    write(target,dict(status='v13_delivery_verified',at_utc=now(),preserved_v12_files=len(preserved()),
        example_prediction_rows_identical=144,wind_cli_rows_exact=432,latest_notebook_code_cells=3,
        relocated_browser=browser,report_pages=26,production_model_changed=False,
        new_independent_assessment=False,protected_outcomes_read=False,competition_submitted=False))
    manifest(OUT,'model');verify_directory(OUT);print('VERIFIED v13',flush=True)


def package():
    checks();preserved();verify_directory(OUT)
    assert read(OUT/'validation/v13_delivery.json')['status']=='v13_delivery_verified'
    assert read(OUT/'validation/v13_relocated_browser/visual_review.json')['status']=='passed'
    if CHANNELS.exists():raise FileExistsError('Preserve completed archives')
    CHANNELS.mkdir();documents=CHANNELS/'icy_road_documents';documents.mkdir()
    old_documents=P/'submission_channels_20261101_v12/icy_road_documents'
    for name in read(old_documents/'manifest.json')['files']:
        if name not in {'README.md','AI_USAGE.md'}:copy(old_documents/name,documents/name)
    copy(REPORT/'analysis_report_v13.pdf',documents/'reports/analysis_report_v13.pdf')
    copy(ROOT/'docs/images/wind_network_projection_20261102.png',documents/'figures/wind_network_projection.png')
    copy(P/'wind_network_projection_review_20261102_v2/route_wind_comparison.csv',documents/'data/route_wind_comparison.csv')
    copy(ROOT/'docs/delivery/SUBMISSION_READINESS_20261106.md',documents/'SUBMISSION_READINESS.md')
    (documents/'README.md').write_text('''# 문서자료 · v13

[26쪽 현재 분석 보고서](reports/analysis_report_v13.pdf)는 기존 24쪽에 채택된 풍속의 843구간 적용·제출 검토 2쪽을 보충합니다. [새 풍속 지도](figures/wind_network_projection.png)·[노선별 비교 CSV](data/route_wind_comparison.csv)·[조건 기준표](RISK_CRITERIA.md)를 함께 제공합니다. 기존 v12 보고서·관측망 비교 그림·지표 CSV는 당시 근거로 보존합니다.

실행 코드·학습 자료·모델·환경·노트북·CSV·GIS·현재 오프라인 탐색은 별도 모델자료 ZIP에 있습니다. 새 풍속은 기존 69특성 모형의 구간 적용이며 새 독립 평가가 아닙니다. 결빙 v2 F1 0.026554는 기온 기준선 0.036601보다 낮습니다. 조건 노출은 사고확률이나 공식 현장 위험등급이 아닙니다.

[제출 준비 상태](SUBMISSION_READINESS.md)를 확인합니다. 결과물 마감 날짜·시각·용량 제한·계정 승인·참가자의 직접 최종 판단은 별도 확인이 필요합니다. 로컬 후보 준비이며 실제 대회 접수 완료를 뜻하지 않습니다.
''','utf8')
    (documents/'AI_USAGE.md').write_text('''# AI 지원과 참가자 검토

Codex가 프로젝트 현황·이전 검산 근거를 확인하고, 채택된 풍속의 843구간 결과·CSV·GIS·오프라인 탐색·26쪽 보고서를 통합했습니다. 기존 v12 파일·모형·예제 예측·보호 봉인은 대조해 보존합니다. 실제 CLI·Jupyter 노트북·브라우저·ZIP 파일 해시 검증의 결과는 모델자료에 있습니다.

사용자는 마감이 가까운 대회 프로젝트의 현황 파악과 후속 작업을 지시했습니다. AI의 검산을 참가자의 직접 검토로 기록하지 않습니다. 참가자 최종 선택·직접 확인 내역은 실제 수행 후 추가해야 합니다. 결빙 기준선 미달과 미채택 실험을 유지하며, 공식 성적·현장 위험등급을 새로 검증한 것으로 표현하지 않습니다. 대회 업로드·문의 발송·공개 전환·Git 커밋·푸시는 수행하지 않았습니다. 전체 AI 지원 기록은 모델자료의 AI_USAGE.md에 있습니다.
''','utf8')
    manifest(documents,'documents')
    secrets=[]
    for line in (ROOT/'secret.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            value=line.split('=',1)[1].strip().strip('\"\x27')
            if len(value)>=12:secrets.append(value.encode())
    for folder in [OUT,documents]:
        records=read(folder/'manifest.json')['files']
        errors=inspect_documents(folder,[n for n in records if n.endswith('.md')]);assert not errors,'\n'.join(errors)
        for name in records:
            path=folder/name
            assert path.suffix.lower() not in {'.env','.pem','.key','.hwp'} and '/.git/' not in '/'+name
            if path.suffix in {'.py','.json','.md','.txt','.ipynb','.html','.js','.log','.yml','.csv'}:
                data=path.read_bytes();assert not any(value in data for value in secrets),name
                assert not re.search(rb'(?:github_pat_[A-Za-z0-9_]{40,}|RGAPI-[A-Za-z0-9-]{30,}|sk-[A-Za-z0-9_-]{30,})',data),name
    results={channel:archive(folder,CHANNELS/f'icy_road_{channel}.zip','icy_road_'+channel)
        for channel,folder in [('documents',documents),('model',OUT)]}
    verify_directory(OLD)
    write(CHANNELS/'submission_receipt.json',dict(status='two_channel_archives_verified',at_utc=now(),archives=results,
        model_source=OUT.relative_to(ROOT).as_posix(),preserved_v12_files=len(preserved()),
        execution=read(OUT/'validation/v13_delivery.json'),competition_submitted=False,
        result_submission_deadline=None,remaining=['마감 날짜·시각·용량 제한','계정 승인·접수 상태','참가자 최종 검토']))
    print(json.dumps(results,ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',required=True,choices=['prepare','verify','package'])
    globals()[p.parse_args().stage]()
