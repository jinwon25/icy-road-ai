"""v6 실행 자산을 보존하고 검수한 보고서·현재 문서를 비공개 v7에 묶는다."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.blind_icing_validation import DEFAULT, verify as verify_blind, read, write, now, old_freezes
from scripts.check_markdown import inspect_documents
from scripts.review_submission_bundle import verify_directory
from src.submission_archive import verify_archive
from src.data_source import sha256_file as sha

PRIVATE = ROOT / 'outputs/private'
OLD = PRIVATE / 'submission_candidate_20261025_v6'
OUT = PRIVATE / 'submission_candidate_20261026_v7'
REPORT = PRIVATE / 'editorial_report_20261026_v4'
OLD_SHA = 'b9cd4f701b033d7c6e3f8a0d370174ff23def05b7b55769ebe490213f5e9b439'
CORE = ('model/', 'data/', 'exports/', 'figures/', 'code/', 'src/', 'notebooks/', 'reports/', 'demo/', 'licenses/')
CORE_NAMES = {'extended_training_plan.json', 'requirements.txt', 'requirements-notebook.txt'}


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def source_checks():
    assert sha(OLD.with_suffix('.zip')) == OLD_SHA
    assert sha(DEFAULT / 'summary.json') == '45ebf8f83abc25857a085b84f76b292e34400364df0058d6355156ba16571a48'
    verify_blind(DEFAULT)
    assert old_freezes() == (47, 549)
    visual = read(REPORT / 'visual_review.json')
    receipt = read(REPORT / 'receipt.json')
    assert visual['status'] == 'passed' and visual['pages'] == 10
    assert visual['pdf_sha256'] == receipt['pdf_sha256'] == sha(REPORT / 'analysis_report_v7.pdf')
    assert receipt['manuscript_sha256'] == sha(ROOT / 'docs/delivery/ANALYSIS_REPORT.md')
    for name, expected in receipt['source_hashes'].items():
        assert sha(ROOT / name) == expected, 'Report source changed: ' + name


def core_check():
    original = read(OUT / 'provenance/v6_manifest.json')['files']
    names = [name for name in original if name.startswith(CORE) or name in CORE_NAMES]
    for name in names:
        assert sha(OUT / name) == original[name]['sha256'], name
    return names


def sync_index():
    """미커밋 사용자 수정은 제외하고 검토·스테이지한 문서만 반영한다."""
    git = ['git', '-c', 'safe.directory=' + ROOT.as_posix()]
    names = subprocess.check_output(git + ['ls-files', '-z'], cwd=ROOT).decode('utf8').split('\0')
    original = read(OUT / 'provenance/v6_manifest.json')['files']
    copied = {}
    for name in filter(None, names):
        allowed = name.startswith(('docs/', 'config/', 'scripts/', 'src/', 'tests/', '.github/', 'notebooks/')) or name in {'README.md', 'AI_USAGE.md', 'requirements-research.txt'}
        if not allowed:
            continue
        if name in original and not (name.startswith('docs/') or name.endswith('.md')):
            continue
        target = OUT / ('README_repository.md' if name == 'README.md' else name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(git + ['show', ':' + name], cwd=ROOT))
        copied[name] = sha(target)
    write(OUT / 'provenance/v7_source_index.json', dict(at_utc=now(), source='Git index; existing unstaged user work excluded', files=copied))


def manifest():
    files = {p.relative_to(OUT).as_posix(): dict(bytes=p.stat().st_size, sha256=sha(p))
             for p in OUT.rglob('*') if p.is_file() and p != OUT / 'manifest.json'
             and '__pycache__' not in p.parts and p.suffix != '.pyc' and p.relative_to(OUT).parts[0] != 'local_review'}
    write(OUT / 'manifest.json', dict(version=11, package_label='v7', status='private_review_candidate', at_utc=now(), files=files,
        production_model_version='v3', icing_version='v2', production_model_changed=False, competition_submitted=False,
        current_report='reports/analysis_report_v7.pdf', source_zip_sha256=OLD_SHA))


def prepare():
    if OUT.exists():
        raise FileExistsError('Preserve previous bundle')
    source_checks()
    verify_directory(OLD)
    for name in read(OLD / 'manifest.json')['files']:
        copy(OLD / name, OUT / name)
    copy(OLD / 'manifest.json', OUT / 'provenance/v6_manifest.json')
    copy(OLD.with_suffix('.receipt.json'), OUT / 'provenance/v6_archive_receipt.json')
    copy(OLD / 'README.md', OUT / 'README_v6.md')
    sync_index()
    copy(REPORT / 'analysis_report_v7.pdf', OUT / 'reports/analysis_report_v7.pdf')
    copy(REPORT / 'receipt.json', OUT / 'validation/v7_report_source.json')
    copy(REPORT / 'visual_review.json', OUT / 'validation/v7_report_visual.json')
    copy(PRIVATE / 'official_updates_editorial_20261025_v1/summary.json', OUT / 'provenance/official_20261025_2350.json')
    (OUT / 'README.md').write_text('''# 미관측 도로의 노면온도와 결빙 조건 · 비공개 검토 v7

공공 기상 이력으로 센서가 없는 도로의 온도를 추정하고 결빙 탐지의 한계와 구간별 활용 범위를 검토한 결과물입니다. 같은 개발 범위의 온도 MAE는 13.66% 낮아졌으나 결빙 F1은 기온 기준선보다 낮습니다. v7은 **온도 v3·결빙 v2를 유지하고 보고서와 검토 경로를 개편한 묶음**입니다.

## 읽는 순서

1. [현재 10쪽 분석 보고서](reports/analysis_report_v7.pdf): 문제·자료·검증·온도와 결빙 결과·새 지역 평가·활용과 한계.
2. [심사자 검토 안내](docs/delivery/REVIEWER_GUIDE.md): 핵심 질문·실행·발표 흐름.
3. [구간 탐색](demo/review/index.html)·[CSV 규약](docs/delivery/CSV_CONTRACT.md): 저장 결과와 입력 가용 범위 확인.
4. [공식 규정·일정](docs/competition/OFFICIAL_UPDATE_20261025.md)·[AI 지원 기록](AI_USAGE.md): 적용 조건과 실제 작업 범위.

온도 개발 비교는 9지점·두 겨울 310,091유효쌍이며 MAE 1.145698°C입니다. 결빙 일별 지점 F1은 현재 0.026554, 같은 가용 입력의 기온 기준선은 0.036601입니다. 반복 개발 점수이며 공식 성적이 아닙니다. 새 4지역 주 후보도 재현율 하락·8사건 손실·자료 품질 문제로 미채택했습니다.

## 실행 환경과 검사

Windows·Python 3.11·CPU 환경입니다. 주요 버전은 requirements 파일에 고정했습니다. 패키지 설치 이후 예제 추론·최종 재학습은 포함 자료로 실행하며 외부 예측 API나 키가 필요하지 않습니다. 새 폴더에 압축을 풀고 이 폴더를 작업 위치로 사용합니다.

```powershell
python -m pip install -r requirements-notebook.txt
python scripts/review_submission_bundle.py
python scripts/review_submission_bundle.py --smoke --output local_review/smoke.json
```

첫 검사는 전체 파일·해시·경로를 확인합니다. 실행 검사는 예측 144행을 기준 파일과 대조하고 노트북 5개 코드 셀을 실행합니다. 출력은 `local_review/`에 기록하며 기존 파일과 겹치면 새 이름을 사용합니다. 해당 예제는 실행 확인으로 독립 성능평가가 아닙니다.

학습·추론은 `code/train.py`, `code/predict.py`, [실행 노트북](notebooks/submission_review_v7.ipynb)에서 확인합니다. 새 노트북은 기존 코드 셀 5개를 그대로 유지하고 최신 보고서 연결과 지표 해석을 보완합니다. 구체적인 명령은 [실행 안내](README_v4.md)의 실행 절을 참고합니다. 그 문서의 과거 규정·최신 보고서 표기는 현재 안내로 대체합니다. 모든 연구 탐색 입력이 이 묶음에 들어 있는 것은 아닙니다.

## 파일 구성과 보존

`data/`는 포함 학습·예제 자료, `model/`은 고정 모델, `code/`와 `src/`는 처리·학습·추론 코드, `exports/`와 `figures/`는 CSV·지도·공간 파일입니다. `research/`는 비교 결과와 감사 근거, `validation/`은 실행·보존 기록, `licenses/`는 이용조건입니다. [보고서 원고](docs/delivery/ANALYSIS_REPORT.md)는 현재 PDF와 같은 문장입니다.

500m 843개·1km 423개는 같은 도로의 두 분할입니다. 지도는 조건 노출이며 사고확률·공식 위험등급이 아닙니다. 현재 추정 온도와 결빙에 쓰는 기준 온도를 구분하고 보호 입력 부족 18행은 NA로 둡니다.

기존 v6의 모델·예측·CSV·지도·노트북·데모·실행 코드는 해시로 보존합니다. `reports/current/current_report.pdf`는 10월 24일의 **과거 8쪽 보고서**입니다. 최신 보고서는 이 README 첫 링크와 `manifest.json`의 `current_report`를 기준으로 합니다. 과거 README·manifest·검증 기록도 해당 시점의 근거로 남깁니다. [v7 검증](docs/delivery/REVIEW_BUNDLE_V7_20261026.md)

실제 화면 조작 영상은 [review_walkthrough.webm](demo/review_walkthrough.webm), 추론 출력의 시각화 영상은 [extended_inference.mp4](demo/extended_inference.mp4)입니다. 두 영상 모두 학습 실행 전체를 녹화한 것으로 소개하지 않습니다.

10월 25일 23:50 KST 공식 확인에서 접수 날짜·경로는 별도 공지 예정입니다. 본 묶음은 접수 완료본이 아닙니다. 제공 자료의 승인받지 않은 제3자 열람·배포를 금지하며 ZIP·원자료·모델·예측·인증정보는 GitHub에 올리지 않습니다.
''', encoding='utf8')
    core = core_check(); manifest()
    print('PREPARED v7; preserved core files:', len(core), flush=True)


def verify():
    destination = OUT / 'validation/v7_delivery.json'
    if destination.exists(): raise FileExistsError('Preserve verification')
    source_checks(); sync_index()
    copy(REPORT / 'analysis_report_v7.pdf', OUT / 'reports/analysis_report_v7.pdf')
    copy(REPORT / 'receipt.json', OUT / 'validation/v7_report_source.json')
    copy(REPORT / 'visual_review.json', OUT / 'validation/v7_report_visual.json')
    core = core_check(); manifest()
    names = [p.relative_to(OUT).as_posix() for p in OUT.rglob('*.md') if '__pycache__' not in p.parts]
    errors = inspect_documents(OUT, names)
    if errors: raise ValueError('\n'.join(errors))
    local = OUT / 'local_review'; local.mkdir(exist_ok=True)
    attempt = 1
    while any(local.glob(f'v7_{attempt:02}*')): attempt += 1
    output = local / f'v7_{attempt:02}.json'
    env = os.environ.copy()
    env.update(OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2', LOKY_MAX_CPU_COUNT='2',
               TEMP=str(PRIVATE / 'icing_test_tmp_20261025'), TMP=str(PRIVATE / 'icing_test_tmp_20261025'))
    run = subprocess.run([sys.executable, '-X', 'utf8', 'scripts/review_submission_bundle.py', '--smoke', '--output', str(output.relative_to(OUT))],
                         cwd=OUT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
    output.with_suffix('.driver.log').write_bytes(run.stdout)
    assert run.returncode == 0, 'Execution failed; inspect ' + str(output.with_suffix('.driver.log'))
    result = read(output); assert result['prediction_rows_identical'] == 144
    for check in result['checks']:
        target = OUT / 'validation' / ('v7_' + check['name'] + '.log')
        copy(OUT / check['log'], target); check['log'] = target.relative_to(OUT).as_posix()
    old_notebook = read(OUT / 'notebooks/extended_submission_review.ipynb')
    new_notebook = read(OUT / 'notebooks/submission_review_v7.ipynb')
    old_cells = [c for c in old_notebook['cells'] if c['cell_type'] == 'code']
    new_cells = [c for c in new_notebook['cells'] if c['cell_type'] == 'code']
    assert old_cells == new_cells and len(new_cells) == 5
    command = [sys.executable, '-X', 'utf8', 'scripts/check_notebook.py', 'notebooks/submission_review_v7.ipynb']
    run = subprocess.run(command, cwd=OUT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
    log = OUT / 'validation/v7_current_notebook.log'; log.write_bytes(run.stdout)
    assert run.returncode == 0, 'Current notebook failed; inspect ' + str(log)
    result['current_notebook'] = dict(path='notebooks/submission_review_v7.ipynb', code_cells_identical=5,
                                      returncode=0, log=log.relative_to(OUT).as_posix())
    core_check(); source_checks()
    write(destination, dict(status='v7_delivery_verified', at_utc=now(), source_zip_sha256=OLD_SHA,
          core_files_unchanged=len(core), core_files=core, markdown_documents=len(names), execution=result,
          report_sha256=sha(OUT / 'reports/analysis_report_v7.pdf'), production_model_changed=False, competition_submitted=False))
    manifest(); verify_directory(OUT)
    print('VERIFIED v7; documents:', len(names), '; prediction rows:', result['prediction_rows_identical'], flush=True)


def package():
    source_checks(); core_check()
    assert read(OUT / 'validation/v7_delivery.json')['status'] == 'v7_delivery_verified'
    # 검사 후 문서의 완료 수치가 바뀌면 인덱스를 다시 동기화하되 실행 자산은 보존한다.
    sync_index(); core_check(); manifest()
    source_manuscript = REPORT / 'ANALYSIS_REPORT.md'
    bundled_manuscript = OUT / 'docs/delivery/ANALYSIS_REPORT.md'
    source_text = source_manuscript.read_text(encoding='utf8')
    assert source_text == bundled_manuscript.read_text(encoding='utf8')
    write(OUT / 'validation/v7_manuscript_equivalence.json', dict(status='identical_text',
        source_raw_sha256=sha(source_manuscript), bundled_raw_sha256=sha(bundled_manuscript),
        normalized_utf8_sha256=hashlib.sha256(source_text.encode('utf8')).hexdigest(),
        note='Git index may normalize CRLF to LF; PDF and bundled Markdown use identical text.'))
    manifest()
    names = [p.relative_to(OUT).as_posix() for p in OUT.rglob('*.md') if '__pycache__' not in p.parts]
    assert not inspect_documents(OUT, names)
    target = OUT.with_suffix('.zip')
    if target.exists(): raise FileExistsError('Preserve existing ZIP')
    verify_directory(OUT)
    records = read(OUT / 'manifest.json')['files']
    from src.kma_rwis_download import load_auth_key
    key = load_auth_key(ROOT / 'secret.env').encode()
    for name in records:
        assert not name.endswith(('.env', '.pem', '.key')) and '/.git/' not in '/' + name
        if (OUT / name).suffix in {'.py', '.json', '.md', '.txt', '.ipynb', '.html', '.js', '.log'}:
            assert key not in (OUT / name).read_bytes(), name
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in sorted(records): archive.write(OUT / name, name)
        archive.write(OUT / 'manifest.json', 'manifest.json')
    checked = verify_archive(target)
    receipt = dict(status='v7_archive_verified', at_utc=now(), archive=target.name, bytes=target.stat().st_size,
                   sha256=sha(target), files=len(checked['files']), manifest_sha256=sha(OUT / 'manifest.json'),
                   model_version='v3', icing_version='v2', competition_submitted=False)
    write(target.with_suffix('.receipt.json'), receipt)
    print(receipt, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['prepare', 'verify', 'package'], required=True)
    globals()[parser.parse_args().stage]()
