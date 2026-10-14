"""외부 접속을 차단한 상태에서 개발 후보의 하루 추론을 저장 예측과 대조한다."""
import json
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.joint_surface import FEATURES, WEATHER
from src.method_blending import domain
from src.offline_runtime import deny_network
from scripts.fresh_station_validation import old_freezes, verify_seal

PRIVATE = ROOT / 'outputs/private'
OUT = PRIVATE / 'offline_inference_20261013_v1'
PLAN = dict(station='12207', group='seohaean_seocheon', date_kst='2024-12-15', rows=144,
            temperature_components=['weather12_no_distance', 'weather_mse300', 'weather_mae300'],
            temperature_blend='equal_distance_mse_mae300', classifier='catboost400', classifier_role='미채택 연구 후보의 점수 재현',
            inference='기존 캐시·로컬 저장 모델만 사용. 외부 API 분석/예측 서비스·새 관측 다운로드·새 학습 없음.',
            score_semantics='CatBoost의 가중 점수는 보정된 Ice 확률·최종 위험 등급 아님.',
            boundary='온도 범위는 경험적 진단이며90% 포함 보장·결빙 판정·안전 판정 아님.',
            independent_assessment=False, protected_or_assessment_outcomes_read=False, final_model_promoted=False)


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


def main():
    if OUT.exists():
        raise FileExistsError('Preserve previous offline verification')
    freeze = old_freezes()
    for name in ['fresh_station_validation_20261009_v2', 'temperature_blind_20261010_v1', 'temperature_mean_blind_20261010_v1']:
        verify_seal(PRIVATE / name)
    OUT.mkdir(); signatures = {}
    def pin(path):
        signatures[str(path.relative_to(ROOT))] = sha(path)
    for path in [Path(__file__), ROOT / 'src/offline_runtime.py']:
        pin(path)
    shutil.copy2(Path(__file__), OUT / 'analysis_source.py')
    write = lambda name, value: (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    write('experiment_plan.json', PLAN)
    temp_source = PRIVATE / 'temperature_pair_blending_20261010_v1'; classifier_source = PRIVATE / 'ice_methodology_20261010_v1'; intervals_source = PRIVATE / 'temperature_uncertainty_20261010_v1'
    for folder, expected in [(temp_source, 'independent_fixed_pairs_audit_passed'), (classifier_source, 'independent_ice_methodology_audit_passed'), (intervals_source, 'independent_temperature_range_audit_passed')]:
        for name in ['summary.json', 'independent_verification.json']:
            pin(folder / name)
        audit = read(folder / 'independent_verification.json')
        if audit['status'] != expected or audit['summary_sha256'] != sha(folder / 'summary.json'):
            raise ValueError('Audited source required')
    source = PRIVATE / 'method_blending_20261010_v2'; receipt_path = source / 'reused_model_receipts.json'; pin(receipt_path)
    receipts = read(receipt_path)
    weather_path = PRIVATE / 'weather_distance_20261010_v1/development_inputs.parquet'; pin(weather_path)
    features_path = classifier_source / 'contexts/seohaean_seocheon/query_inputs.parquet'; pin(features_path)
    temperature_path = temp_source / 'seohaean_seocheon/outer_predictions.parquet'; pin(temperature_path)
    scores_path = classifier_source / 'contexts/seohaean_seocheon/query_predictions.parquet'; pin(scores_path)
    interval_path = intervals_source / 'intervals.parquet'; pin(interval_path)
    models, matrix, predicted = {}, {}, {}
    # 순수 추론뿐 아니라 캐시 읽기·모델 역직렬화부터 접속 차단을 유지한다.
    with deny_network() as attempts, threadpool_limits(limits=2):
        raw = domain(pd.read_parquet(weather_path, columns=['station', 'time', 'group', *WEATHER]))
        start = pd.Timestamp(PLAN['date_kst']); end = start+pd.Timedelta(days=1)
        keep = lambda f: f.station.eq(PLAN['station']) & f.time.ge(start) & f.time.lt(end)
        weather = raw.loc[keep(raw)].sort_values('time').reset_index(drop=True)
        if len(weather) != 144 or not weather.time.equals(pd.Series(pd.date_range(start, periods=144, freq='10min'))):
            raise ValueError('Complete fixed development day required')
        for candidate in PLAN['temperature_components']:
            receipt = next(r for r in receipts if r['candidate'] == candidate and set(r['forbidden_stations']) == {'12207', '12408'})
            model_path = (ROOT / receipt['model_path']).resolve(); pin(model_path)
            if sha(model_path) != receipt['model_sha256'] or PLAN['station'] in receipt['training_stations']:
                raise ValueError('Excluded model signature changed')
            model = joblib.load(model_path); models[candidate] = model
            matrix[candidate] = weather[list(model.feature_names_in_)]
            predicted[candidate] = np.where(weather.asos_air_temp.notna(), model.predict(matrix[candidate]), np.nan)
        mean = sum(predicted[c]/3 for c in PLAN['temperature_components'])
        cx = pd.read_parquet(features_path, columns=['station', 'time', *FEATURES]); cx = cx.loc[keep(cx)].sort_values('time').reset_index(drop=True)
        pd.testing.assert_frame_equal(weather[['station', 'time']], cx[['station', 'time']])
        cat_path = classifier_source / 'contexts/seohaean_seocheon/catboost400.joblib'; pin(cat_path)
        cat_receipt_path = classifier_source / 'fit_receipts.json'; pin(cat_receipt_path)
        cat_receipt = next(r for r in read(cat_receipt_path) if r['candidate'] == 'catboost400' and r['context_groups'] == ['seohaean_seocheon'])
        assert sha(cat_path) == cat_receipt['model_sha256'] and PLAN['station'] not in cat_receipt['training_stations']
        cat = joblib.load(cat_path); score = cat.predict_proba(cx[FEATURES])[:, list(cat.classes_).index(1)]
        reference = pd.read_parquet(temperature_path, columns=['station', 'time', *PLAN['temperature_components'], PLAN['temperature_blend']]); reference = reference.loc[keep(reference)].sort_values('time').reset_index(drop=True)
        for candidate in PLAN['temperature_components']:
            np.testing.assert_allclose(predicted[candidate], reference[candidate], atol=1e-10, rtol=0, equal_nan=True)
        np.testing.assert_allclose(mean, reference[PLAN['temperature_blend']], atol=1e-10, rtol=0, equal_nan=True)
        scores = pd.read_parquet(scores_path, columns=['station', 'time', 'catboost400_score', 'fallback']); scores = scores.loc[keep(scores)].sort_values('time').reset_index(drop=True)
        assert not scores.fallback.any()
        np.testing.assert_allclose(score, scores.catboost400_score, atol=1e-12, rtol=0)
        calibration_path = intervals_source / 'calibrations.json'; pin(calibration_path)
        radius = read(calibration_path)[PLAN['group']][PLAN['temperature_blend']]['radius']; lower, upper = mean-radius, mean+radius
        reference_interval = pd.read_parquet(interval_path, columns=['station', 'time', PLAN['temperature_blend']+'_lower', PLAN['temperature_blend']+'_upper']); reference_interval = reference_interval.loc[keep(reference_interval)].sort_values('time').reset_index(drop=True)
        np.testing.assert_allclose(lower, reference_interval[PLAN['temperature_blend']+'_lower'], atol=1e-10, rtol=0, equal_nan=True)
        np.testing.assert_allclose(upper, reference_interval[PLAN['temperature_blend']+'_upper'], atol=1e-10, rtol=0, equal_nan=True)
    if attempts:
        raise RuntimeError('Network attempt was observed; offline proof failed')
    result = weather[['station', 'time']].copy()
    result['estimated_road_temp_c'], result['empirical_lower_c'], result['empirical_upper_c'], result['uncalibrated_catboost_score'] = mean, lower, upper, score
    result.to_parquet(OUT / 'development_day_inference.parquet', index=False, compression='zstd')
    write('input_signatures.json', signatures)
    assert old_freezes() == freeze
    for name in ['fresh_station_validation_20261009_v2', 'temperature_blind_20261010_v1', 'temperature_mean_blind_20261010_v1']:
        verify_seal(PRIVATE / name)
    receipt = PLAN | dict(status='offline_inference_replay_passed', checked_at_utc=datetime.now(timezone.utc).isoformat(), network_attempts=0, external_prediction_api_calls=0,
                          verified_prediction_values=144*7, local_models_loaded=4, new_model_fits=0, input_signatures=signatures, result_sha256=sha(OUT / 'development_day_inference.parquet'),
                          old_frozen_files=freeze[0], reserved_frozen_files=freeze[1])
    write('verification_receipt.json', receipt)
    print(json.dumps({k: receipt[k] for k in ['status', 'rows', 'network_attempts', 'local_models_loaded', 'verified_prediction_values', 'new_model_fits', 'old_frozen_files', 'reserved_frozen_files']}))


if __name__ == '__main__':
    main()
