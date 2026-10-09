"""모델 고정 후 정적 위치·개발 참조만으로 보호 지점 예측을 먼저 저장한다."""
import json
import sys
import zipfile
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive, sha256_file
from src.observation_io import daily_members, read_columns
from src.validation import PROTECTED_STATIONS, canonical_station_id
from src.point_inputs import PointInputBuilder
from src.frozen_assessment import verify_freeze, protected_point_inputs


def main():
    frozen = verify_freeze(ROOT)
    private = ROOT / 'outputs/private'; out = private / 'frozen_assessment_v1'
    if (out / 'predictions_receipt.json').exists():
        raise FileExistsError('Frozen predictions already saved; verify receipt rather than overwrite')
    columns = ['관측 지점번호', '고속도로', '관측소 위도', '관측소 경도', '관측소 고도 (m)']
    names = ['station', 'route', 'lat', 'lon', 'elevation_m']
    # 정적 열만 읽는다. 이 단계에서는 노면온도·상태 열을 요청하지 않는다.
    with zipfile.ZipFile(competition_archive(ROOT)) as archive:
        parts = [read_columns(archive, member, columns, names) for member in daily_members(archive, 'RWIS')]
    meta = pd.concat(parts, ignore_index=True).drop_duplicates()
    meta['station'] = meta.station.map(canonical_station_id)
    meta = meta.loc[meta.station.isin(PROTECTED_STATIONS)].copy()
    for key in ('lat', 'lon', 'elevation_m'): meta[key] = pd.to_numeric(meta[key], errors='raise')
    meta['route'] = meta.route.str.strip(); meta = meta.drop_duplicates()
    if len(meta) != 3 or not meta.station.is_unique: raise ValueError('Changing or missing protected static metadata')
    meta.to_csv(out / 'static_metadata.csv', index=False, encoding='utf-8-sig')
    builder = PointInputBuilder.from_root(ROOT)
    temperature = joblib.load(private / 'model_candidates/temperature_v1/weather_ridge.joblib')
    ice = joblib.load(private / 'model_candidates/ice_thermal_v1/ice_hgb.joblib')
    tcard = json.loads((private / 'model_candidates/temperature_v1/model_card.json').read_text(encoding='utf-8'))
    icard = json.loads((private / 'model_candidates/ice_thermal_v1/model_card.json').read_text(encoding='utf-8'))
    times = pd.DatetimeIndex([])
    for start, end in frozen['evaluation_periods']:
        times = times.append(pd.date_range(start, pd.Timestamp(end) + pd.Timedelta(hours=23, minutes=50), freq='10min'))
    frames, references = [], []
    with threadpool_limits(limits=2):
        for point in meta.to_dict(orient='records'):
            features, mapping = protected_point_inputs(builder, point, times, frozen)
            weather = temperature.predict(features[tcard['feature_names']])
            estimate = np.where(features.neighbor_road_temp.notna(), .5 * (weather + features.neighbor_road_temp), weather)
            estimate = np.where(features.asos_air_temp.notna(), estimate, np.nan)
            score = ice.predict_proba(features[icard['feature_names']])[:, 1]
            result = features[['station', 'time', 'near_distance_km', 'near_age_minutes', 'neighbor_age_minutes', 'aws_age_minutes', 'asos_age_minutes']].copy()
            result['estimated_road_temp_c'] = estimate
            result['ice_score'] = score
            result['predicted_ice'] = (score >= frozen['ice_threshold']).astype(int)
            frames.append(result); references.append({'target': point['station'], **mapping})
            features.to_parquet(out / f"inputs_{point['station']}.parquet", index=False)
    result = pd.concat(frames, ignore_index=True)
    assert not result.duplicated(['station', 'time']).any() and len(result) == 103680
    result.to_parquet(out / 'predictions.parquet', index=False)
    result.to_csv(out / 'predictions.csv.gz', index=False, encoding='utf-8-sig', compression='gzip')
    receipt = {'status': 'predictions_saved_before_outcomes', 'rows': len(result), 'reference_mapping': references,
               'protected_outcomes_loaded': False, 'threshold': frozen['ice_threshold'],
               'freeze_sha256': sha256_file(out / 'freeze.json'), 'predictions_sha256': sha256_file(out / 'predictions.parquet'),
               'input_sha256': {p.name: sha256_file(p) for p in out.glob('inputs_*.parquet')}}
    (out / 'predictions_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': receipt['status'], 'rows': len(result)}), flush=True)


if __name__ == '__main__':
    main()
