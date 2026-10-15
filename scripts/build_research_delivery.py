"""감사된 연구 결과·고정 모델·새 지점 재현 자료를 비공개 인계 폴더에 묶는다."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import shutil
import subprocess
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.research_delivery import file_sha, verify_cohort, verify_delivery
from scripts.fresh_station_validation import PRIVATE, SOURCE, DEFAULT_OUT, verify_seal
from scripts.baseline_ice_logistic import FEATURES


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=PRIVATE / 'research_delivery_20261009_v2')
    args = parser.parse_args(); out = args.output.resolve()
    if not out.is_relative_to(PRIVATE.resolve()):
        parser.error('Local private output required')
    if out.exists():
        raise FileExistsError('Preserve previous delivery')
    fresh = DEFAULT_OUT
    verify_seal(fresh)
    fresh_audit=read(fresh / 'independent_verification.json')
    assert fresh_audit['status'] in {'passed','passed_with_collection_interval_deviation'} and fresh_audit['metrics_reproduced'] is True
    assert read(fresh / 'uncertainty_verification.json')['status'] == 'passed'
    spatial = [PRIVATE / 'segment_exposure_20261009_v1', PRIVATE / 'segment_exposure_second_winter_20261009_v1']
    for folder in spatial:
        assert read(folder / 'independent_verification.json')['status'] == 'passed'
    assert read(PRIVATE / 'score_calibration_20261009_v1/independent_verification.json')['status'] == 'passed'
    raw = pd.read_parquet(PRIVATE / 'ice_group_balanced_20261009_v1/feature_matrix.parquet')
    temp = pd.read_parquet(PRIVATE / 'weather_fallback_20261009_v1/training_index.parquet')
    index = pd.read_parquet(PRIVATE / 'ice_group_balanced_20261009_v1/development_index.parquet')
    pd.testing.assert_frame_equal(index[['station', 'time']], temp[['station', 'time']])
    training = pd.concat([temp[['station', 'time', 'road_temp']], raw[FEATURES]], axis=1)
    plan = read(fresh / 'plan.json')
    verify_cohort(training, pd.read_parquet(fresh / 'predictions.parquet'), plan['station_groups'])
    out.mkdir(parents=True)
    (out / 'training').mkdir()
    training.to_parquet(out / 'training/temperature_first_winter23.parquet', index=False, compression='zstd')

    def copy(source, target):
        destination = out / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    for name in ['weather_hgb23.joblib', 'fit_receipt.json', 'plan.json', 'points.csv', 'point_references.json',
                 'predictions.parquet', 'evaluation.parquet', 'summary.json', 'coverage.json', 'station_metrics.csv',
                 'daily_metrics.csv', 'event_metrics.csv', 'prediction_seal.json', 'prediction_audit.json',
                 'independent_verification.json', 'uncertainty_plan.json', 'temporal_uncertainty.json', 'uncertainty_verification.json', 'analysis_source.py', 'input_signature.json', 'download_manifest.json', 'fresh_validation_review.jpg', 'figure_receipt.json']:
        copy(fresh / name, 'fresh_validation/' + name)
    for source in sorted(fresh.glob('inputs_*.parquet')):
        copy(source, 'fresh_validation/' + source.name)
    for folder in sorted(fresh.glob('collection_run_*')):
        for name in ['receipt.json','request_start_intervals.json','collector_source.py']:
            copy(folder / name, 'fresh_validation/' + folder.name + '/' + name)
    for kind, folder in [('original_ice', 'external_augmentation_nested_v1'), ('original_weather_ridge', 'external_temperature_nested_v1')]:
        copy(SOURCE / folder / 'baseline/model.joblib', 'models/' + kind + '.joblib')
        copy(SOURCE / folder / 'baseline/fit_manifest.json', 'models/' + kind + '_fit.json')
    for folder, label in zip(spatial, ['2024-25', '2025-26']):
        for source in sorted(folder.iterdir()):
            if source.is_file():
                copy(source, 'segments/' + label + '/' + source.name)
    for name in ['segment_exposure_review.jpg', 'segment_review.html', 'route_direction_review.csv', 'summary.json', 'viewer_verification.json']:
        copy(PRIVATE / 'segment_review_20261009_v2' / name, 'review/' + name)
    for folder in ['score_calibration_20261009_v1', 'state_temperature_diagnostics_20261009_v1']:
        for source in sorted((PRIVATE / folder).iterdir()):
            if source.is_file() and source.suffix in {'.json', '.csv'}:
                copy(source, 'diagnostics/' + folder + '/' + source.name)
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode('utf-8').split('\0')
    for name in sorted(set(filter(None, names))):
        source = ROOT / name
        if source.suffix.lower() in {'.py', '.md', '.json', '.yml', '.yaml', '.txt', '.ipynb'} or name == '.gitignore':
            assert not name.startswith('outputs/') and source.name != 'secret.env'
            copy(source, 'code/' + name)
    manual = '''# 비공개 연구 인계물

이 폴더는 참가자 본인의 로컬 검토·연구 재현용입니다. 제공 자료·학습 모델·새 지점 정답을 포함하므로 GitHub 업로드나 제3자 전달용이 아닙니다. 대회 참가 서약과 원천별 이용 조건·종료 후 폐기 조건을 따릅니다. 공식 제출본이나 검증된 위험등급 제품이 아닙니다.

## 확인 순서

1. `code/docs/delivery/RESEARCH_DELIVERY_REVIEW_20261009.md`에서 결과와 미충족 조건을 확인합니다.
2. `review/segment_review.html`을 브라우저로 열어 두 겨울·노선·방향을 선택합니다. 외부 통신이나 인증키가 필요하지 않습니다.
3. `segments/2024-25/`, `segments/2025-26/`의 CSV·GeoPackage·Shapefile과 필드 정의를 함께 읽습니다.
4. 아래 명령으로 파일 해시·첫 겨울 23지점 회귀 재적합·새 8지점 고정 예측·분류 및 온도 지표를 재현합니다.

```powershell
python -m pip install -r code/requirements.txt
$env:OMP_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
python -X utf8 code/scripts/reproduce_research_delivery.py --delivery .
```

`reproduction_receipt.json`은 최초 재현 성공 시에만 추가합니다. 학습 매개변수·임계값을 조정하지 않으며, 이미 열린 8지점 정답의 재계산은 새 독립 평가가 아닙니다. 기존 14지점 분류·Ridge 모델은 저장 모델의 추론을 재현하고, 재학습하지 않습니다.

## 포함 범위와 한계

첫 겨울 23지점의 기상 단독 회귀 학습 표, 새 8지점의 고정 입력·예측·정답, 두 겨울 집계 공간 파일, 진단 결과, 코드·문서·고정 환경·모델을 포함합니다. 보호 3지점과 기존 다음 겨울 9지점 정답·API 인증키·원본 ZIP·요청 원문은 포함하지 않습니다. 원천 정답 수집 감사와 전 구간 GIS 재생성에는 원본 작업 공간의 서명된 자료·캐시가 필요합니다. 이 패키지의 독립 실행은 **고정 입력에서 모델·지표 재현**까지입니다.

500m 통계는 유지 구간의 중앙점 1곳의 시계열이며, 1km 통계는 하위 500m 값의 유지 길이 가중 평균입니다. 1km의 slots와 p05는 가중된 중앙점 수·중앙점 분위수로서 고유 시각 수나 1km 전체의 분위수가 아닙니다. 상대 거리는 공식 이정이 아니며 교량·터널 코드는 시설의 정확한 경계가 아닙니다. 두 겨울 노출 차이를 실제 결빙·사고 증감으로 해석하지 않습니다.
'''
    (out / 'README.md').write_text(manual, 'utf-8')
    files = {p.relative_to(out).as_posix(): file_sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    manifest = dict(scope='private_research_handoff_not_final_competition_submission', created_at_utc=datetime.now(timezone.utc).isoformat(),
                    files=files, frozen_query_rows=138240, training_period='2024-11-01..2025-02-28',
                    network_required_for_replay=False, protected_and_old_future_outcomes_included=False,
                    all_spatial_source_reconstruction_portable=False,
                    collection_interval_compliant=fresh_audit['collection_interval_compliant'])
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf-8')
    verify_delivery(out)
    print('Created private research delivery:', out, 'files:', len(files), flush=True)


if __name__ == '__main__':
    main()
