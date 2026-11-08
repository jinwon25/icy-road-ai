"""기존 v9를 보존하고 안정화 습도·보고서·지도의 v10 실행과 두 ZIP을 검증한다."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import nbformat as nb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_objective_icing import read, write, now, verify_preserved
from scripts.review_submission_bundle import verify_directory
from scripts.package_review_v8 import copy, archive
from scripts.check_markdown import inspect_documents
from src.data_source import sha256_file as sha

P = ROOT / 'outputs/private'
OLD = P / 'submission_candidate_20261031_v9'
OUT = P / 'submission_candidate_20261101_v10'
CHANNELS = P / 'submission_channels_20261101_v10'
REPORT = P / 'report_update_20261101_v10_final'
SUPPLEMENT = P / 'weather_history_supplement_20261101_v2'
UPDATED = {'README.md', 'README_repository.md', 'AI_USAGE.md', 'docs/STATUS.md', 'docs/README.md',
           'docs/START_HERE.md', 'docs/delivery/REVIEWER_GUIDE.md', 'scripts/README.md', 'config/README.md'}
STUDIES = ['weather_humidity_stable_20261101_v1', 'weather_history_review_20261101_v2',
           'weather_history_segment_projection_20261101_v1', 'weather_history_projection_review_20261101_v1']

MODEL_README = '''# 미관측 고속도로 기상·노면온도 추정과 결빙 조건 · v10

기상 이력으로 센서 없는 도로의 기상·노면온도를 추정하고 공간 검증과 결빙 한계를 함께 제공합니다. 이번 묶음은 습도 모형·문맥에 무관한 계산·겨울 전이 검증·기상 지도를 갱신했습니다. 노면온도 v3·결빙 v2·기온·풍속·보호 평가는 보존했습니다. 비공개 로컬 검토본이며 실제 대회 접수 완료본이 아닙니다.

## 결과와 읽는 순서

1. [19쪽 통합 보고서](reports/analysis_report_v10.pdf), [검토 안내](docs/delivery/REVIEW_BUNDLE_V10_20261101.md).
2. [최종 습도 학습·추론](research/weather_history_supplement/README.md), [설계·반례·검산](docs/research/WEATHER_SPACE_TIME_20261101.md).
3. [기본 온도·결빙 노트북](notebooks/submission_review_v10.ipynb), [새 습도·기상 지도 검토](notebooks/weather_review_v10.ipynb).
4. [공식 목록 탐색](research/latest/official_inventory_viewer_20261031_v1/index.html), [갱신된 기상 지도](research/latest/weather_history_projection_review_20261101_v1/weather_projection_two_winters.png).
5. [조건 기준표](docs/delivery/RISK_CRITERIA_20261031.md), [CSV 규약](docs/delivery/CSV_CONTRACT.md), [AI 지원 기록](AI_USAGE.md).

| 대상 | 현재 결과 | 범위 |
| --- | --- | --- |
| 노면온도 | MAE 1.145698°C, 13.66% 감소 | 기존 v3, 개발 9곳·두 겨울·310,091유효쌍 |
| 기온 | MAE 1.323764°C, AWS 대비 22.10% 감소 | 기상 정답 개발 4곳·지역 제외 |
| 상대습도 | MAE 5.686973%p, AWS 대비 12.91% 감소 | 기존 모형 대비 추가 3.22%, 서천 1.15% 악화 |
| 습도 지역·겨울 제외 | MAE 6.008156→5.834129%p, 2.90% 감소 | 역방향은 사후 재현, 반복 개발 자료 |
| 1분 풍속 | MAE 0.563455m/s, 42.67% 감소 | 기존 모형, 국지 변동의 한계 |
| 결빙 | F1 0.026554 < 기온 기준선 0.036601 | 기상 개선을 결빙 개선으로 해석하지 않음 |

새 습도는 양 겨울·저온 구간·지역 악화 제한·날짜 블록 기준을 통과했습니다. 서상 편향과 반복 개발 선택의 한계는 남습니다. 같은 24시간 문맥 앞에 더 오래된 입력을 넣으면 결과가 달라지던 초기 구현은 독립 창 합산으로 바로잡고 12개 제외 모형을 다시 학습했습니다. 실제 CLI·전체 재학습 432행은 정확히 일치했습니다. 공식 순위·새 독립 성능을 입증한 결과는 아닙니다.

## 실행

Windows·Python 3.11·CPU에서 검증했습니다. NumPy 2.2.6, pandas 2.2.3, scikit-learn 1.6.1, SciPy 1.15.3, PyArrow 20.0.0, joblib 1.5.1을 사용합니다. 고정 환경 파일을 포함합니다. 최초 설치 후 기본 추론·최종 모형 재학습에 GPU·외부 AI 서비스·인증정보가 필요하지 않습니다.

압축을 푼 `icy_road_model` 폴더에서 실행합니다. 출력이 이미 있으면 새 이름을 사용합니다.

```powershell
python -m pip install -r requirements-notebook.txt
$env:OMP_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
python scripts/review_submission_bundle.py --smoke --output local_review/my_review.json
python scripts/check_notebook.py notebooks/weather_review_v10.ipynb
python -X utf8 code/train.py --output local_review/my_refit
```

첫 검사는 전체 해시·기존 예측 144행 일치·기본 5코드 셀 실행입니다. 기본 노트북은 재학습을 생략합니다. 위 학습 명령은 포함된 허용 23곳 자료의 기존 노면온도 모형을 재학습합니다.

```powershell
cd research/weather_history_supplement
python -m pip install -r requirements.txt
python scripts/predict_weather_history.py --input data/weather_context_example.csv --output my_weather.csv --output-start 2024-12-15 --output-end 2024-12-16
python scripts/retrain_weather_history.py --bundle . --output my_humidity_refit
```

출력일 앞의 최소 24시간 기상을 함께 넣습니다. 48시간 예제 입력 864행에서 선택일 432행을 출력합니다. 입력을 먼저 출력일로 자르면 이력을 잃습니다. 해당 폴더의 `notebooks/weather_history_supplement.ipynb`에서 `RUN_REFIT=True`로 습도 전체 재학습을 실행합니다. 447,794개 유효 학습 행을 사용하며 별도 위치의 실제 전체 재학습까지 확인했습니다. 예제는 재현 검사로 독립 성능 평가가 아닙니다. 기온·풍속을 포함한 기존 세 모형 재학습은 보존된 `research/weather_observation_supplement/`에서 가능합니다.

## 자료와 검증

| 경로 | 역할 |
| --- | --- |
| data/ · model/ · code/ | 기존 온도·결빙의 자료·모형·학습·추론 |
| research/weather_history_supplement/ | 현재 습도·기존 기온/풍속·허용 학습 자료·24시간 문맥 예제·환경 |
| research/latest/weather_humidity_stable_20261101_v1/ | 최종 두 제외 검증·소스 수정 대조·독립 감사 |
| research/latest/weather_history_review_20261101_v2/ | 최종 습도 64행 지표와 현재 세 목표 지표 |
| research/latest/weather_history_segment_projection_20261101_v1/ | 일별 202,320행·겨울별 1,686행·GIS·검산 |
| validation/v10_delivery.json | 이 폴더의 실제 기본·기상 CLI·세 노트북 검사 |
| validation/weather_history_full_refit.json | 별도 위치 습도 전체 재학습의 정확한 일치 |
| exports/ · figures/ · demo/ | 기존 도로 결과·지도·오프라인 탐색·실제 화면 영상 |
| provenance/ · licenses/ · docs/ | 보존 이력·이용조건·실험 설명·AI 지원 |

843구간·두 겨울 29,134,080개 10분 캐시는 원 비공개 작업 공간에 보존합니다. ZIP에는 일별·겨울별 집계와 GIS를 포함합니다. 전체 원천 재수집과 모든 과거 연구 재실행에는 원 작업 공간이 필요하지만 최종 습도와 기존 최종 모형의 전체 재학습·예제 추론은 포함 자료로 가능합니다.

`humidity_history_status`는 과거 입력 충실도, `humidity_history_outside_training_range`는 학습 최솟값·최댓값 이탈입니다. 오차·신뢰도·결빙확률이 아닙니다. ASOS 172 출처 50구간도 학습에 없던 출처로 표시합니다. 기존 노면온도·조건 노출·공식 목록 비교는 유지했습니다. 방향별 구간 수를 독립 관측 수로 늘려 해석하지 않습니다.

현재 진입점은 이 README와 최상위 manifest입니다. 과거 README·날짜별 문서·v9 기상 결과는 당시 이력입니다. 11월 6일은 사용자 제공 작업 마감 기준이며 공식 상세 확인 범위는 `docs/competition/OFFICIAL_UPDATE_20261101.md`를 따릅니다. 자료·모형은 허용된 비공개 심사 범위에서 사용하며 AI 검산과 참가자 직접 판단을 구별합니다.
'''


def source_checks():
    frozen = verify_preserved()
    verify_directory(OLD)
    build = read(REPORT / 'build_receipt.json')
    visual = read(REPORT / 'visual_review.json')
    assert visual['status'] == 'passed' and visual['pages'] == 19
    assert visual['pdf_sha256'] == build['pdf_sha256'] == sha(REPORT / 'analysis_report_v10.pdf')
    for name, digest in build['sources'].items():
        assert sha(ROOT / name) == digest, name
    assert (REPORT / 'analysis_report_v10.md').read_text(encoding='utf8') == (ROOT / 'docs/delivery/ANALYSIS_REPORT_V10_20261101.md').read_text(encoding='utf8')
    receipt = read(SUPPLEMENT / 'receipt.json')
    for name, digest in receipt['files'].items():
        assert sha(SUPPLEMENT / name) == digest, name
    verification = read(P / 'weather_history_supplement_validation_20261101_v2/receipt.json')
    assert verification['status'] == 'weather_history_supplement_verified'
    assert verification['source_receipt_sha256'] == sha(SUPPLEMENT / 'receipt.json')
    for name in [STUDIES[0], STUDIES[2]]:
        audit = read(P / name / 'independent_verification.json')
        assert audit['status'] == 'passed' and audit['summary_sha256'] == sha(P / name / 'summary.json')
    return frozen


def preserved():
    records = read(OLD / 'manifest.json')['files']
    names = []
    for name, record in records.items():
        if name in UPDATED:
            continue
        assert sha(OUT / name) == record['sha256'], name
        names.append(name)
    return names


def manifest(folder, channel):
    path = folder / 'manifest.json'
    if path.exists():
        index = 1
        while (folder / f'provenance/v10_previous_manifest_{index:02d}.json').exists():
            index += 1
        saved = folder / f'provenance/v10_previous_manifest_{index:02d}.json'
        saved.parent.mkdir(exist_ok=True)
        path.rename(saved)
    records = {p.relative_to(folder).as_posix(): dict(bytes=p.stat().st_size, sha256=sha(p))
               for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts
               and p.suffix != '.pyc' and p.relative_to(folder).parts[0] != 'local_review'}
    value = dict(package_label='v10', channel=channel, status='private_review_candidate', at_utc=now(),
                 files=records, current_report='reports/analysis_report_v10.pdf', competition_submitted=False)
    if channel == 'model':
        value.update(current_notebook='notebooks/submission_review_v10.ipynb', production_model_version='v3',
                     icing_version='v2', production_model_changed=False, humidity_model_changed=True,
                     air_temperature_model_changed=False, wind_model_changed=False,
                     weather_supplement='research/weather_history_supplement')
    write(path, value)


def notebooks():
    prior = nb.read(OLD / 'notebooks/submission_review_v9.ipynb', as_version=4)
    original = [c for c in prior.cells if c.cell_type == 'code']
    for cell in prior.cells:
        if cell.cell_type == 'markdown':
            cell.source = cell.source.replace(' · v9', ' · v10').replace('analysis_report_v9.pdf', 'analysis_report_v10.pdf')
    prior.cells.append(nb.v4.new_markdown_cell('''## 현재 습도와 지도

`weather_review_v10.ipynb`에서 최종 습도 지표·새 기상 지도를 확인합니다.
`../research/weather_history_supplement/README.md`는 과거 문맥을 포함한 432행 추론·전체 재학습 진입점입니다.
기존 온도·결빙 5코드 셀은 보존했습니다. 앞선 v9 기상 자료는 당시 이력입니다.'''))
    assert original == [c for c in prior.cells if c.cell_type == 'code']
    nb.write(prior, OUT / 'notebooks/submission_review_v10.ipynb')
    current = nb.v4.new_notebook(metadata=prior.metadata, cells=[nb.v4.new_markdown_cell('''# 최종 습도와 두 겨울의 도로 기상

포함된 집계·감사 해시와 최종 수치를 확인합니다. API·보호 정답·원 연구 특성 캐시가 필요하지 않습니다.
공간 비교 3.22%, 지역과 겨울 동시 제외 2.90%는 반복 개발 결과입니다. 서천 악화와 서상 편향을 함께 읽습니다.'''),
        nb.v4.new_code_cell('''from pathlib import Path
import hashlib, json
import pandas as pd
from IPython.display import display, Image
ROOT=next(p for p in [Path.cwd(),*Path.cwd().parents] if (p/'extended_training_plan.json').exists())
P=ROOT/'research/latest'
read=lambda p: json.loads(p.read_text(encoding='utf8'))
digest=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
for name in ['weather_humidity_stable_20261101_v1','weather_history_segment_projection_20261101_v1']:
    audit=read(P/name/'independent_verification.json')
    assert audit['status']=='passed' and audit['summary_sha256']==digest(P/name/'summary.json')
study=read(P/'weather_humidity_stable_20261101_v1/summary.json')
assert study['primary_success']
for mode, report in study['reports'].items():
    assert all(report['gates'].values())
    print(mode, report['metrics']['instant_residual']['pooled']['mae'], report['metrics']['stable_history']['pooled']['mae'])
metrics=pd.read_csv(P/'weather_history_review_20261101_v2/humidity_validation_metrics.csv')
assert len(metrics)==64
display(metrics)
display(pd.read_csv(P/'weather_history_review_20261101_v2/adopted_weather_metrics.csv'))
display(Image(filename=str(ROOT/'docs/images/weather_humidity_stable_20261101.png')))'''),
        nb.v4.new_markdown_cell('''## 갱신된 습도·이력 품질·지도

기온·풍속·노면온도·기존 조건 노출은 보존했습니다. 이력 충실도와 범위 이탈은 오차나 신뢰구간이 아닙니다.
ASOS 172 출처 50구간은 학습에 없던 출처입니다. 구간 추정 지도가 결빙확률을 의미하지 않습니다.'''),
        nb.v4.new_code_cell('''directory=P/'weather_history_segment_projection_20261101_v1'
summary=read(directory/'summary.json')
for name in ['weather_segments_500m.csv','weather_segment_daily.csv.gz','weather_and_preserved_road_estimates.csv','weather_segments.gpkg']:
    assert digest(directory/name)==summary['files'][name]
segments=pd.read_csv(directory/'weather_segments_500m.csv')
days=pd.read_csv(directory/'weather_segment_daily.csv.gz')
assert len(segments)==1686 and segments.seg_id.nunique()==843 and len(days)==202320
assert not any(summary[k] for k in ['road_temperature_changed','air_temperature_changed','wind_changed','icing_changed'])
display(pd.read_csv(P/'weather_history_projection_review_20261101_v1/route_weather_summary.csv'))
display(segments[['seg_id','winter','new_asos_source_domain','humidity_history_outside_fraction','humidity_history_partial_fraction']].head())
display(Image(filename=str(P/'weather_history_projection_review_20261101_v1/weather_projection_two_winters.png')))
verification=read(ROOT/'validation/weather_history_full_refit.json')
assert verification['status']=='weather_history_supplement_verified' and verification['actual_cli_rows_identical']==432
print('습도 전체 재학습 검증:', verification['complete_refit_targets'])''')])
    nb.validate(current)
    nb.write(current, OUT / 'notebooks/weather_review_v10.ipynb')


def prepare():
    if OUT.exists():
        raise FileExistsError('Preserve previous candidate')
    frozen = source_checks()
    for name in read(OLD / 'manifest.json')['files']:
        copy(OLD / name, OUT / name)
    copy(OLD / 'manifest.json', OUT / 'provenance/v9_manifest.json')
    copy(OLD / 'README.md', OUT / 'README_v9.md')
    command = ['git', '-c', 'safe.directory=' + ROOT.as_posix(), 'ls-files', '--cached', '--others', '--exclude-standard', '-z']
    sources = {}
    for name in sorted(set(filter(None, subprocess.check_output(command, cwd=ROOT).decode('utf8').split('\0')))):
        if not name.startswith(('src/', 'scripts/', 'tests/', 'config/', 'docs/', 'notebooks/')):
            continue
        path, target = ROOT / name, OUT / name
        if not path.is_file() or path.suffix not in ['.py', '.md', '.json', '.ipynb', '.png', '.jpg', '.txt', '.yml', '.yaml']:
            continue
        if target.exists() and name not in UPDATED:
            continue
        copy(path, target)
        sources[name] = sha(path)
    for name in ['AI_USAGE.md', 'README.md']:
        copy(ROOT / name, OUT / ('README_repository.md' if name == 'README.md' else name))
    for path in SUPPLEMENT.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            copy(path, OUT / 'research/weather_history_supplement' / path.relative_to(SUPPLEMENT))
    for name in STUDIES:
        for path in (P / name).iterdir():
            if path.is_file() and path.suffix in ['.json', '.csv', '.gz', '.gpkg', '.png', '.py']:
                copy(path, OUT / 'research/latest' / name / path.name)
    verification = P / 'weather_history_supplement_validation_20261101_v2'
    copy(verification / 'receipt.json', OUT / 'validation/weather_history_full_refit.json')
    for name in ['cli.log', 'notebook_full_refit.log']:
        copy(verification / name, OUT / 'validation/weather_history' / name)
    failed = P / 'weather_history_supplement_20261101_v1'
    for name in ['failure.json', 'factory_before_stable_window_fix.py']:
        copy(failed / name, OUT / 'provenance/humidity_numeric_failure' / name)
    for name in ['factory_before_completion_lookup_fix.py', 'completion_lookup_fix.json']:
        path = SUPPLEMENT / name
        if path.exists():
            copy(path, OUT / 'provenance/humidity_completion_fix' / name)
    copy(REPORT / 'analysis_report_v10.pdf', OUT / 'reports/analysis_report_v10.pdf')
    copy(REPORT / 'build_receipt.json', OUT / 'validation/v10_report_build.json')
    copy(REPORT / 'visual_review.json', OUT / 'validation/v10_report_visual.json')
    quality = P / 'official_review_20261101_v1'
    for name in ['final_tests.xml', 'final_quality.json']:
        if (quality / name).exists():
            copy(quality / name, OUT / 'validation/quality_20261101' / name)
    (OUT / 'README.md').write_text(MODEL_README, encoding='utf8')
    notebooks()
    old = preserved()
    write(OUT / 'provenance/v10_preparation.json', dict(at_utc=now(), source_files=sources, preservation=frozen,
          preserved_v9_files=old, supplement_receipt_sha256=sha(SUPPLEMENT / 'receipt.json'),
          point_ten_minute_caches_included=False, research_feature_caches_included=False,
          production_model_changed=False, humidity_model_changed=True))
    manifest(OUT, 'model')
    verify_directory(OUT)
    print('V10 PREPARED', len(old), 'v9 files preserved', flush=True)


def verify():
    source_checks()
    old = preserved()
    verify_directory(OUT)
    target = OUT / 'validation/v10_delivery.json'
    if target.exists():
        raise FileExistsError('Preserve verification')
    local = OUT / 'local_review'
    local.mkdir(exist_ok=True)
    index = 1
    while any(local.glob(f'v10_{index:02d}*')):
        index += 1
    prefix = f'v10_{index:02d}'
    weather = OUT / 'research/weather_history_supplement'
    env = os.environ.copy()
    env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2', LOKY_MAX_CPU_COUNT='2')
    commands = [
        ('core', OUT, [sys.executable, 'scripts/review_submission_bundle.py', '--smoke', '--output', f'local_review/{prefix}.json']),
        ('weather_review', OUT, [sys.executable, 'scripts/check_notebook.py', 'notebooks/weather_review_v10.ipynb']),
        ('weather_cli', weather, [sys.executable, 'scripts/predict_weather_history.py', '--input', 'data/weather_context_example.csv',
            '--output', str(local / (prefix + '_weather.csv')), '--output-start', '2024-12-15', '--output-end', '2024-12-16']),
        ('weather_notebook', OUT, [sys.executable, 'scripts/check_notebook.py', str(weather / 'notebooks/weather_history_supplement.ipynb')]),
    ]
    for name, cwd, command in commands:
        run = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
        log = local / (prefix + '_' + name + '.driver.log')
        log.write_bytes(run.stdout)
        assert run.returncode == 0, str(log)
        print('PASSED', name, flush=True)
    result = read(local / (prefix + '.json'))
    assert result['prediction_rows_identical'] == 144 and result['notebook'] == 'notebooks/submission_review_v10.ipynb'
    a = pd.read_csv(local / (prefix + '_weather.csv'), float_precision='round_trip')
    b = pd.read_csv(weather / 'data/expected_predictions.csv', float_precision='round_trip')
    pd.testing.assert_frame_equal(a, b, check_exact=True)
    assert len(a) == 432
    for path in local.glob(prefix + '*'):
        copy(path, OUT / 'validation/v10_execution' / path.name)
    errors = inspect_documents(OUT, [p.relative_to(OUT).as_posix() for p in OUT.rglob('*.md')])
    assert not errors, '\n'.join(errors)
    source_checks()
    preserved()
    write(target, dict(status='v10_delivery_verified', at_utc=now(), preserved_v9_files=len(old), execution=result,
          weather_prediction_rows_identical=len(a), current_notebook_code_cells=5, weather_review_code_cells=2,
          weather_supplement_notebook_code_cells=3, weather_full_refit_previously_verified=True,
          production_model_changed=False, humidity_model_changed=True, competition_submitted=False))
    manifest(OUT, 'model')
    verify_directory(OUT)
    print('V10 VERIFIED', flush=True)


def package():
    source_checks()
    preserved()
    verify_directory(OUT)
    assert read(OUT / 'validation/v10_delivery.json')['status'] == 'v10_delivery_verified'
    if CHANNELS.exists():
        raise FileExistsError('Preserve archives')
    CHANNELS.mkdir()
    documents = CHANNELS / 'icy_road_documents'
    documents.mkdir()
    copy(REPORT / 'analysis_report_v10.pdf', documents / 'reports/analysis_report_v10.pdf')
    for source, target in [('weather_adopted_20261101.png', 'weather_accuracy.png'),
        ('weather_humidity_stable_20261101.png', 'humidity_validation.png'),
        ('weather_projection_20261101.png', 'weather_maps.png'),
        ('inventory_comparison_20261031_v3.png', 'official_inventory_comparison.png')]:
        copy(ROOT / 'docs/images' / source, documents / 'figures' / target)
    copy(ROOT / 'docs/delivery/RISK_CRITERIA_20261031.md', documents / 'RISK_CRITERIA.md')
    copy(OUT / 'data/condition_evidence_criteria.csv', documents / 'data/condition_evidence_criteria.csv')
    for name in ['adopted_weather_metrics.csv', 'humidity_validation_metrics.csv']:
        copy(P / 'weather_history_review_20261101_v2' / name, documents / 'data' / name)
    copy(ROOT / 'AI_USAGE.md', documents / 'AI_USAGE.md')
    (documents / 'README.md').write_text('''# 문서자료 · 도로 기상·노면온도 추정과 결빙 조건

[19쪽 통합 보고서](reports/analysis_report_v10.pdf)는 자료·공간 검증·도로 기상·노면온도 개선·결빙 한계·구간 활용·재현을 설명합니다.
[현재 기상 오차](figures/weather_accuracy.png), [습도 두 검증](figures/humidity_validation.png), [두 겨울 지도](figures/weather_maps.png),
[공식 목록 비교](figures/official_inventory_comparison.png), [조건 기준표](RISK_CRITERIA.md)를 함께 제공합니다.

지역 제외에서 기온·습도·풍속 MAE는 AWS 우선보다 22.10·12.91·42.67% 감소했습니다. 습도는 기존 대비 추가 3.22%, 지역·겨울 동시 제외에서도 2.90% 개선했습니다. 서천 1.15% 악화와 서상 편향은 남습니다. 노면온도 MAE 개선은 13.66%입니다. 현재 결빙 F1 0.026554는 기온 기준선 0.036601보다 낮습니다. 반복 개발 결과로 공식 성적이나 1등 달성을 뜻하지 않습니다.

지도는 기상 추정·조건 노출·공식 목록의 비교이며 결빙확률·사고확률·공식 위험등급이 아닙니다. 코드·포함 학습 자료·모형·환경·노트북·데모·GIS와 실제 검증 기록은 별도 모델자료 ZIP에 있습니다. 새 습도는 24시간 과거 문맥을 함께 입력하며 실제 CLI·전체 재학습의 432행 일치를 확인했습니다.

AI 지원·실패·기여 설명은 보고서와 별도 모델자료의 전체 AI_USAGE.md에 있습니다. 이 폴더의 AI_USAGE.md는 요약 안내입니다. 11월 6일은 사용자 제공 작업 마감 기준이며 공식 상세 날짜의 독립 확인과 구별합니다. 단일 최상위 폴더의 비공개 로컬 검토본으로 실제 대회 업로드는 수행하지 않았습니다.
''', encoding='utf8')
    (documents / 'AI_USAGE.md').write_text('''# AI 활용과 참가자 검토

Codex가 현황 점검, 실험·검산 코드, 습도 고도화, 수치 안정성 수정, 지도·보고서·실행 자료 제작을 지원했습니다. 사용자는 목표·작업 범위·공식 안내와 예상 마감일을 제공했습니다. AI의 실행·시각 검토를 참가자의 수동 검토로 기재하지 않습니다.

초기 56비교 뒤 문맥 의존 문제를 찾아 독립 창 합산으로 수정하고 최종 습도 12모형을 다시 학습했습니다. 기존 대비 공간 3.22%·지역과 겨울 동시 제외 2.90% 개선과 서천 악화·서상 편향을 함께 보고했습니다. 기온·풍속·노면온도·결빙 모델은 유지했습니다.

보호 정답·개봉된 4지역 정답을 추가 학습·선택에 사용하지 않았습니다. 실패 자료·수정 전 소스·검산을 보존했습니다. 최종 습도 전체 재학습·CLI 432행, 기존 예측 144행, 노트북과 ZIP 전 파일 해시를 검증합니다. 참가자의 직접 검토·최종 판단은 실제 수행 후 기록해야 합니다. 전체 지원·실패·선택 근거는 모델자료의 AI_USAGE.md를 따릅니다. 외부 업로드·발송·공개는 수행하지 않았습니다.
''', encoding='utf8')
    manifest(documents, 'documents')
    secret_values = []
    secret = ROOT / 'secret.env'
    if secret.exists():
        for line in secret.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                value = line.split('=', 1)[1].strip().strip('\"\x27')
                if len(value) >= 12:
                    secret_values.append(value.encode())
    for folder in [OUT, documents]:
        records = read(folder / 'manifest.json')['files']
        errors = inspect_documents(folder, [n for n in records if n.endswith('.md')])
        assert not errors, '\n'.join(errors)
        for name in records:
            path = folder / name
            assert path.suffix not in ['.env', '.pem', '.key', '.hwp'] and '/.git/' not in '/' + name
            if path.suffix in ['.py', '.json', '.md', '.txt', '.ipynb', '.html', '.js', '.log', '.yml', '.csv']:
                data = path.read_bytes()
                assert not any(value in data for value in secret_values), name
                assert not re.search(rb'(?:github_pat_[A-Za-z0-9_]{40,}|RGAPI-[A-Za-z0-9-]{30,}|sk-[A-Za-z0-9_-]{30,})', data), name
    results = {'documents': archive(documents, CHANNELS / 'icy_road_documents.zip', 'icy_road_documents'),
               'model': archive(OUT, CHANNELS / 'icy_road_model.zip', 'icy_road_model')}
    source_checks()
    write(CHANNELS / 'submission_receipt.json', dict(status='two_channel_archives_verified', at_utc=now(), archives=results,
          model_source=OUT.relative_to(ROOT).as_posix(), preserved_v9_files=len(preserved()),
          execution=read(OUT / 'validation/v10_delivery.json'), competition_submitted=False,
          production_model_changed=False, humidity_model_changed=True))
    print(json.dumps(results, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, choices=['prepare', 'verify', 'package'])
    globals()[parser.parse_args().stage]()
