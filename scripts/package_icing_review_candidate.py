"""v4 실행 자산을 보존하고 결빙 후속 연구·최신 안내를 v5에 묶어 검증한다."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.submission_archive import verify_archive
from scripts.check_markdown import inspect_documents
from scripts.evaluate_method_blending import preservation

PRIVATE = ROOT / 'outputs/private'
OLD = PRIVATE / 'submission_candidate_20261024_v4'
OUT = PRIVATE / 'submission_candidate_20261025_v5'
OLD_SHA = 'fdf1ffb7007ba9898817968af0731a33bc9426ca676039d3931482d190500ff2'
STUDIES = {'fixed': 'icing_transition_20261025_v1',
           'exact': 'icing_threshold_refinement_20261025_v1',
           'comparison': 'icing_transition_comparison_20261025_v1'}


def read(path):
    return json.loads(path.read_text('utf-8'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', 'utf-8')


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def decision():
    comparison = read(PRIVATE / STUDIES['comparison'] / 'summary.json')
    assert comparison['status'] == 'icing_transition_comparison_complete'
    assert comparison['eligible_candidates'] == []
    audit = PRIVATE / 'icing_transition_audit_20261025_v1/receipt.json'
    assert comparison['audit_sha256'] == sha(audit)
    assert read(audit)['status'] == 'icing_transition_independently_verified'
    for key, source in [('fixed_grid', 'fixed'), ('exact_threshold', 'exact')]:
        assert read(audit)['checks'][key]['summary_sha256'] == sha(PRIVATE / STUDIES[source] / 'summary.json')
    assert sha(OLD.with_suffix('.zip')) == OLD_SHA
    return comparison


def manifest():
    files = {p.relative_to(OUT).as_posix(): dict(sha256=sha(p), bytes=p.stat().st_size)
             for p in OUT.rglob('*') if p.is_file() and p != OUT/'manifest.json'
             and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    write(OUT/'manifest.json', dict(version=9, package_label='v5', status='private_icing_review_candidate',
          created_at_utc=datetime.now(timezone.utc).isoformat(), files=files,
          development_scope='extended_two_winter', production_model_version='v3', icing_version='v2',
          production_model_changed=False, independent_performance_qualified=False, competition_submitted=False))


def core_check():
    original = read(OUT/'provenance/v4_manifest.json')['files']
    core = [name for name in original if name.startswith(('model/', 'data/', 'exports/', 'figures/',
            'code/', 'src/', 'notebooks/', 'reports/', 'demo/', 'licenses/'))
            or name in ['extended_training_plan.json', 'requirements.txt', 'requirements-notebook.txt']]
    for name in core:
        assert sha(OUT/name) == original[name]['sha256'], name
    return core


def sync_guides():
    """기존 실행 코드는 보존하고 문서와 추가 소스만 동기화한다."""
    names = subprocess.check_output(['git', '-c', 'safe.directory='+ROOT.as_posix(), 'ls-files', '-z',
                                     '--cached', '--others', '--exclude-standard'], cwd=ROOT).decode('utf-8').split('\0')
    additions = []
    original_names = set(read(OUT/'provenance/v4_manifest.json')['files'])
    for name in filter(None, names):
        source = ROOT/name
        if not source.is_file():
            continue
        allowed = name.startswith(('docs/', 'config/', 'scripts/', 'src/', 'tests/', '.github/', 'notebooks/')) or name == 'requirements-research.txt'
        if allowed and (name.startswith('docs/') or source.suffix == '.md' or name not in original_names):
            copy(source, OUT/name)
            additions.append(name)
    copy(ROOT/'AI_USAGE.md', OUT/'AI_USAGE.md')
    copy(ROOT/'README.md', OUT/'README_repository.md')
    write(OUT/'provenance/current_source_sync.json', {name: sha(OUT/name) for name in additions})
    (OUT/'README.md').write_text('''# 도로 결빙 위험 추정 · 비공개 제출 검토 v5

기상 자료로 관측 장비가 없는 도로의 노면온도와 결빙 여부를 추정하고, 도로 구간별 결과를 지도·CSV로 확인하는 연구 묶음입니다. **10월 25일 추가 결빙 실험은 기존 성능을 넘지 못해 온도 v3·결빙 v2 모델을 유지했습니다.** 이번 묶음은 최신 연구·공식 확인·처음 읽는 안내를 추가합니다.

## 먼저 읽을 내용

1. [처음 읽는 안내](docs/START_HERE.md): 문제·자료·평가 지표·버전 설명.
2. [현재 상태](docs/STATUS.md)와 [새 결빙 연구](docs/research/ICING_TRANSITION_REVIEW_20261025.md): 실제 결과와 미채택 이유.
3. [공식 규정·제출 일정](docs/competition/OFFICIAL_UPDATE_20261025.md): 결과물 날짜·방법은 별도 공지 예정. 11월 6일은 참가신청 종료일.
4. [CSV 열·단위](docs/delivery/CSV_CONTRACT.md)와 [구간 탐색 화면](demo/review/index.html): 저장 결과의 확인 방법.
5. [보존한 v4 실행 안내](README_v4.md): 포함 모델의 추론·노트북·재학습 절차.

## 결과를 해석하는 범위

같은 개발 자료에서 온도 MAE는 1.145698°C입니다. 결빙의 일별 지점 평균 F1은 0.026554로 동일 입력 범위의 ASOS 기온 기준선 0.036601보다 낮습니다. 보호 정답은 추가 학습·선택에 사용하지 않았고, 같은 개발 지역을 반복 사용했으므로 새 독립 평가·공식 점수·입상 보장이 아닙니다. 입력 부족 18행은 NA입니다.

## 실행 예제

이 폴더를 작업 위치로 사용하고 Python 3.11 환경에서 포함 의존성을 설치합니다. 설치에는 패키지 접근이 필요하며, 설치 후 아래 추론은 포함 파일로 실행됩니다. 출력 폴더는 새 경로를 사용하세요.

```powershell
python -m pip install -r requirements-notebook.txt
python code/predict.py --input data/weather_example.csv --output local_review/predictions.csv --output-start 2024-12-15 --output-end 2024-12-16
python scripts/check_notebook.py notebooks/extended_submission_review.ipynb
```

명령 예제의 예측 144행은 `data/example_predictions.csv`와 비교할 수 있습니다. 노트북은 포함 모델·입력으로 5개 코드 셀을 실행합니다. 모델 실행 근거와 [실제 브라우저 조작 영상](demo/review_walkthrough.webm)은 구별합니다. 후자는 저장 결과를 탐색하는 화면을 녹화한 것입니다.

## 무엇을 보존하고 추가했는가

v4 모델·입력·예측·CSV 11종·지도·8쪽 보고서·실행 코드·노트북·데모를 그대로 보존했습니다. `research/icing_transition/`에는 두 탐색법의 예측·집계·선택 기록을, `validation/icing_transition/`에는 저장 모델 재실행과 독립 검산·테스트 로그를 더했습니다. 미채택 연구 모델 가중치와 전체 연구 입력은 원 비공개 작업 공간에 남겨 두었습니다. 모든 과거 연구 명령을 이 묶음만으로 실행할 수 있다는 뜻은 아닙니다.

`validation/icing_review_delivery.json`은 보존·명령 실행·노트북·Markdown 검사 결과입니다. `manifest.json`은 각 파일의 크기와 SHA-256 목록이며 ZIP 검증 영수증은 압축 파일 옆에 있습니다. [v4 당시 안내](README_v4.md)의 일정 확인 범위는 위 최신 공식 문서로 대체됩니다. 원본 기록은 비교를 위해 보존합니다.

대회 제공 자료는 승인받지 않은 제3자에게 제공하지 않습니다. 이 묶음은 로컬 비공개 검토용이며 대회 접수·외부 공개를 수행한 결과가 아닙니다. [AI 활용 기록](AI_USAGE.md)에는 참가자 지시와 AI가 실제 수행한 분석·검산을 구별했습니다.
''', 'utf-8')


def prepare():
    if OUT.exists():
        raise FileExistsError('Preserve existing candidate')
    decision()
    frozen = preservation()
    original = read(OLD/'manifest.json')
    for name, record in original['files'].items():
        assert sha(OLD/name) == record['sha256'], name
        copy(OLD/name, OUT/name)
    copy(OLD/'manifest.json', OUT/'provenance/v4_manifest.json')
    copy(OLD.with_suffix('.receipt.json'), OUT/'provenance/v4_archive_receipt.json')
    copy(OLD/'README.md', OUT/'README_v4.md')
    copy(OLD/'AI_USAGE.md', OUT/'AI_USAGE_v4.md')
    for kind, source in STUDIES.items():
        for p in (PRIVATE/source).iterdir():
            if p.is_file() and p.suffix in ['.json', '.csv', '.parquet', '.png']:
                copy(p, OUT/'research/icing_transition'/kind/p.name)
    copy(PRIVATE/'icing_transition_audit_20261025_v1/receipt.json', OUT/'validation/icing_transition/audit.json')
    for filename in ['icing_transition_tests_20261025.log', 'icing_transition_tests_20261025_retry1.log',
                     'markdown_scope_review_20261025.json']:
        copy(PRIVATE/filename, OUT/'validation/icing_transition'/filename)
    sync_guides()
    core = core_check()
    write(OUT/'provenance/icing_review_plan.json', dict(source_zip_sha256=OLD_SHA, core_files=len(core),
          frozen_counts=list(frozen), production_model_changed=False, protected_labels_read=False))
    manifest()
    print('v5 prepared; preserved core files:', len(core), flush=True)


def verify():
    destination = OUT/'validation/icing_review_delivery.json'
    if destination.exists():
        raise FileExistsError('Preserve completed verification')
    decision()
    frozen = preservation()
    sync_guides()
    core = core_check()
    names = [p.relative_to(OUT).as_posix() for p in OUT.rglob('*.md') if '__pycache__' not in p.parts]
    errors = inspect_documents(OUT, names)
    if errors:
        raise ValueError('\n'.join(errors))
    environment = os.environ.copy()
    temp = PRIVATE/'icing_test_tmp_20261025'
    temp.mkdir(exist_ok=True)
    environment.update(OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2', LOKY_MAX_CPU_COUNT='2',
                       TMP=str(temp), TEMP=str(temp))
    checks = []
    commands = [('notebook', ['scripts/check_notebook.py', 'notebooks/extended_submission_review.ipynb']),
                ('prediction_cli', ['code/predict.py', '--input', 'data/weather_example.csv',
                  '--output', 'validation/icing_transition/cli_prediction.csv',
                  '--output-start', '2024-12-15', '--output-end', '2024-12-16'])]
    for name, args in commands:
        run = subprocess.run([sys.executable, '-X', 'utf8', *args], cwd=OUT, env=environment,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
        log = OUT/f'validation/icing_transition/{name}.log'
        attempt = 1
        while log.exists():
            log = OUT/f'validation/icing_transition/{name}_retry{attempt}.log'
            attempt += 1
        log.write_bytes(run.stdout)
        print(name, run.returncode, run.stdout.decode('utf-8', errors='replace')[-700:], flush=True)
        assert run.returncode == 0, name
        checks.append(dict(name=name, returncode=0, log_file=log.relative_to(OUT).as_posix(), log_sha256=sha(log)))
    import pandas as pd
    args = dict(dtype={'station': str, 'predicted_ice': 'Int64'}, parse_dates=['time'], float_precision='round_trip')
    predicted = pd.read_csv(OUT/'validation/icing_transition/cli_prediction.csv', **args)
    pd.testing.assert_frame_equal(predicted, pd.read_csv(OUT/'data/example_predictions.csv', **args), check_exact=True)
    raw = (PRIVATE/'icing_transition_tests_20261025_retry1.log').read_bytes()
    unit = raw.decode('utf-16') if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else raw.decode('utf-8-sig')
    match = re.search(r'(\d+) passed', unit)
    assert match and int(match[1]) == 345 and 'FAILED' not in unit
    assert preservation() == frozen
    core_check()
    write(destination, dict(status='icing_review_delivery_verified', checks=checks, unit_tests=345,
          markdown_documents=len(names), prediction_rows=len(predicted),
          original_core_files_unchanged=len(core), core_files=core, source_zip_sha256=OLD_SHA,
          frozen_counts=list(frozen), production_model_changed=False, protected_labels_read=False,
          new_independent_assessment=False, competition_submitted=False,
          created_at_utc=datetime.now(timezone.utc).isoformat()))
    manifest()
    print('v5 delivery verified', flush=True)


def package():
    assert read(OUT/'validation/icing_review_delivery.json')['status'] == 'icing_review_delivery_verified'
    decision()
    core_check()
    target = OUT.with_suffix('.zip')
    if target.exists():
        raise FileExistsError('Preserve completed ZIP')
    # 검증 후 내용을 다시 복사하지 않고 최종 파일 바이트를 ZIP에서 대조한다.
    manifest()
    records = read(OUT/'manifest.json')['files']
    for name in records:
        assert not name.endswith(('.key', '.pem', '.env')) and '/.git/' not in '/'+name
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in sorted(records):
            archive.write(OUT/name, name)
        archive.write(OUT/'manifest.json', 'manifest.json')
    checked = verify_archive(target)
    receipt = dict(status='icing_review_archive_verified', archive=target.name, bytes=target.stat().st_size,
                   sha256=sha(target), files=len(checked['files']), manifest_sha256=sha(OUT/'manifest.json'),
                   production_model_version='v3', production_model_changed=False, competition_submitted=False)
    write(target.with_suffix('.receipt.json'), receipt)
    print(json.dumps(receipt, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['prepare', 'verify', 'package'], required=True)
    globals()[parser.parse_args().stage]()
