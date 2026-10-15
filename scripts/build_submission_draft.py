"""공식 제출 구조의 비공개 검토 초안을 새 폴더에 만든다. 외부로 전송하지 않는다."""
import argparse
import json
import os
import platform
import shutil
import sys
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive, sha256_file
from src.frozen_assessment import verify_freeze

PRIVATE_REFERENCE_PREFIXES = (
    'external/uos_chainage_reference', 'external/official_cctv_anchors',
    'spatial/chainage_reference', 'spatial/official_chainage_anchors',
)


def private_reference(path, private):
    relative = path.relative_to(private).as_posix()
    return any(relative == prefix or relative.startswith(prefix + '/')
               for prefix in PRIVATE_REFERENCE_PREFIXES)


def main():
    verify_freeze(ROOT)
    private = ROOT / 'outputs/private'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=private / 'submission_draft_v1')
    args = parser.parse_args()
    out = args.output.resolve()
    if out.parent != private.resolve() or not out.name.startswith('submission_'):
        raise ValueError('New submission draft must be a named child of outputs/private')
    if out.exists(): raise FileExistsError('Existing submission draft is preserved; use a new version for revisions')
    confirmation_path = private / 'participant_confirmation_20261009.json'
    confirmation = json.loads(confirmation_path.read_text(encoding='utf-8')) if confirmation_path.exists() else {}
    participant_confirmed = (confirmation.get('personal_project_owner_confirmed') is True
                             and bool(confirmation.get('confirmed_actions')) and confirmation.get('ai_support_retained') is True)
    archive = competition_archive(ROOT)
    sources = []
    for directory in ('src', 'scripts', 'config', 'tests', 'notebooks', 'docs', '.github'):
        sources.extend(p for p in (ROOT / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    for name in ('README.md', 'AI_USAGE.md', 'requirements.txt', 'workspace_manifest.json', 'artifact_manifest.json', 'invalidated_artifacts.json'):
        sources.append(ROOT / name)
    sources.append(archive)
    for child in private.iterdir():
        if child.name.startswith(('submission_', 'package_', 'invalid_route_', 'smoke_')): continue
        if child.is_dir():
            sources.extend(p for p in child.rglob('*') if p.is_file() and not private_reference(p, private))
        elif not private_reference(child, private):
            sources.append(child)
    expected = sum(p.stat().st_size for p in sources)
    if shutil.disk_usage(ROOT).free < expected * 1.2: raise RuntimeError('Insufficient draft workspace capacity')
    out.mkdir()
    for i, source in enumerate(sources, 1):
        destination = out / source.relative_to(ROOT); destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if i % 1000 == 0: print(f'Copied {i}/{len(sources)}', flush=True)
    # 심사자가 찾기 쉬운 제출 항목별 사본. 실행 경로는 원래 outputs/private 구조를 보존한다.
    for name in ('data', 'model', 'figures', 'demo'): (out / name).mkdir()
    shutil.copytree(private / 'model_candidates', out / 'model', dirs_exist_ok=True)
    shutil.copytree(private / 'demo', out / 'demo', dirs_exist_ok=True)
    for source in (private / 'segment_condition_proposal').iterdir():
        if source.suffix.lower() in ('.jpg', '.png', '.shp', '.shx', '.dbf', '.prj', '.cpg', '.gpkg'): shutil.copy2(source, out / 'figures' / source.name)
    for relative in ['segment_condition_proposal/segment_estimates_and_environment.csv', 'segment_ice_exploratory/segment_ice_summary.csv', 'frozen_assessment_v1/daily_scores.csv', 'frozen_assessment_v1/summary.json']:
        shutil.copy2(private / relative, out / 'data' / Path(relative).name)
    conditions=pd.read_csv(out/'data/segment_estimates_and_environment.csv')
    exploratory=pd.read_csv(out/'data/segment_ice_summary.csv')[['segment_id','score_mean','score_max','predicted_ice_slots','height_proxy_m','threshold']]
    combined=conditions.merge(exploratory,on='segment_id',validate='one_to_one')
    combined['ice_output_status']='exploratory_DSM_transfer_failed_classifier'
    combined.to_csv(out/'data/segment_estimates_combined.csv',index=False,encoding='utf-8-sig')
    links = {'raw_archive': archive.name, 'ten_minute_temperature': 'outputs/private/segment_inference_v1/<segment_id>/temperature_10min.csv.gz',
             'ten_minute_exploratory_ice': 'outputs/private/segment_ice_exploratory/<segment_id>/ice_10min_exploratory.csv.gz',
             'protected_predictions': 'outputs/private/frozen_assessment_v1/predictions.csv.gz',
             'external_data_and_notices': 'outputs/private/external/', 'frozen_methods': 'outputs/private/frozen_assessment_v1/freeze.json'}
    (out / 'data/data_index.json').write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding='utf-8')
    hardware = {'os': platform.platform(), 'python': platform.python_version(), 'cpu': platform.processor(), 'logical_cpus': os.cpu_count(),
                'gpu_used': False, 'cuda_required': False, 'training_thread_limit': 2}
    try:
        import psutil
        hardware['ram_bytes'] = psutil.virtual_memory().total
    except ImportError: pass
    (out / 'environment.json').write_text(json.dumps(hardware, ensure_ascii=False, indent=2), encoding='utf-8')
    preface = '''# 비공개 제출 검토 초안 — icy-road-ai

이 폴더는 자동 제출되지 않은 검토 초안이다. 보호 지점 온도 평균 MAE 0.930°C이지만 결빙 TP0/FP3/FN64, F1=0으로 탐지에 실패했다. 운영 경보·수상권 성능·사고 위험등급으로 주장하지 않는다. 참가자 직접 기여 설명은 확인 전이다.

## 검토 순서

1. `docs/validation/EVALUATION_STATUS.md`: 고정 평가 결과와 위험도 제안의 적용 범위.
2. `data/`: 구간 요약·환경조건·임계값·일별 평가. 전체 10분 CSV 위치는 `data/data_index.json`.
3. `figures/`: 조건 노출의 JPG/PNG·Shapefile 전체 부속 파일·GPKG. 공식 이정·방향은 미확정.
4. `model/`: 온도·분류 저장 모델과 모델 카드. 실제 실행용 같은 모델은 원래 `outputs/private/model_candidates/`에도 있다.
5. `demo/inference_demo.mp4`: 실제 명령 로그 재생과 결과 설명 39초. 화면 녹화가 아니며 실행 원문·시간 기록을 함께 제공한다.
6. `notebooks/analysis_review.ipynb`: 데이터·개발 검증·일회 평가 결과를 순서대로 읽는다. 저장 출력은 비웠다.

## 환경과 빠른 재현

Windows/Python 3.11, CPU 사용·GPU/CUDA 불필요. 실제 하드웨어는 `environment.json`, 라이브러리는 `requirements.txt`에 고정했다. 원본 수정 ZIP은 코드의 고정 경로·해시를 유지하기 위해 패키지 루트에 두었다. `data/`는 결과와 위치 색인이다. `src/`, `scripts/`, `notebooks/`, `model/`, `demo/`, `figures/`를 모두 포함한다.

```powershell
python -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt
.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v
.\\.venv\\Scripts\\python.exe scripts/demo_inference.py
.\\.venv\\Scripts\\python.exe scripts/check_notebook.py
```

학습·추론 전체 순서는 `docs/delivery/RUNBOOK.md`와 `config/notebook_workflow.json`에 있다. 학습 재실행은 별도 복사본에서 수행하고 기존 고정 평가 파일을 덮어쓰지 않는다. 이 패키지에는 이미 평가한 보호 정답이 있으므로 새 모델을 개발한 뒤 같은 지점을 독립 최종 검증이라고 보고할 수 없다. 고정·예측·평가 세 명령은 기존 기록이 있으면 재실행을 차단한다. 모델 출력은 회귀 °C와 보정되지 않은 분류 점수이며 외부 API 인증정보나 상용 LLM 서비스 호출이 필요하지 않다. 외부 원자료와 저작권·이용 고지는 `outputs/private/external/`에 있다.

## 제출 전 남은 확인

- 참가자 본인이 직접 수행한 판단·수정·검증 내용을 AI 활용 기록에 확인·기입해야 한다.
- 공식 이정·상하행 연결, 추가 필수 회귀 변수·CSV 열 규격, 부분 날짜·미정의 지표 처리 조건을 확인해야 한다.
- 구간 결빙 출력은 DSM 대체와 분류 실패가 있는 탐색적 결과다. 조건 노출 지도를 검증된 결빙 위험등급으로 바꾸지 않는다.
- 신청서·개인정보·인증정보·무효화된 과거 구간 출력은 포함하지 않았다. 공개 공유용 묶음이 아니다.

아래는 원본 프로젝트의 방법·실험 안내다. 이 제출 복사본에서는 현재 폴더가 수정본 작업 루트이므로 다시 `outputs/private/releases/20261007`로 이동하지 않는다.

---

'''
    if participant_confirmed:
        preface = preface.replace('참가자 직접 기여 설명은 확인 전이다.', '개인 참가자의 수행 주체와 지시·자료 확보 기여는 확인됐으며 AI 지원을 함께 기록했다. 최종 모델 선택·제출 검토는 미완료다.')
        preface = preface.replace('참가자 본인이 직접 수행한 판단·수정·검증 내용을 AI 활용 기록에 확인·기입해야 한다.',
                                  '확인된 개인 수행 주체·참가자 기여·AI 지원 기록을 검토하고 최종 모델 선택·제출 판단을 보완해야 한다.')
    (out / 'README.md').write_text(preface + (ROOT / 'README.md').read_text(encoding='utf-8'), encoding='utf-8')
    files = {p.relative_to(out).as_posix(): {'bytes': p.stat().st_size, 'sha256': sha256_file(p)} for p in out.rglob('*') if p.is_file()}
    manifest = {'status': 'private_review_draft_not_submitted', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'files': files, 'total_bytes': sum(v['bytes'] for v in files.values()),
                'participant_contribution_confirmed': participant_confirmed,
                'participant_confirmation_sha256': sha256_file(confirmation_path) if confirmation_path.exists() else None,
                'final_model_selection_confirmed': confirmation.get('final_model_selection_confirmed', False),
                'classifier_usable_for_operational_warning': False,
                'excluded': ['invalid_route_*', 'smoke_*', 'application_and_credentials', 'git_history', *PRIVATE_REFERENCE_PREFIXES],
                'source_root': str(ROOT)}
    (out / 'submission_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(out), 'files': len(files), 'bytes': manifest['total_bytes'], 'status': manifest['status']}, ensure_ascii=False), flush=True)


if __name__ == '__main__': main()
