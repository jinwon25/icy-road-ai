"""완료된 모든 구간의 시간·참조·추정식·조건 노출과 저장 해시를 검증한다."""
import json
import sys
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.condition_exposure import cold_moisture_condition
from src.data_source import sha256_file
from src.validation import assert_training_stations


def main():
    private = ROOT / 'outputs/private'
    source = private / 'segment_inference_v1'
    summary = json.loads((source / 'summary.json').read_text(encoding='utf-8'))
    flat = pd.read_csv(source / 'segment_temperature_summary.csv', dtype={'near_source': str})
    card = json.loads((private / 'model_candidates/temperature_v1/model_card.json').read_text(encoding='utf-8'))
    model = joblib.load(private / 'model_candidates/temperature_v1/weather_ridge.joblib')
    assert len(flat) == summary['segments'] == 467 and flat.segment_id.is_unique
    assert flat.near_source.notna().all()
    assert_training_stations(flat.near_source)
    allowed = set(card['training_stations'])
    assert set(flat.near_source) <= allowed
    periods = json.loads((ROOT / 'config/evaluation.json').read_text(encoding='utf-8'))['evaluation_periods']
    expected = pd.DatetimeIndex([])
    for start, end in periods:
        expected = expected.append(pd.date_range(start, pd.Timestamp(end) + pd.Timedelta(hours=23, minutes=50), freq='10min'))
    rows = 0
    with threadpool_limits(limits=2):
        for index, row in enumerate(flat.itertuples(), 1):
            folder = source / row.segment_id
            record = json.loads((folder / 'summary.json').read_text(encoding='utf-8'))
            assert sha256_file(folder / 'features.parquet') == record['feature_sha256']
            assert sha256_file(folder / 'predictions.parquet') == record['predictions_sha256']
            features = pd.read_parquet(folder / 'features.parquet')
            result = pd.read_parquet(folder / 'predictions.parquet')
            assert pd.DatetimeIndex(result.time).equals(expected)
            assert pd.DatetimeIndex(features.time).equals(expected)
            assert result.segment_id.eq(row.segment_id).all()
            assert record['mapping']['near_source'] in allowed
            for key in ('near_source', 'moisture_source'):
                value = record['mapping'][key]
                assert value is None or value in allowed
            for age, limit in [('aws_age_minutes', 60), ('asos_age_minutes', 60), ('near_age_minutes', 30), ('neighbor_age_minutes', 60)]:
                values = features[age].dropna()
                assert values.between(0, limit, inclusive='right').all(), (row.segment_id, age)
            weather = model.predict(features[card['feature_names']])
            blended = np.where(features.neighbor_road_temp.notna(), .5 * (weather + features.neighbor_road_temp), weather)
            blended = np.where(features.asos_air_temp.notna(), blended, np.nan)
            np.testing.assert_allclose(blended, result.estimated_road_temp_c, rtol=1e-12, atol=1e-12, equal_nan=True)
            radius = card['absolute_error_p90_reference_c']
            for key, temperature in [('condition_exposure', blended), ('condition_exposure_low', blended + radius), ('condition_exposure_high', blended - radius)]:
                calculated = cold_moisture_condition(temperature, features.aws_dewpoint, features.rain15_max_24h)
                np.testing.assert_allclose(calculated, result[key], equal_nan=True)
                assert result[key].eq(1).sum() == record['conditions'][key]['exposure_slots']
            # CSV 표현도 첫째·중간·마지막 구간에서 원본 예측과 일치해야 한다.
            if index in (1, 234, 467):
                exported = pd.read_csv(folder / 'temperature_10min.csv.gz', parse_dates=['time'])
                pd.testing.assert_frame_equal(exported, result, check_dtype=False, atol=1e-10, rtol=1e-10)
            rows += len(result)
            if index % 100 == 0: print(f'Audited {index}/467', flush=True)
    assert rows == summary['rows'] == 16139520
    report = {'status': 'all_segments_verified', 'segments': len(flat), 'rows': rows,
              'temperature_available': int(flat.temperature_available.sum()),
              'neighbor_temperature_available': int(flat.neighbor_temperature_available.sum()),
              'weather_only_temperature_slots': int(flat.weather_only_temperature_slots.sum()),
              'reference_stations': sorted(set(flat.near_source)),
              'max_reference_distance_km': float(flat.near_rwis_distance_km.max()),
              'all_prediction_formulas_recomputed': True, 'csv_roundtrip_segments': 3,
              'protected_sources_used': False, 'inference_summary_sha256': sha256_file(source / 'summary.json')}
    (source / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
