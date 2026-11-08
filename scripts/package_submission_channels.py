"""보존된 v7을 문서자료·모델자료 두 ZIP으로 준비하고 전 파일·실행을 확인한다."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.check_markdown import inspect_documents
from scripts.review_submission_bundle import verify_directory
from src.submission_archive import safe_name

SOURCE = ROOT / 'outputs/private/submission_candidate_20261026_v7'
CORE = ('model/', 'data/', 'exports/', 'figures/', 'code/', 'src/', 'notebooks/', 'reports/', 'demo/', 'licenses/')
UPDATES = (
    'scripts/review_submission_bundle.py', 'scripts/review_official_updates.py',
    'scripts/package_submission_channels.py', 'tests/test_bundle_review.py',
    'tests/test_official_review.py', 'tests/test_submission_channels.py',
    'docs/competition/OFFICIAL_UPDATE_20261031.md', 'docs/competition/COMPETITION_REQUIREMENTS.md',
    'docs/delivery/FOLLOWUP_READINESS_20261031.md', 'docs/delivery/RISK_CRITERIA_20261031.md',
    'docs/STATUS.md', 'docs/README.md', 'scripts/README.md', 'config/README.md',
    'config/official_requirements_20261031.json', 'AI_USAGE.md',
)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def manifest(folder, channel):
    files = {p.relative_to(folder).as_posix(): {'bytes': p.stat().st_size, 'sha256': sha(p)}
             for p in folder.rglob('*') if p.is_file() and p.name != 'manifest.json'
             and '__pycache__' not in p.parts and p.relative_to(folder).parts[0] != 'local_review'}
    # 하위 exports 등의 manifest도 재현 자료이므로 포함한다.
    for p in folder.rglob('manifest.json'):
        if p != folder / 'manifest.json' and p.relative_to(folder).parts[0] != 'local_review':
            files[p.relative_to(folder).as_posix()] = {'bytes': p.stat().st_size, 'sha256': sha(p)}
    value = dict(package_label='submission_20261031', channel=channel, files=files,
                 status='local_submission_candidate', competition_submitted=False,
                 current_report='reports/analysis_report_v7.pdf')
    if channel == 'model':
        value.update(current_notebook='notebooks/submission_review_v7.ipynb',
                     production_model_version='v3', icing_version='v2', production_model_changed=False)
    write(folder / 'manifest.json', value)


def verify_channel_archive(path, root_name):
    """ZIP의 단일 최상위 폴더·구성원·해시를 압축 해제 없이 전량 확인한다."""
    safe_name(root_name)
    if '/' in root_name:
        raise ValueError('One top-level folder required')
    prefix = root_name + '/'
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive member')
        for info in infos:
            safe_name(info.filename)
            if not info.filename.startswith(prefix) or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('Unexpected root or linked archive member')
        records = json.loads(archive.read(prefix + 'manifest.json'))['files']
        if set(names) != {prefix + name for name in records} | {prefix + 'manifest.json'}:
            raise ValueError('Archive membership differs from manifest')
        for name, record in records.items():
            safe_name(name)
            with archive.open(prefix + name) as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if digest != record['sha256'] or archive.getinfo(prefix + name).file_size != record['bytes']:
                raise ValueError('Archive hash or size mismatch: ' + name)
    return {'files': len(records), 'sha256': sha(path), 'bytes': path.stat().st_size, 'root': root_name}


def archive_channel(folder):
    verify_directory(folder)
    target = folder.with_suffix('.zip')
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in sorted(read(folder / 'manifest.json')['files']) + ['manifest.json']:
            archive.write(folder / name, folder.name + '/' + name)
    return verify_channel_archive(target, folder.name)


MODEL_README = '''# 미관측 도로 노면온도·결빙 조건 · 모델자료

2026 DATA·AI 분석 경진대회 전북 고속도로 과제의 모델 실행 자료입니다. 온도 모델 v3·결빙 판정 v2·v7 보고서와 기존 산출물을 유지하고 10월 31일 제출 형식과 재현 검사를 보완했습니다. 대회 접수 완료본이 아닙니다.

## 실행 환경과 시작 방법

Windows·Python 3.11·CPU에서 검증했습니다. GPU·CUDA·외부 AI 예측 API·인증키는 필요하지 않습니다. 주요 라이브러리 버전은 `requirements.txt`와 `requirements-notebook.txt`에 고정되어 있습니다. 최초 설치에는 패키지 다운로드가 필요합니다. ZIP을 해제하고 `icy_road_model` 폴더에서 실행합니다.

```powershell
python -m pip install -r requirements-notebook.txt
$env:OMP_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
python scripts/review_submission_bundle.py --smoke --output local_review/reviewer.json
```

전체 파일 해시, 예제 144행의 정확한 일치, [현재 노트북](notebooks/submission_review_v7.ipynb) 실행을 검사합니다. 출력 이름이 이미 있으면 새 이름을 사용합니다. 기본 노트북 실행은 재학습하지 않습니다.

```powershell
python -X utf8 code/train.py --output local_review/my_refit
python -X utf8 code/predict.py --input data/weather_example.csv --output local_review/my_prediction.csv --output-start 2024-12-15 --output-end 2024-12-16
```

학습은 포함된 허용 23곳·두 겨울 자료와 고정 계획을 사용합니다. 기존 전체 재학습 검증은 `validation/extended_delivery.json`, 이번 실행 검사는 `local_review/submission_smoke.json`과 ZIP 밖의 `submission_receipt.json`을 참고합니다. 로컬 실행 로그는 검증 후 ZIP에 `validation/submission_20261031/`로 복사합니다. 전체 연구 탐색 입력이 모두 포함된 것은 아닙니다.

## 파일 구성과 읽는 순서

1. [10쪽 보고서](reports/analysis_report_v7.pdf), [현재 제출 조건](docs/competition/OFFICIAL_UPDATE_20261031.md).
2. [결빙 조건 기준표 설명](docs/delivery/RISK_CRITERIA_20261031.md), `data/condition_evidence_criteria.csv`, [CSV 규약](docs/delivery/CSV_CONTRACT.md).
3. [노트북](notebooks/submission_review_v7.ipynb), [구간 탐색](demo/review/index.html), [AI 지원 기록](AI_USAGE.md).

| 경로 | 역할 |
| --- | --- |
| data/ · model/ | 학습·예제·기상 입력·추정 결과와 고정 모델. 보호 정답 제외 |
| src/ · code/ · scripts/ | 데이터 처리·모델·학습·추론·검사. 주요 진입점은 code/train.py와 code/predict.py |
| notebooks/ | 자료 해시·전처리·추론·개발 지표·출력 검사와 재학습 설명 |
| demo/ | 추론 출력 시각화 MP4·화면 조작 WebM·오프라인 탐색. 전체 학습 녹화 아님 |
| figures/ · exports/ | 500m·1km 지도·Shapefile·CSV·10분 예측·일별 지표 |
| reports/ · docs/ · research/ | 보고서·방법·한계·비교 실험·집계 근거 |
| licenses/ · provenance/ · validation/ | 이용조건·출처·과거 봉인·실행 검증 |

과거 README·날짜별 문서·manifest는 당시 이력입니다. 현재 진입점은 이 README와 최상위 manifest입니다. `reports/current/current_report.pdf`는 과거 8쪽 보고서입니다.

## 결과와 해석

같은 개발 9곳·두 겨울·310,091유효쌍에서 온도 MAE는 1.145698°C로 기존 대비 13.66% 감소했습니다. 현재 결빙 F1 0.026554는 같은 입력 기온 기준선 0.036601보다 낮습니다. 반복 개발 점수이며 공식 성적이 아닙니다. 새 4지역 주 후보도 8사건 손실·자료 품질 문제로 미채택했습니다.

500m 843개·1km 423개는 같은 도로의 두 분할입니다. 조건 노출과 환경 상관을 사고확률·현장 위험등급으로 해석하지 않습니다. 보호 입력 부족 18행은 NA입니다. 센서·제설 이력과 참가자의 직접 검토·최종 판단이 남아 있습니다.

## 제출과 이용 조건

10월 27일 접수 개시와 문서자료·모델자료 ZIP 구분은 사용자 제공 공식 공지·제출 화면을 근거로 합니다. 제공 본문에는 마감 날짜가 없으며 참가신청 종료일로 대신 확정하지 않습니다. 문서자료 ZIP은 별도로 준비했습니다. 이 자료는 승인된 대회 심사를 위한 비공개 후보이며 제3자 배포용이 아닙니다. API 키·신청서·개인 인증 파일은 포함하지 않습니다.
'''

DOCUMENT_README = '''# 전북 고속도로 노면온도·결빙 조건 분석 · 문서자료

[분석 보고서](reports/analysis_report_v7.pdf)는 개요, 활용 데이터, 모델 개발 방법, 실험·평가, 활용 가능성과 한계를 설명하는 10쪽 문서입니다. 분석 기준일은 10월 25일이고 10월 31일 준비에서 모델·수치는 변경하지 않았습니다.

| 자료 | 읽는 목적 |
| --- | --- |
| [분석 보고서](reports/analysis_report_v7.pdf) | 문제·자료·공간 검증·온도 개선·결빙 실패·기대 활용 |
| [결빙 조건 기준표](RISK_CRITERIA.md) | 실행 임계값·환경 해석·현장 위험등급 검증의 한계 |
| [AI 지원 요약](AI_USAGE.md) | 지원 단계·선택 근거·실패·참가자 직접 검토 범위 |
| [500m 지도](figures/candidate_condition_map_500m.jpg) | 저온·수분 조건 노출. 실제 결빙률·사고확률 아님 |
| [1km 지도](figures/candidate_condition_map_1000m.jpg) | 동일 도로를 다른 규모로 표현 |

온도 MAE 1.145698°C와 13.66% 감소는 동일 개발 9곳·두 겨울·310,091유효쌍의 비교입니다. 현재 결빙 F1 0.026554는 같은 입력 기온 기준선 0.036601보다 낮습니다. 새 4지역 주 후보는 재현율 하락·8사건 손실·자료 품질 문제로 미채택했습니다. 공식 성적이 아닙니다.

모델자료 ZIP은 별도로 제출하며 학습·추론 코드, 고정 모델, 데이터, 실행 Notebook, 환경 파일, 데모, 모든 CSV·공간파일과 상세 AI·이용조건 기록을 포함합니다. 보고서에 표시된 실행 경로는 모델자료 내부 경로입니다. 문서자료 ZIP만으로 모델이 실행되는 것은 아닙니다.

10월 27일 접수 개시와 두 ZIP 형식은 사용자 제공 공식 공지·화면으로 확인했습니다. 제공 본문에는 마감 날짜가 없어 미확인입니다. 원본 보고서·모델의 과거 검증을 유지한 로컬 제출 후보로, 대회 접수 완료를 의미하지 않습니다. 센서·제설 자료와 현장 위험기준 검증, 참가자 최종 검토가 남아 있습니다.
'''

AI_SUMMARY = '''# AI 활용과 검토 요약

Codex가 문제·문헌 검토, 전처리·모델·평가·검산 코드 작성과 실행, 실험 비교·실패 분석, 보고서·재현 자료·제출 묶음 정리를 지원했습니다. 과거 작업의 도구·모델 표기는 모델자료의 전체 AI_USAGE.md를 따릅니다. 이번 작업은 Codex 지원으로 수행했습니다.

참가자는 개인 프로젝트의 수행 주체이며 대회 주제·작업 경로·자료 확보·후속 검토 방향을 지정했습니다. 10월 31일에는 현황 파악과 후속 작업을 요청하고 공식 공지·제출 화면·문제 설명을 제공했습니다. AI가 실행한 검산과 코드 수정을 참가자의 수동 검토로 기재하지 않습니다. 참가자의 직접 모델 선택·최종 검토 내용은 실제 수행 후 추가해야 합니다.

동일 개발 범위의 온도 오차가 줄어 온도 v3를 유지했습니다. 결빙 후속 실험은 기준선 미달, 지역·겨울·재현율 악화 또는 기존 탐지 사건 손실 때문에 채택하지 않았습니다. 새 4지역 주 후보의 F1 상승도 8사건 손실과 관측 품질 실패로 채택하지 않았습니다. 결빙 v2 유지가 공식 F1 최대화를 입증한 선택은 아닙니다.

10월 31일에는 공지 수집 실패가 성공 종료되는 문제와 과거 노트북만 실행하는 검사 도구를 보완했습니다. 기존 모델·예측·보호 평가를 보존하고 코드 테스트·파일 해시·예제 예측·현재 노트북·두 ZIP 전량 검증을 수행한 기록은 모델자료와 상위 제출 영수증에 연결합니다. 새 학습·독립 성능평가·문의 발송·대회 접수는 수행하지 않았습니다.
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise FileExistsError('Preserve previous delivery; choose a new output directory')
    if out.is_relative_to(SOURCE.resolve()):
        raise ValueError('Output must not modify the preserved source bundle')
    baseline = verify_directory(SOURCE)
    original = read(SOURCE / 'manifest.json')
    archive_receipt = read(SOURCE.with_suffix('.receipt.json'))
    if sha(SOURCE.with_suffix('.zip')) != archive_receipt['sha256']:
        raise ValueError('Original v7 archive changed')
    model, documents = out / 'icy_road_model', out / 'icy_road_documents'
    out.mkdir(parents=True)
    for name in original['files']:
        copy(SOURCE / name, model / name)
    copy(SOURCE / 'manifest.json', model / 'provenance/v7_manifest.json')
    copy(SOURCE / 'README.md', model / 'README_v7.md')
    for name in UPDATES:
        copy(ROOT / name, model / name)
    copy(ROOT / 'README.md', model / 'README_repository.md')
    (model / 'README.md').write_text(MODEL_README, encoding='utf8')
    preserved = [name for name in original['files'] if name.startswith(CORE)]
    for name in preserved:
        if sha(model / name) != original['files'][name]['sha256']:
            raise ValueError('Core asset changed: ' + name)
    write(model / 'provenance/submission_20261031.json', dict(
        at_utc=datetime.now(timezone.utc).isoformat(), source_archive_sha256=archive_receipt['sha256'],
        source_files=baseline['files'], core_files_preserved=len(preserved),
        updated_sources={name: sha(ROOT / name) for name in UPDATES}, competition_submitted=False))
    documents.mkdir()
    (documents / 'README.md').write_text(DOCUMENT_README, encoding='utf8')
    (documents / 'AI_USAGE.md').write_text(AI_SUMMARY, encoding='utf8')
    copy(ROOT / 'docs/delivery/RISK_CRITERIA_20261031.md', documents / 'RISK_CRITERIA.md')
    for name in ('reports/analysis_report_v7.pdf', 'figures/candidate_condition_map_500m.jpg',
                 'figures/candidate_condition_map_1000m.jpg', 'data/condition_evidence_criteria.csv'):
        copy(model / name, documents / name)
    manifest(model, 'model')
    environment = os.environ.copy()
    environment.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='2',
                       OPENBLAS_NUM_THREADS='2', LOKY_MAX_CPU_COUNT='2')
    run = subprocess.run([sys.executable, '-X', 'utf8', 'scripts/review_submission_bundle.py',
        '--smoke', '--output', 'local_review/submission_smoke.json'], cwd=model, env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
    (out / 'model_execution.log').write_bytes(run.stdout)
    if run.returncode:
        raise RuntimeError('Model execution failed; inspect model_execution.log')
    execution = read(model / 'local_review/submission_smoke.json')
    for p in (model / 'local_review').glob('submission_smoke*'):
        copy(p, model / 'validation/submission_20261031' / p.name)
    # 최초 manifest는 실행 전 기록으로 보존하고 새 검증 기록을 포함해 다시 생성한다.
    (model / 'manifest.json').rename(model / 'provenance/submission_pre_execution_manifest.json')
    manifest(model, 'model')
    manifest(documents, 'documents')
    secret_path = ROOT / 'secret.env'
    local_secrets = []
    if secret_path.exists():
        for line in secret_path.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                value = line.split('=', 1)[1].strip().strip('\"\x27')
                if len(value) >= 12:
                    local_secrets.append(value)
    for folder in (model, documents):
        names = list(read(folder / 'manifest.json')['files'])
        errors = inspect_documents(folder, [name for name in names if name.endswith('.md')])
        for name in names:
            p = folder / name
            if p.name in {'secret.env', '.env'} or p.suffix.lower() in {'.key', '.pem', '.hwp'}:
                errors.append('Forbidden private file: ' + name)
            if p.suffix in {'.py', '.md', '.json', '.ipynb', '.yml', '.txt'}:
                text = p.read_text(encoding='utf-8-sig')
                if re.search(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|RGAPI-[A-Za-z0-9-]{30,}|sk-[A-Za-z0-9_-]{30,})', text):
                    errors.append('Credential pattern: ' + name)
                if any(value in text for value in local_secrets):
                    errors.append('Local credential value: ' + name)
        if errors:
            raise ValueError('\n'.join(errors))
    results = {channel: archive_channel(folder) for channel, folder in [('documents', documents), ('model', model)]}
    verify_directory(SOURCE)
    write(out / 'submission_receipt.json', dict(status='two_channel_archives_verified',
        at_utc=datetime.now(timezone.utc).isoformat(), archives=results, execution=execution,
        original_v7_archive_sha256=sha(SOURCE.with_suffix('.zip')), core_files_preserved=len(preserved),
        model_or_prediction_changed=False, competition_submitted=False,
        remaining=['마감 날짜·용량 제한 확인', '참가자 직접 검토·최종 판단', '현장 위험등급 검증·결빙 성능 한계']))
    print(json.dumps(results, ensure_ascii=False))


if __name__ == '__main__':
    main()
