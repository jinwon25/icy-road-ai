"""추가 검증·명시적 결빙 후보·기상 탐색을 v10 보존 위에 통합하고 두 ZIP을 검증한다."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import nbformat as nb
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,now,verify_preserved
from scripts.review_submission_bundle import verify_directory
from scripts.package_review_v8 import copy,archive
from scripts.check_markdown import inspect_documents
from src.data_source import sha256_file as sha

P=ROOT/'outputs/private';OLD=P/'submission_candidate_20261101_v10';OUT=P/'submission_candidate_20261101_v11'
CHANNELS=P/'submission_channels_20261101_v11';REPORT=P/'report_update_20261101_v11_final'
UPDATED={'README.md','README_repository.md','AI_USAGE.md','docs/STATUS.md','docs/README.md','docs/START_HERE.md',
    'docs/delivery/REVIEWER_GUIDE.md','scripts/README.md','config/README.md'}
STUDIES=['weather_thermodynamics_20261101_v1','weather_catboost_20261101_v1','frost_icing_20261101_v1',
    'competition_profile_review_20261101_v1','weather_explorer_20261101_v2','weather_explorer_validation_20261101_v4',
    'followup_review_20261101_v1','thermodynamic_references_20261101_v1']

README='''# 미관측 고속도로 기상·노면온도 추정과 결빙 조건 · v11

관측이 없는 도로의 기상·노면온도를 추정하고, 검증의 한계와 실행 목적을 명시한 비공개 검토 묶음입니다. 최신 물리 입력·다른 나무 구조의 36적합은 교체 조건을 통과하지 못해 현재 모형을 유지했습니다. 명시적 F1 후보와 두 겨울 구간 기상 탐색을 추가했습니다. 실제 대회 업로드 완료본이 아닙니다.

## 먼저 확인할 결과

| 대상 | 결과 | 범위 |
| --- | --- | --- |
| 노면온도 | MAE 1.145698°C·기존 대비13.66% 감소 | 기존 v3, 개발9곳·두 겨울310,091유효쌍 |
| 기온·습도·풍속 | AWS 대비 MAE22.10·12.91·42.67% 감소 | 기상정답4곳 지역제외, 현재 모형 유지 |
| 결빙 기존 v2 | 일별지점F1 0.026554 | 기존온도·수분 판정 |
| F1 우선 검토 후보 | 알려진 기온0°C 기준선 F1 0.036601 | 정밀도·둘째 겨울 F1 악화도 함께 보고 |
| 구간 기상 탐색 | 843구간·240일·두 겨울·품질필터·CSV | 관측정확도·결빙확률·공식위험등급 아님 |

F1 후보는 새로 학습해 얻은 독립 개선이 아닙니다. 통합점수만 보면 더 높지만 희소양성과 특정지점 집중·겨울편차가 큽니다. 보호 정답을 열지 않았고 수상순위·현장안전성을 보장하지 않습니다. 조건과 손해를 확인한 뒤 용도에 맞는 프로필로 실행합니다.

1. [22쪽 보고서](reports/analysis_report_v11.pdf), [현재 구성·근거](docs/delivery/REVIEW_BUNDLE_V11_20261101.md).
2. [F1 우선·기존 v2 프로필](docs/delivery/COMPETITION_PROFILES_20261101.md), [추가 실험·레퍼런스](docs/research/FOLLOWUP_METHODS_20261101.md).
3. [오프라인 기상 탐색](research/latest/weather_explorer_20261101_v2/index.html): 현재 Chrome·Edge에서 파일을 엽니다. 외부 요청·Python·인증이 필요하지 않습니다.
4. [기본 온도·결빙 검토](notebooks/submission_review_v11.ipynb), [추가 지표·GUI·F1 CLI 검토](notebooks/followup_review_v11.ipynb).
5. [현재 습도 학습·추론](research/weather_history_supplement/README.md), [조건 기준표](docs/delivery/RISK_CRITERIA_20261031.md), [AI 지원 기록](AI_USAGE.md).

## 설치와 기존 모델 검사

Windows·Python3.11·CPU에서 검증했습니다. NumPy2.2.6·pandas2.2.3·scikit-learn1.6.1·SciPy1.15.3·PyArrow20.0.0·joblib1.5.1입니다. `requirements-notebook.txt`와 별도 기상 폴더의 고정 환경 파일을 사용합니다. 최종 실행·재학습에 GPU·외부 AI 예측 API·인증정보가 필요하지 않습니다. CatBoost는 미채택 연구용이며 기본 추론에 필요하지 않습니다.

```powershell
python -m pip install -r requirements-notebook.txt
$env:OMP_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
python scripts/review_submission_bundle.py --smoke --output local_review/my_review.json
python scripts/check_notebook.py notebooks/followup_review_v11.ipynb
python code/train.py --output local_review/my_refit
```

첫 검사는 전체 파일 해시·기존 예측144행·기본 5코드 셀을 확인합니다. 후속 4코드 셀은 포함 지표·감사·GUI와 F1 우선 CLI를 확인합니다. 원래 출력이 있으면 새 이름을 사용합니다. 위 학습은 포함된 허용23곳의 기존 노면온도 모형을 재학습합니다.

## 결빙 프로필을 명시해 실행

```powershell
python scripts/predict_competition_profile.py --bundle . --input data/weather_example.csv --output local_review/score_priority.csv --icing-profile score_priority_asos_zero --output-start 2024-12-15 --output-end 2024-12-16
python scripts/predict_competition_profile.py --bundle . --input data/weather_example.csv --output local_review/preserved_v2.csv --icing-profile preserved_v2 --output-start 2024-12-15 --output-end 2024-12-16
```

온도 v3와 기존 v2판정 열을 보존하고 선택한 정책·실제 기준온도를 명시합니다. 기본 `code/predict.py`는 기존 v2입니다. 별도 F1 후보103,680행은 `research/latest/competition_profile_review_20261101_v1/protected_score_priority_predictions.csv.gz`이며 기존 `exports/protected_predictions_10min.csv`와 구별합니다. 보호 18NA와 온도·행키를 정확히 보존했습니다. 공식 고정 CSV 양식이나 보호성적을 새로 확인한 결과는 아닙니다.

## 현재 습도 전체 재학습·추론

```powershell
cd research/weather_history_supplement
python -m pip install -r requirements.txt
python scripts/predict_weather_history.py --input data/weather_context_example.csv --output my_weather.csv --output-start 2024-12-15 --output-end 2024-12-16
python scripts/retrain_weather_history.py --bundle . --output my_humidity_refit
```

출력일 앞24시간 기상을 함께 넣고 추론 후 날짜를 선택합니다. 예제864행에서 선택일432행을 출력하며 전체447,794유효행 습도 재학습을 별도 위치에서 검증했습니다. 예제는 재현검사로 독립성능평가가 아닙니다. 기존기온·풍속과 비교용습도 전체재학습은 `research/weather_observation_supplement/`에 보존합니다.

## 탐색과 포함 근거

HTML에서 기온·상대습도·풍속·습도범위이탈·과거이력부족을 선택하고 두 겨울을 같은 색범위로 비교합니다. 구간의240일시계열·CSV다운로드와 전체CSV·GIS가 연결됩니다. ASOS172출처50구간과 입력 품질을 정확도·확률로 해석하지 않습니다. 126필터·163만수치·실제다운로드·모바일·외부요청0을 검증했습니다.

`research/latest/`에는 새36적합·서리 반증의 집계·감사, 명시적프로필·보호후보·탐색·80+14행CSV가 있습니다. 새 미채택 모형 전체·184MB특성캐시·전체2,913만구간10분캐시는 원 작업공간에 보존합니다. 원자료재수집·모든과거연구 재실행에는 원 비공개 작업공간이 필요합니다. 최종 모형 재학습·기본추론·F1프로필·탐색의 실행은 포함자료로 가능합니다.

현재 진입점은 이 README와 최상위manifest입니다. 과거README·버전별문서는 당시이력입니다. v10의 모델·예측·데모·검산은 보존했습니다. 11월6일은 사용자제공 작업마감기준으로 공식상세확인과 구별합니다. AI의 검토를 참가자의 수동확인으로 기재하지 않습니다.
'''


def source_checks():
    frozen=verify_preserved();verify_directory(OLD)
    build=read(REPORT/'build_receipt.json');visual=read(REPORT/'visual_review.json')
    assert visual['status']=='passed' and visual['pages']==22 and visual['pdf_sha256']==build['pdf_sha256']==sha(REPORT/'analysis_report_v11.pdf')
    for name,digest in build['sources'].items():assert sha(ROOT/name)==digest,name
    for name in STUDIES[:3]:
        audit=read(P/name/'independent_verification.json');assert audit['status']=='passed' and audit['summary_sha256']==sha(P/name/'summary.json')
    assert read(P/STUDIES[3]/'summary.json')['status']=='explicit_competition_profiles_verified'
    gui=read(P/STUDIES[5]/'summary.json');v=read(P/STUDIES[5]/'visual_review.json')
    assert gui['status']=='passed' and v['status']=='passed' and gui['html_sha256']==v['html_sha256']==sha(P/STUDIES[4]/'index.html')
    return frozen


def preserved():
    names=[]
    for name,record in read(OLD/'manifest.json')['files'].items():
        if name in UPDATED:continue
        assert sha(OUT/name)==record['sha256'],name;names.append(name)
    return names


def manifest(folder,channel):
    path=folder/'manifest.json'
    if path.exists():
        i=1
        while (folder/f'provenance/v11_previous_manifest_{i:02d}.json').exists():i+=1
        copy(path,folder/f'provenance/v11_previous_manifest_{i:02d}.json')
        # manifest 자체만 새 값으로 갱신한다. 원본은 바로 위 provenance에 보존했다.
    files={p.relative_to(folder).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in folder.rglob('*')
        if p.is_file() and p!=path and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.relative_to(folder).parts[0]!='local_review'}
    value=dict(package_label='v11',channel=channel,status='private_review_candidate',at_utc=now(),files=files,
        current_report='reports/analysis_report_v11.pdf',competition_submitted=False)
    if channel=='model':value.update(current_notebook='notebooks/submission_review_v11.ipynb',followup_notebook='notebooks/followup_review_v11.ipynb',
        production_model_version='v3',icing_version='v2',production_model_changed=False,humidity_model_changed=False,
        explicit_score_priority_profile='score_priority_asos_zero',preserved_default_icing_profile='preserved_v2',
        score_priority_predictions='research/latest/competition_profile_review_20261101_v1/protected_score_priority_predictions.csv.gz',
        weather_explorer='research/latest/weather_explorer_20261101_v2/index.html',weather_supplement='research/weather_history_supplement')
    if path.exists():path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    else:write(path,value)


def prepare():
    if OUT.exists():raise FileExistsError('Preserve candidate')
    frozen=source_checks()
    for name in read(OLD/'manifest.json')['files']:copy(OLD/name,OUT/name)
    copy(OLD/'manifest.json',OUT/'provenance/v10_manifest.json');copy(OLD/'README.md',OUT/'README_v10.md')
    command=['git','-c','safe.directory='+ROOT.as_posix(),'ls-files','--cached','--others','--exclude-standard','-z'];sources={}
    for name in sorted(set(filter(None,subprocess.check_output(command,cwd=ROOT).decode('utf8').split('\0')))):
        if not name.startswith(('src/','scripts/','tests/','config/','docs/','notebooks/')):continue
        path=ROOT/name;dest=OUT/name
        if not path.is_file() or path.suffix not in ['.py','.md','.json','.ipynb','.png','.jpg','.html','.txt','.yml','.yaml']:continue
        if dest.exists() and name not in UPDATED:continue
        copy(path,dest);sources[name]=sha(path)
    copy(ROOT/'AI_USAGE.md',OUT/'AI_USAGE.md');copy(ROOT/'README.md',OUT/'README_repository.md')
    for name in STUDIES:
        for path in (P/name).iterdir():
            if path.is_file() and (path.name=='LICENSE' or path.suffix in ['.json','.csv','.gz','.png','.html','.txt','.py','.xml','.log']):
                copy(path,OUT/'research/latest'/name/path.name)
    for name in ['analysis_report_v11.pdf']:copy(REPORT/name,OUT/'reports'/name)
    copy(REPORT/'build_receipt.json',OUT/'validation/v11_report_build.json');copy(REPORT/'visual_review.json',OUT/'validation/v11_report_visual.json')
    oldnb=nb.read(OLD/'notebooks/submission_review_v10.ipynb',as_version=4);code=[c for c in oldnb.cells if c.cell_type=='code']
    for cell in oldnb.cells:
        if cell.cell_type=='markdown':cell.source=cell.source.replace(' · v10',' · v11').replace('analysis_report_v10.pdf','analysis_report_v11.pdf')
    oldnb.cells.append(nb.v4.new_markdown_cell('''## 추가 검토와 실행 목적

`followup_review_v11.ipynb`에서 추가36적합의 미채택·두 겨울기상탐색·명시적 F1 후보의 실제CLI를 확인합니다.
기존 온도·결빙5코드셀은 보존했습니다. F1 후보의 정밀도·둘째 겨울 손해를 함께 검토합니다.'''))
    assert code==[c for c in oldnb.cells if c.cell_type=='code'];nb.write(oldnb,OUT/'notebooks/submission_review_v11.ipynb')
    copy(ROOT/'notebooks/followup_review_20261101.ipynb',OUT/'notebooks/followup_review_v11.ipynb')
    (OUT/'README.md').write_text(README,encoding='utf8')
    names=preserved()
    write(OUT/'provenance/v11_preparation.json',dict(at_utc=now(),source_files=sources,preserved_v10_files=names,preservation=frozen,
        production_model_changed=False,explicit_competition_profile_added=True,weather_explorer_added=True,
        new_unadopted_model_caches_included=False,full_segment_weather_point_caches_included=False))
    manifest(OUT,'model');verify_directory(OUT);print('V11 PREPARED',len(names),'v10 files preserved',flush=True)


def verify():
    source_checks();names=preserved();verify_directory(OUT)
    if (OUT/'validation/v11_delivery.json').exists():raise FileExistsError('Preserve verification')
    local=OUT/'local_review';local.mkdir(exist_ok=True);index=1
    while any(local.glob(f'v11_{index:02d}*')):index+=1
    prefix=f'v11_{index:02d}';env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
    commands=[('core',[sys.executable,'scripts/review_submission_bundle.py','--smoke','--output',f'local_review/{prefix}.json']),
        ('followup',[sys.executable,'scripts/check_notebook.py','notebooks/followup_review_v11.ipynb']),
        ('score_priority',[sys.executable,'scripts/predict_competition_profile.py','--bundle','.',
            '--input','data/weather_example.csv','--output',f'local_review/{prefix}_score.csv','--icing-profile','score_priority_asos_zero',
            '--output-start','2024-12-15','--output-end','2024-12-16'])]
    for name,command in commands:
        run=subprocess.run(command,cwd=OUT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
        log=local/(prefix+'_'+name+'.driver.log');log.write_bytes(run.stdout);assert run.returncode==0,str(log);print('PASSED',name,flush=True)
    dtype={'station':str,'predicted_ice':'Int64','preserved_v2_predicted_ice':'Int64'}
    a=pd.read_csv(local/(prefix+'_score.csv'),dtype=dtype,parse_dates=['time'],float_precision='round_trip')
    b=pd.read_csv(OUT/'research/latest/competition_profile_review_20261101_v1/score_priority_asos_zero_example.csv',dtype=dtype,parse_dates=['time'],float_precision='round_trip')
    pd.testing.assert_frame_equal(a,b,check_exact=True);assert len(a)==144
    # 실제로 복사된 HTML에서 상대 경로·다운로드까지 다시 검사한다.
    browser=P/'weather_explorer_bundle_validation_v11';assert not browser.exists()
    gui_env=env.copy();gui_env.update(PYTHONPATH=str(P/'browser_runtime_20261024'),PLAYWRIGHT_NODEJS_PATH='C:/Program Files/nodejs/node.exe')
    run=subprocess.run([sys.executable,str(ROOT/'scripts/audit_weather_explorer_20261101.py'),'--viewer',str(OUT/'research/latest/weather_explorer_20261101_v2'),
        '--output',str(browser)],cwd=ROOT,env=gui_env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
    (local/(prefix+'_browser.driver.log')).write_bytes(run.stdout);assert run.returncode==0,'Relocated browser check failed'
    assert read(browser/'summary.json')['status']=='passed'
    for path in browser.iterdir():
        if path.is_file():copy(path,OUT/'validation/v11_browser'/path.name)
    for path in local.glob(prefix+'*'):copy(path,OUT/'validation/v11_execution'/path.name)
    errors=inspect_documents(OUT,[p.relative_to(OUT).as_posix() for p in OUT.rglob('*.md')]);assert not errors,'\n'.join(errors)
    source_checks();preserved();execution=read(local/(prefix+'.json'))
    write(OUT/'validation/v11_delivery.json',dict(status='v11_delivery_verified',at_utc=now(),preserved_v10_files=len(names),execution=execution,
        score_priority_rows_identical=len(a),basic_notebook_code_cells=5,followup_notebook_code_cells=4,
        relocated_browser=read(browser/'summary.json'),production_model_changed=False,competition_submitted=False))
    manifest(OUT,'model');verify_directory(OUT);print('V11 VERIFIED',flush=True)


def package():
    source_checks();preserved();verify_directory(OUT)
    assert read(OUT/'validation/v11_delivery.json')['status']=='v11_delivery_verified'
    if CHANNELS.exists():raise FileExistsError('Preserve archives')
    CHANNELS.mkdir();documents=CHANNELS/'icy_road_documents';documents.mkdir()
    copy(REPORT/'analysis_report_v11.pdf',documents/'reports/analysis_report_v11.pdf')
    for src,dest in [('weather_adopted_20261101.png','weather_accuracy.png'),('weather_projection_20261101.png','weather_maps.png'),
        ('weather_followup_20261101.png','additional_comparison.png'),('competition_profiles_20261101.png','icing_profiles.png'),
        ('weather_explorer_20261101.png','weather_explorer.png'),('inventory_comparison_20261031_v3.png','official_inventory_comparison.png')]:
        copy(ROOT/'docs/images'/src,documents/'figures'/dest)
    copy(ROOT/'docs/delivery/RISK_CRITERIA_20261031.md',documents/'RISK_CRITERIA.md')
    copy(OUT/'data/condition_evidence_criteria.csv',documents/'data/condition_evidence_criteria.csv')
    for name in ['weather_comparison_metrics.csv','icing_profile_metrics.csv']:copy(P/'followup_review_20261101_v1'/name,documents/'data'/name)
    (documents/'README.md').write_text('''# 문서자료 · 기상·노면온도 추정과 결빙 선택 목적

[22쪽 통합 보고서](reports/analysis_report_v11.pdf)에 자료·개발·공간 검증·효과·한계·실행을 통합했습니다.
[기상 오차](figures/weather_accuracy.png), [두 겨울 기상 지도](figures/weather_maps.png), [추가 비교](figures/additional_comparison.png),
[F1 선택의 이득과 손해](figures/icing_profiles.png), [실제 기상 탐색](figures/weather_explorer.png),
[공식 목록 비교](figures/official_inventory_comparison.png), [조건 기준표](RISK_CRITERIA.md)를 제공합니다.

현재 노면온도 MAE는1.145698°C, 기상 세 목표의 AWS대비MAE감소는22.10·12.91·42.67%입니다. 추가36적합은 현재 모형 교체조건을 넘지 못해 유지했습니다. 알려진 ASOS0°C는 F1우선 실행후보로 별도 제공하며 기존 v2의.026554보다 높은.036601이지만 정밀도·둘째 겨울은 낮습니다. 새로운 독립 개선이나 공식 성적이 아닙니다.

실행 코드·최종 모형·학습 자료·고정 환경·노트북·보호 예측 비교·오프라인 HTML·CSV·GIS·검산 기록은 모델자료 ZIP에 있습니다. AI 지원·실패·기여 구분은 보고서와 모델자료의 AI_USAGE.md를 따릅니다. 실제 대회 업로드·공개는 수행하지 않았습니다.
''',encoding='utf8')
    (documents/'AI_USAGE.md').write_text('''# AI 지원·검토 요약

Codex가 공식 안내·논문·공개 구현 검토, 추가36적합·서리 반증·독립 검산, 명시적F1실행후보, 구간 기상 탐색·22쪽 보고서·재현 묶음을 지원했습니다. 사용자는1등목표·작업범위·지속진행과 예상마감을 제공했습니다.

실패한 새모형을 채택하거나기준을사후완화하지 않았습니다. 알려진기온기준선의실행프로필은학습성능향상과구별하고정밀도·둘째 겨울의손해를명시했습니다. 보호 정답은읽지않았고원모형·온도·행키·18NA·v10은보존했습니다.

실제CLI·Jupyter·전체 파일해시·163만GUI수치·126필터·모바일을검증했습니다. AI의 실행·시각검토를 참가자의 수동 확인으로 기재하지 않습니다. 참가자의 직접 검토·최종 판단은 실제 수행 후 기록해야 합니다. 전체 지원·실패·선택 근거는 모델자료의 AI_USAGE.md를 따릅니다. 외부 발송·업로드·푸시는 하지 않았습니다.
''',encoding='utf8')
    manifest(documents,'documents');secret_values=[];secret=ROOT/'secret.env'
    if secret.exists():
        for line in secret.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                value=line.split('=',1)[1].strip().strip('\"\x27')
                if len(value)>=12:secret_values.append(value.encode())
    for folder in [OUT,documents]:
        names=read(folder/'manifest.json')['files'];errors=inspect_documents(folder,[n for n in names if n.endswith('.md')]);assert not errors,'\n'.join(errors)
        for name in names:
            path=folder/name;assert path.suffix not in ['.env','.key','.pem','.hwp'] and '/.git/' not in '/'+name
            if path.suffix in ['.py','.md','.json','.txt','.html','.js','.yml','.log','.csv','.ipynb']:
                content=path.read_bytes();assert not any(v in content for v in secret_values),name
                assert not re.search(rb'(?:github_pat_[A-Za-z0-9_]{40,}|RGAPI-[A-Za-z0-9-]{30,}|sk-[A-Za-z0-9_-]{30,})',content),name
    archives={'documents':archive(documents,CHANNELS/'icy_road_documents.zip','icy_road_documents'),
        'model':archive(OUT,CHANNELS/'icy_road_model.zip','icy_road_model')}
    source_checks();write(CHANNELS/'submission_receipt.json',dict(status='two_channel_archives_verified',at_utc=now(),archives=archives,
        model_source=OUT.relative_to(ROOT).as_posix(),preserved_v10_files=len(preserved()),execution=read(OUT/'validation/v11_delivery.json'),
        production_model_changed=False,explicit_score_priority_profile_added=True,weather_explorer_added=True,competition_submitted=False))
    print(json.dumps(archives,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',required=True,choices=['prepare','verify','package'])
    globals()[parser.parse_args().stage]()
