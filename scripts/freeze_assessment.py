"""개발 근거·입력·모델·평가 코드를 해시로 고정한다. 보호 정답은 읽지 않는다."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive, sha256_file
from src.validation import PROTECTED_STATIONS


def main():
    private = ROOT / 'outputs/private'
    out = private / 'frozen_assessment_v1'
    if (out / 'freeze.json').exists(): raise FileExistsError('Existing methodology freeze must not be replaced')
    if (out / 'assessment_started.json').exists(): raise ValueError('Cannot freeze after opening outcomes')
    archive = competition_archive(ROOT)
    assert json.loads((ROOT / 'config/data_source.json').read_text(encoding='utf-8'))['release'] == '20261007'
    parity = json.loads((private / 'point_sources/parity_verification.json').read_text(encoding='utf-8'))
    assert parity['rows'] == 483768 and parity['feature_count'] == 55 and parity['stations'] == 14
    audit = json.loads((private / 'segment_inference_v1/audit.json').read_text(encoding='utf-8'))
    assert audit['status'] == 'all_segments_verified'
    icard = json.loads((private / 'model_candidates/ice_thermal_v1/model_card.json').read_text(encoding='utf-8'))
    tcard = json.loads((private / 'model_candidates/temperature_v1/model_card.json').read_text(encoding='utf-8'))
    for card in (icard, tcard):
        assert not set(card['training_stations']) & PROTECTED_STATIONS
        assert len(card['training_stations']) == 14 and not card['official_holdout_used']
    paths = list((ROOT / 'src').glob('*.py'))
    paths += [ROOT / 'scripts' / name for name in ['freeze_assessment.py', 'predict_frozen_holdout.py', 'evaluate_frozen_holdout.py', 'baseline_ice_logistic.py', 'audit_ice_weather_history.py', 'train_temperature_candidate.py', 'train_ice_candidate.py']]
    paths += [ROOT / 'config' / name for name in ['data_source.json', 'evaluation.json']]
    paths += [private / 'model_candidates' / model / name for model, names in [('temperature_v1', ['model_card.json', 'weather_ridge.joblib']), ('ice_thermal_v1', ['model_card.json', 'ice_hgb.joblib'])] for name in names]
    paths += list((private / 'point_sources').glob('*'))
    paths += [private / 'sensor_availability/metadata.csv']
    evidence = ['forward_physics/summary.json', 'memory_forward/summary.json', 'dsm_consistent/summary.json', 'height_transfer/summary.json', 'catboost_forward/summary.json', 'temperature_physics/summary.json', 'physical_ice/summary.json']
    paths += [private / name for name in evidence]
    manifest = {'status': 'methodology_frozen_before_protected_outcomes', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'target_stations': sorted(PROTECTED_STATIONS), 'protected_outcomes_opened_at_freeze': False,
                'archive_sha256': sha256_file(archive),
                'evaluation_periods': json.loads((ROOT / 'config/evaluation.json').read_text(encoding='utf-8'))['evaluation_periods'],
                'ice_threshold': icard['default_threshold'],
                'selection_rationale': '개발 14개 지점의 공간·겨울 전이 근거로 기존 41특성 열·수분 HGB 가중치20과 과거 RWIS 1:1 온도 혼합을 고정한다. 이력·DSM·복사·CatBoost 추가는 일관된 개선이 없어 채택하지 않는다.',
                'threshold_rationale': '전체 개발 LOSO 점수의 잠정 지점별 일평균 F1로 전역 임계값을 보정했다. 보정 점수는 독립 성능으로 보고하지 않는다.',
                'target_static_height_policy': 'Provided station elevation; no DSM substitution on protected stations.',
                'segment_policy': 'Temperature and condition exposure only are verified. Ice DSM transfer is exploratory and cannot inherit station assessment accuracy.',
                'evaluation_policy': 'One saved prediction set before outcomes. Complete144-slot days; undefined metrics null. No model, threshold, or feature selection from final outcomes.',
                'files': {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in paths if p.is_file()}}
    out.mkdir(parents=True, exist_ok=True)
    (out / 'freeze.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': manifest['status'], 'files': len(manifest['files']), 'threshold': manifest['ice_threshold']}), flush=True)


if __name__ == '__main__':
    main()
