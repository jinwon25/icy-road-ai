"""보존 ZIP의 누수·지표·필수 파일을 검사하고 자립 실행 노트북을 새 후보에 반영한다."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.submission_archive import restore_archive, verify_archive
from src.submission_io import read_weather
from src.submission_runtime import FEATURES
from src.validation import PROTECTED_STATIONS, assert_training_stations
from src.method_blending import ALLOWED, domain
from src.qa633_metrics import daily_table, aggregate
from scripts.audit_qa633_development import reference
from scripts.audit_temperature_blind_validation import compare
from scripts.evaluate_method_blending import preservation

PRIVATE = ROOT / 'outputs/private'
BASE = PRIVATE / 'submission_candidate_20261016_v1.zip'
OUT = PRIVATE / 'submission_candidate_20261019_v1'
REVIEW = PRIVATE / 'delivery_review_20261019_v1'


def read(path):
    return json.loads(path.read_text('utf-8'))


def write(path, value):
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def prepare():
    expected = read(PRIVATE / 'review_repair_delivery_20261016.json')['archive_sha256']
    manifest = restore_archive(BASE, OUT, expected)
    REVIEW.mkdir(exist_ok=False)
    old = read(OUT / 'notebooks/analysis_review.ipynb')
    source = '\n'.join(''.join(c['source']) for c in old['cells'] if c['cell_type'] == 'code')
    write(REVIEW / 'initial_findings.json', {
        'archive_sha256': expected, 'verified_base_files': len(manifest['files']),
        'old_notebook_references_private_workspace': 'PRIVATE = ROOT / "outputs" / "private"' in source,
        'old_notebook_runs_original_data_smoke_by_default': 'scripts/audit_data.py' in source and 'SMOKE_COMMANDS' in source,
        'private_workspace_present_in_archive': any(n.startswith('outputs/private/') for n in manifest['files']),
        'notebook_runtime_requirements_present': 'nbformat' in (OUT / 'requirements.txt').read_text('utf-8'),
        'remedy': 'Add a package-only submission notebook; retain historical research notebook.'})
    shutil.copy2(ROOT / 'notebooks/submission_review.ipynb', OUT / 'notebooks/submission_review.ipynb')
    shutil.copy2(ROOT / 'requirements-notebook.txt', OUT / 'requirements-notebook.txt')
    print('기존 ZIP 해시 검증·새 후보 복원 완료', len(manifest['files']), flush=True)


def audit():
    if (REVIEW / 'audit.json').exists():
        raise FileExistsError('Preserve completed audit')
    frozen = preservation()
    plan = read(OUT / 'training_plan.json')
    keys = pd.read_parquet(OUT / 'data/training_weather_temperature.parquet', columns=['station', 'time'])
    domain(keys)
    assert_training_stations(keys.station)
    assert set(keys.station) == set(plan['allowed_stations']) == set(ALLOWED)
    assert list(FEATURES) == plan['features']
    for fit in read(OUT / 'model/fit_receipts.json'):
        assert fit['training_rows'] == len(keys) and set(fit['training_stations']) == set(ALLOWED)
        assert fit['features'] == list(FEATURES)
        assert fit['model_sha256'] == sha(OUT / 'model' / (fit['name']+'.joblib'))
    # 정답 열이 있는 Parquet은 값을 열기 전에 지점과 기간만 검사한다.
    checked_tables = []
    for path in sorted((OUT / 'data').rglob('*.parquet')):
        columns = pq.read_schema(path).names
        if {'road_temp', 'ice', 'state_raw', 'observed_ice', 'actual_ice'} & set(columns):
            assert {'station', 'time'} <= set(columns), path.name
            ids = pd.read_parquet(path, columns=['station', 'time'])
            domain(ids)
            assert_training_stations(ids.station)
            checked_tables.append({'path': path.relative_to(OUT).as_posix(), 'rows': len(ids)})
    assert not set(PROTECTED_STATIONS) & set(keys.station)
    print('학습·포함 개발 정답의 지점/기간 격리 확인', flush=True)

    baseline = OUT / 'research/baselines'
    expected = read(baseline / 'summary.json')
    fixed = domain(pd.read_parquet(baseline / 'fixed_comparator_predictions.parquet'))
    comparisons = 0
    for method in expected['reports']:
        for minimum in [144, 130, 72, 1]:
            days = daily_table(fixed, fixed[method], expected['population'], minimum)
            current, stations = aggregate(days, expected['population'])
            ref, ref_stations, ref_days = reference(fixed, method, expected['population'], minimum)
            compare(ref, current)
            compare(current, expected['reports'][method]['coverage'][str(minimum)])
            pd.testing.assert_frame_equal(days[ref_days.columns], ref_days, check_exact=False, atol=1e-12, rtol=0)
            pd.testing.assert_frame_equal(stations[ref_stations.columns], ref_stations, check_exact=False, atol=1e-12, rtol=0)
            comparisons += 1
    print('독립 NumPy 지표 검산', comparisons, flush=True)

    protected = pd.read_csv(OUT / 'data/protected_predictions_10min.csv.gz', dtype={'station': str}, parse_dates=['time'])
    assert not {'road_temp', 'ice', 'state_raw', 'observed_ice', 'actual_ice'} & set(protected.columns)
    assert len(protected) == 103680 and not protected.duplicated(['station', 'time']).any()
    assert set(protected.station) == set(PROTECTED_STATIONS)
    missing = int(protected.predicted_ice.isna().sum())
    assert missing == 18

    required = ['README.md', 'requirements.txt', 'requirements-notebook.txt', 'environment.json',
        'training_plan.json', 'AI_USAGE.md', 'model/model_card.json', 'code/train.py', 'code/predict.py',
        'notebooks/submission_review.ipynb', 'demo/inference_demo.webm', 'demo/index.html',
        'reports/current/current_report.pdf']
    for name in required:
        assert (OUT / name).is_file() and (OUT / name).stat().st_size > 0, name
    import cv2
    video = cv2.VideoCapture(str(OUT / 'demo/inference_demo.webm'))
    assert video.isOpened()
    frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = video.get(cv2.CAP_PROP_FPS)
    decoded = 0
    while True:
        ok, frame = video.read()
        if not ok:
            break
        decoded += 1
    video.release()
    assert decoded == frames and frames > 0 and fps > 0
    visual = read(OUT / 'reports/current/visual_review.json')
    assert visual['pdf_sha256'] == sha(OUT / 'reports/current/current_report.pdf')

    commands = [
        ('csv_inference', [sys.executable, '-X', 'utf8', 'code/predict.py', '--input', 'data/weather_example.csv', '--output', 'validation/review_20261019_example.csv']),
        ('notebook', [sys.executable, '-X', 'utf8', str(ROOT / 'scripts/check_notebook.py'), str(OUT / 'notebooks/submission_review.ipynb')]),
    ]
    command_results = []
    for name, command in commands:
        if name == 'csv_inference' and (OUT / 'validation/review_20261019_example.csv').exists():
            actual = read_weather(OUT / 'validation/review_20261019_example.csv')
            previous = read_weather(OUT / 'data/example_predictions.csv')
            pd.testing.assert_frame_equal(actual, previous, check_dtype=False, check_exact=True)
            command_results.append({'name': name, 'reused_exactly_verified_output': True,
                                    'log_sha256': sha(REVIEW / (name+'.log'))})
            continue
        log = REVIEW / (name+'.log')
        if log.exists():
            old_log = REVIEW / (name+'_previous_'+sha(log)[:12]+'.log')
            if not old_log.exists():
                shutil.copy2(log, old_log)
        result = subprocess.run(command, cwd=OUT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240)
        (REVIEW / (name+'.log')).write_bytes(result.stdout)
        print(name, result.returncode, result.stdout.decode('utf-8', errors='replace')[-900:], flush=True)
        if result.returncode:
            raise RuntimeError('Review failed: '+name)
        command_results.append({'name': name, 'exit_code': 0, 'log_sha256': sha(REVIEW / (name+'.log'))})
    actual = read_weather(OUT / 'validation/review_20261019_example.csv')
    previous = read_weather(OUT / 'data/example_predictions.csv')
    pd.testing.assert_frame_equal(actual, previous, check_dtype=False, check_exact=True)
    assert preservation() == frozen
    write(REVIEW / 'audit.json', {
        'status': 'delivery_isolation_metrics_notebook_audit_passed', 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'training_rows': len(keys), 'training_stations': keys.station.nunique(), 'protected_training_overlap': [],
        'label_table_identity_checks': checked_tables, 'independent_metric_reports': comparisons,
        'example_rows': len(actual), 'csv_prediction_exact': True,
        'protected_prediction_rows': len(protected), 'protected_missing_ice_rows': missing,
        'video_frames_decoded': decoded, 'video_duration_seconds': frames/fps,
        'required_files_checked': required, 'commands': command_results,
        'new_model_fits': 0, 'threshold_changes': 0, 'protected_or_opened_outcomes_read': False,
        'old_frozen_files': frozen[0], 'reserved_frozen_files': frozen[1],
        'official_score_computed': False, 'competition_submitted': False, 'performance_qualified': False})


def package():
    audit_result = read(REVIEW / 'audit.json')
    assert audit_result['status'] == 'delivery_isolation_metrics_notebook_audit_passed'
    # 현재 변경 파일만 갱신한다. 데이터·모델·기존 예측/보고서는 이전 파일 해시를 유지한다.
    changed = ['README.md', 'AI_USAGE.md', 'docs/STATUS.md', 'docs/README.md',
        'docs/competition/COMPETITION_REQUIREMENTS.md', 'docs/competition/OFFICIAL_UPDATE_20261019.md',
        'docs/delivery/DELIVERY_REVIEW_20261019.md', 'docs/history/PROJECT_STATUS.md',
        'scripts/README.md', 'scripts/review_official_updates.py', 'scripts/build_submission_notebook.py',
        'scripts/review_delivery_20261019.py', 'scripts/check_notebook.py',
        'config/official_requirements_20261019.json']
    for name in changed:
        if name == 'README.md':
            continue  # 제출용 README는 별도 작성하여 보존한다.
        path = OUT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, path)
    for name in ['audit.json', 'initial_findings.json', 'notebook.log', 'csv_inference.log',
                 'unit_tests.log', 'repository_checks.json']:
        shutil.copy2(REVIEW / name, OUT / 'validation' / ('review_20261019_'+name))
    with zipfile.ZipFile(BASE) as z:
        old_readme = z.read('README.md').decode('utf-8')
    (OUT / 'README.md').write_text('''# 2026년 10월 19일 제출 후보 검토

기존 모델·예측·16쪽 보고서를 유지하고, 압축 해제한 자료만으로 실행되는 노트북을 추가했습니다.

- 시작 파일: [제출 검토 노트북](notebooks/submission_review.ipynb). Python 3.11에서 `python -m pip install -r requirements-notebook.txt`를 실행하고 같은 환경의 Jupyter 커널로 엽니다. Jupyter UI는 사용하는 편집기에서 제공합니다.
- 명령행 검증: `python -X utf8 scripts/check_notebook.py notebooks/submission_review.ipynb`. 기본 실행은 재학습하지 않으며 추론 144행과 기존 개발 지표 24개를 검산합니다.
- [10월 19일 공식 확인](docs/competition/OFFICIAL_UPDATE_20261019.md): 새 Q&A 목록 4건 확인, 상세 답변·첨부 바이트 미확인. 11월 6일은 참가신청 종료일이며 결과물 마감이 아닙니다.
- [검증 결과와 남은 일](docs/delivery/DELIVERY_REVIEW_20261019.md): 보호 정답 재평가·새 모델 튜닝·제출·외부 공개 없음. 보호 예측 부족 18행은 null 유지.
- 기존 `notebooks/analysis_review.ipynb`는 원 연구 작업 공간이 필요한 과거 노트북입니다. 이번 후보 검토에는 위 제출 노트북을 사용합니다.

현재 모델의 성능 적합 판정은 보류합니다. 운영체제·Python·CPU 실행 정보는 [environment.json](environment.json), 사용 라이브러리는 requirements.txt, 보고서는 [현재 PDF](reports/current/current_report.pdf), 데모영상은 [WebM](demo/inference_demo.webm)에 있습니다. 외부 API 인증정보는 실행에 필요하지 않습니다.

아래는 10월 16일 분석·실행 안내입니다.

'''+old_readme, 'utf-8')
    before = read(OUT / 'manifest.json')
    immutable = [n for n in before['files'] if n.startswith(('data/', 'model/', 'research/', 'demo/', 'reports/current/'))]
    for name in immutable:
        assert sha(OUT / name) == before['files'][name]['sha256'], name
    archive = OUT.with_suffix('.zip')
    if archive.exists():
        raise FileExistsError('Preserve packaged candidate')
    files = {p.relative_to(OUT).as_posix(): {'sha256': sha(p), 'bytes': p.stat().st_size}
             for p in sorted(OUT.rglob('*')) if p.is_file() and p.name != 'manifest.json'
             and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    (OUT / 'manifest.json').write_text(json.dumps({'version': 4, 'status': 'private_candidate_performance_not_qualified',
        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'files': files}, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name in [*files, 'manifest.json']:
            z.write(OUT / name, name)
    verified = verify_archive(archive)
    write(REVIEW / 'package_receipt.json', {'archive': archive.relative_to(ROOT).as_posix(),
        'archive_sha256': sha(archive), 'archive_bytes': archive.stat().st_size,
        'verified_files': len(verified['files']), 'unchanged_model_data_research_demo_report_files': len(immutable),
        'competition_submitted': False, 'model_promoted': False})
    print('새 비공개 후보 포장 완료', len(verified['files']), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, choices=['prepare', 'audit', 'package'])
    globals()[parser.parse_args().stage]()
