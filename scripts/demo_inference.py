"""저장 모델을 다시 읽어 한 구간 하루를 실제 추론하고 저장 결과와 대조한다."""
import json
import sys
import time
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.point_inputs import PointInputBuilder
from src.frozen_assessment import verify_freeze


def main():
    started = time.perf_counter()
    print('icy-road-ai | 저장 모델 실제 추론 검증', flush=True)
    frozen = verify_freeze(ROOT)
    print('고정 입력·모델·평가 코드 47개 해시 확인 완료', flush=True)
    private = ROOT / 'outputs/private'
    segments = pd.read_csv(private / 'segment_inference_v1/segment_temperature_summary.csv')
    row = segments.iloc[0]
    print(f'대상: {row.segment_id} / {row.route}', flush=True)
    print('기간: 2025-01-15 00:00–23:50 KST / 10분 간격 144행', flush=True)
    builder = PointInputBuilder.from_root(ROOT)
    point = {'station': row.segment_id, 'route': row.route, 'lat': row.lat, 'lon': row.lon}
    times = pd.date_range('2025-01-15', periods=144, freq='10min')
    features, mapping = builder.build(point, times)
    print(f"과거 참조 RWIS: {mapping['near_source']} / 보호 지점 참조 없음", flush=True)
    card = json.loads((private / 'model_candidates/temperature_v1/model_card.json').read_text(encoding='utf-8'))
    model = joblib.load(private / 'model_candidates/temperature_v1/weather_ridge.joblib')
    ice = joblib.load(private / 'model_candidates/ice_thermal_v1/ice_hgb.joblib')
    icard = json.loads((private / 'model_candidates/ice_thermal_v1/model_card.json').read_text(encoding='utf-8'))
    environment = pd.read_csv(private / 'spatial/environment_features/segment_environment_inventory.csv').set_index('segment_id')
    features['elevation_m'] = environment.loc[row.segment_id, 'dsm_elevation_m']
    with threadpool_limits(limits=2):
        weather = model.predict(features[card['feature_names']])
        predicted = np.where(features.neighbor_road_temp.notna(), .5 * (weather + features.neighbor_road_temp), weather)
        predicted = np.where(features.asos_air_temp.notna(), predicted, np.nan)
        scores = ice.predict_proba(features[icard['feature_names']])[:, 1]
    result = pd.DataFrame({'time': times, 'estimated_road_temp_c': predicted, 'ice_score_dsm_proxy': scores, 'predicted_ice_dsm_proxy': (scores >= frozen['ice_threshold']).astype(int)})
    saved = pd.read_parquet(private / 'segment_inference_v1' / row.segment_id / 'predictions.parquet').set_index('time').loc[times]
    np.testing.assert_allclose(predicted, saved.estimated_road_temp_c, atol=1e-12, rtol=1e-12, equal_nan=True)
    print('144행 온도: 기존 전체 구간 결과와 1e-12 허용오차 내 일치', flush=True)
    for r in result.iloc[::24].itertuples():
        print(f'{r.time:%H:%M}  온도 {r.estimated_road_temp_c:6.2f}°C  탐색적 분류점수 {r.ice_score_dsm_proxy:.4f}', flush=True)
    out = private / 'demo'; out.mkdir(exist_ok=True)
    result.to_csv(out / 'sample_inference.csv', index=False, encoding='utf-8-sig')
    print('CSV 저장: outputs/private/demo/sample_inference.csv', flush=True)
    print('주의: DSM 대체 점수는 결빙확률·검증된 위험등급이 아님', flush=True)
    print('고정 보호 평가: 온도 MAE 0.930°C / 결빙 TP 0, FP 3, FN 64', flush=True)
    print(f'실제 실행 완료: {time.perf_counter()-started:.2f}초', flush=True)


if __name__ == '__main__': main()
