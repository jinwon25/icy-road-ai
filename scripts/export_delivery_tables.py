"""보존 후보에서 CSV·열 사전·검증 영수증을 생성한다. 새 경로만 허용한다."""
import argparse
from datetime import datetime, timezone
import gzip
import io
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.delivery_tables import classification_tables, temperature_table, daily_prediction_table, segment_correlations, two_winter_tables
from src.method_blending import domain
from src.validation import PROTECTED_STATIONS
from src.data_source import sha256_file as sha


def read(path):
    return json.loads(path.read_text('utf-8'))


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base, out = args.candidate.resolve(), args.output.resolve()
    if base == out or base in out.parents or out in base.parents:
        raise ValueError('Separate immutable candidate and new output directory required')
    if out.exists():
        raise FileExistsError('Preserve existing output; choose a new path')
    # 입력은 후보 manifest의 허용 목록으로만 제한하고 읽은 파일마다 검증한다.
    base_manifest = read(base/'manifest.json')
    manifest = base_manifest['files']
    expanded = base_manifest.get('development_scope') == 'two_winter'
    sources, inventory = {}, []
    out.mkdir(parents=True)

    def source(name):
        path = base/name
        if name not in manifest or sha(path) != manifest[name]['sha256']:
            raise ValueError('Candidate source hash mismatch: '+name)
        sources[name] = manifest[name]
        return path

    def table(name, frame, keys, purpose):
        if keys and (frame[keys].isna().any().any() or frame.duplicated(keys).any()):
            raise ValueError('Missing or duplicate output key: '+name)
        numeric = frame.select_dtypes(include='number')
        if np.isinf(numeric.to_numpy(dtype=float)).any():
            raise ValueError('Infinite CSV value: '+name)
        path = out/(name+'.csv')
        frame.to_csv(path, index=False, encoding='utf-8-sig', na_rep='NA', float_format='%.17g',
                     date_format='%Y-%m-%dT%H:%M:%S')
        # 형식 재독해로 행·열·결측·식별자·유효 숫자를 검사한다.
        identifiers = {c: str for c in ['station', 'seg_id', 'id', 'prediction_group'] if c in frame}
        restored = pd.read_csv(path, dtype=identifiers, keep_default_na=False,
                               na_values=['NA'], float_precision='round_trip')
        if restored.shape != frame.shape or list(restored) != list(frame):
            raise ValueError('CSV shape mismatch: '+name)
        for c in frame:
            if not np.array_equal(frame[c].isna(), restored[c].isna()):
                raise ValueError('CSV null mask mismatch: '+name+'/'+c)
            if c in identifiers and not np.array_equal(frame[c].astype(str).to_numpy(), restored[c].to_numpy()):
                raise ValueError('CSV identifier mismatch: '+name+'/'+c)
        for c in numeric:
            np.testing.assert_array_equal(frame[c].to_numpy(float), restored[c].to_numpy(float))
        inventory.append(dict(file=path.name, rows=len(frame), keys=keys, purpose=purpose,
            sha256=sha(path), bytes=path.stat().st_size,
            columns=[dict(name=c, dtype=str(frame[c].dtype), missing_rows=int(frame[c].isna().sum())) for c in frame]))

    protected = pd.read_csv(source('data/protected_predictions_10min.csv.gz'), dtype={'station': str}, parse_dates=['time'], float_precision='round_trip')
    if set(protected.station) != set(PROTECTED_STATIONS) or len(protected) != 103680:
        raise ValueError('Unexpected protected prediction population')
    forbidden = {'ice', 'road_temp', 'state_raw', 'observed_ice', 'actual_ice'}
    if forbidden & set(protected):
        raise ValueError('Protected outcomes forbidden')
    table('protected_predictions_10min', protected, ['station', 'time'], '보호 3곳·두 겨울의 10분 추정. 관측 정답 없음')
    gaps = protected.loc[protected.estimated_road_temp_c.isna() | protected.predicted_ice.isna()].copy()
    table('protected_missing_inputs', gaps, ['station', 'time'], '입력 부족 행과 사유. 결측은 음성으로 바꾸지 않음')

    summary = pd.read_csv(source('data/segment_candidate_summary.csv'), dtype={'seg_id': str, 'prediction_group': str}, float_precision='round_trip')
    table('segment_estimates', summary, ['scale_m', 'winter', 'seg_id'], '500m·1km 구간의 겨울별 추정과 환경인자')
    index = pd.read_csv(source('data/point_prediction_index.csv'), dtype={'id': str, 'prediction_group': str}, float_precision='round_trip')
    table('point_prediction_index', index, ['kind', 'scale_m', 'id', 'winter'], '지점/구간과 10분 예측 그룹 연결. 기본 후보 data/prediction_groups와 결합')
    group_parts = []
    group_files = read(source('data/prediction_group_manifest.json'))
    group_csv = out/'prediction_groups_10min.csv.gz'
    group_rows = 0
    group_missing = None
    for group, entry in sorted(group_files.items()):
        predictions = pd.read_parquet(source('data/prediction_groups/'+group+'.parquet'))
        if set(predictions.station) != {group} or len(predictions) != entry['rows']:
            raise ValueError('Group identity mismatch')
        expected = pd.date_range(f"{entry['winter']}-11-01", periods=17280, freq='10min')
        if not pd.DatetimeIndex(predictions.time).equals(expected):
            raise ValueError('Group calendar mismatch')
        for point in index.loc[index.kind.eq('protected') & index.prediction_group.eq(group)].itertuples():
            selected = protected.loc[protected.station.eq(point.id) & protected.winter.eq(point.winter)].copy()
            selected['station'] = group
            pd.testing.assert_frame_equal(selected[predictions.columns].reset_index(drop=True),
                                          predictions.reset_index(drop=True), check_dtype=False, check_exact=True)
        flat = predictions.rename(columns={'station': 'prediction_group'}).copy()
        flat.insert(1, 'winter', int(entry['winter']))
        text = flat.to_csv(index=False, na_rep='NA', float_format='%.17g', date_format='%Y-%m-%dT%H:%M:%S')
        reread = pd.read_csv(io.StringIO(text), dtype={'prediction_group': str},
            keep_default_na=False, na_values=['NA'], float_precision='round_trip', parse_dates=['time'])
        pd.testing.assert_frame_equal(flat, reread, check_dtype=False, check_exact=True)
        # 매 그룹은 별도 gzip 멤버로 이어 쓴다. 표준 gzip/pandas에서 하나의 CSV로 읽힌다.
        with gzip.open(group_csv, 'at', encoding='utf-8-sig' if group_rows == 0 else 'utf-8', newline='') as stream:
            flat.to_csv(stream, index=False, header=group_rows == 0, na_rep='NA', float_format='%.17g',
                        date_format='%Y-%m-%dT%H:%M:%S')
        group_rows += len(flat)
        counts = flat.isna().sum()
        group_missing = counts if group_missing is None else group_missing+counts
        daily = daily_prediction_table(predictions)
        daily.insert(0, 'prediction_group', group)
        daily.insert(1, 'winter', int(entry['winter']))
        group_parts.append(daily)
    group_days = pd.concat(group_parts, ignore_index=True)
    decoded_rows = sum(len(c) for c in pd.read_csv(group_csv, chunksize=17280, usecols=['prediction_group']))
    if decoded_rows != group_rows:
        raise ValueError('Compressed group CSV row count mismatch')
    inventory.append(dict(file=group_csv.name, rows=group_rows, keys=['prediction_group','time'],
        purpose='공유 기상 그룹별 두 겨울 10분 예측. 위치 인덱스로 전체 구간·보호 지점 복원',
        sha256=sha(group_csv), bytes=group_csv.stat().st_size,
        columns=[dict(name=c, dtype=str(flat[c].dtype), missing_rows=int(group_missing[c])) for c in flat]))
    table('prediction_group_daily', group_days, ['prediction_group', 'date_kst'], '공유 기상 그룹의 일별 예측·결측 분모. 독립 관측 수가 아님')
    if not set(index.prediction_group) <= set(group_files):
        raise ValueError('Unresolved prediction index')
    totals = group_days.groupby('prediction_group')[['ice_valid_slots','cold_wet_slots','temperature_valid_slots']].sum()
    merged = summary.merge(totals, left_on='prediction_group', right_index=True, suffixes=('', '_daily'), validate='many_to_one')
    for c in ['ice_valid_slots','cold_wet_slots','temperature_valid_slots']:
        np.testing.assert_array_equal(merged[c], merged[c+'_daily'])
    table('segment_environment_correlations', segment_correlations(summary),
          ['scale_m','winter','predictor','target','method'], '구간 속성과 모델 추정값의 기술적 상관. 독립성·인과·관측 Ice와의 관련성 미검증')

    if expanded:
        frame = pd.read_parquet(source('research/two_winter/audited_predictions.parquet'))
        days,stations,scores,temperatures = two_winter_tables(frame)
        audit = read(source('research/two_winter/audit.json'))
        actual = scores.loc[scores.method.eq('current') & scores.min_valid_slots.eq(144)].iloc[0]
        np.testing.assert_allclose(actual.f1_fixed_population,audit['physical']['both']['all']['f1_fixed_population'],rtol=0,atol=1e-12)
    else:
        baseline = read(source('research/baselines/summary.json'))
        fixed = domain(pd.read_parquet(source('research/baselines/fixed_comparator_predictions.parquet')))
        days, stations, scores = classification_tables(fixed, list(baseline['reports']), baseline['population'])
        for row in scores.to_dict('records'):
            old = baseline['reports'][row['method']]['coverage'][str(row['min_valid_slots'])]
            for key in ['precision_available_station_mean', 'recall_available_station_mean', 'f1_available_station_mean']:
                if old[key] is None:
                    assert pd.isna(row[key])
                else:
                    np.testing.assert_allclose(row[key], old[key], atol=1e-12, rtol=0)
        temperature = pd.read_parquet(source('data/development_temperature_oof.parquet'))
        temperatures = temperature_table(temperature)
    table('development_ice_daily', days, ['method','min_valid_slots','station','date_kst'], '허용 개발 9곳의 일별 TP/FP/FN/TN과 지표별 포함 여부')
    table('development_ice_stations', stations, ['method','min_valid_slots','station'], '일평균에서 계산한 지점별 지표. 지표별 날짜 수 유지')
    table('development_ice_summary', scores, ['method','min_valid_slots'], '여섯 방법·네 관측량 조건의 개발 지표. 공식 점수 아님')
    table('development_temperature_stations', temperatures, ['station'], '공간 제외 개발 예측의 BIAS/MAE/RMSE. BIAS=추정-실측')

    receipt = dict(status='delivery_tables_verified', created_at_utc=datetime.now(timezone.utc).isoformat(),
        candidate_manifest_sha256=sha(base/'manifest.json'), sources=sources, tables=inventory,
        csv_encoding='UTF-8 BOM', delimiter=',', missing_value='NA', timezone='Asia/Seoul',
        timestamps='ISO 8601 without offset; all values are KST', official_template=False,
        development_scope='two_winter' if expanded else 'first_winter',
        protected_missing_rows=len(gaps), unique_prediction_groups=len(group_files),
        represented_segment_rows=len(summary), csv_numeric_roundtrip_exact=True,
        protected_predictions_equal_group_reconstruction=True,
        generator_sha256=sha(Path(__file__)), aggregation_module_sha256=sha(ROOT/'src/delivery_tables.py'),
        daily_to_winter_counts_equal=True, new_model_fits=0, model_promoted=False,
        protected_outcomes_read=False, competition_submitted=False)
    write(out/'manifest.json', receipt)
    print(json.dumps({k: receipt[k] for k in ['status','protected_missing_rows','unique_prediction_groups','represented_segment_rows']}, ensure_ascii=False))
    print('CSV tables:', {t['file']:t['rows'] for t in inventory})


if __name__ == '__main__':
    main()
