"""별도 날짜 루프로 96개 집계와 좌표·입력 범위를 검산하고 지도 거리도 검토한다."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha

DEFAULT = ROOT / 'outputs/private/unresolved_review_20261010_v1'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def close(a, b):
    if a is None or pd.isna(a):
        if b is not None and not pd.isna(b):
            raise ValueError('Undefined value differs')
    elif b is None or not math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-12):
        raise ValueError(f'Audit mismatch: {a} / {b}')


def independent_days(frame, policy, minimum, handling):
    """기존 집계기를 호출하지 않고 일별 혼동행렬과 지점별 평균을 계산한다."""
    station_values = {str(st): {k: [] for k in ['precision', 'recall', 'f1']} for st in frame.station.unique()}
    counts = dict(planned_days=0, coverage_days=0, active_days=0, both_zero_days=0,
                  excluded_by_joint_days=0, coverage_ice_days=0, excluded_by_coverage_ice_days=0,
                  included_ice_days=0, included_false_alarm_only_days=0)
    for (station, _), day in frame.groupby(['station', frame.time.dt.date]):
        counts['planned_days'] += 1
        valid = day.loc[day.ice.isin([0, 1])]
        actual = int(valid.ice.eq(1).sum()); predicted = int(valid[policy].eq(1).sum())
        if len(valid) < minimum:
            counts['excluded_by_coverage_ice_days'] += int(actual > 0)
            continue
        counts['coverage_days'] += 1; counts['coverage_ice_days'] += int(actual > 0)
        if actual + predicted == 0:
            counts['both_zero_days'] += 1
            continue
        counts['active_days'] += 1
        if handling == 'joint_defined_only' and (actual == 0 or predicted == 0):
            counts['excluded_by_joint_days'] += 1
            continue
        counts['included_ice_days'] += int(actual > 0)
        counts['included_false_alarm_only_days'] += int(actual == 0 and predicted > 0)
        tp = int((valid.ice.eq(1) & valid[policy].eq(1)).sum())
        metrics = dict(precision=tp / predicted if predicted else None,
                       recall=tp / actual if actual else None, f1=2 * tp / (actual + predicted))
        for metric, value in metrics.items():
            if value is None and handling == 'undefined_zero':
                value = 0.
            if value is not None:
                station_values[str(station)][metric].append(value)
    for metric in ['precision', 'recall', 'f1']:
        means = [sum(v[metric]) / len(v[metric]) for v in station_values.values() if v[metric]]
        counts[metric + '_days'] = sum(len(v[metric]) for v in station_values.values())
        counts[metric + '_stations'] = len(means)
        counts[metric + '_available_station_macro'] = sum(means) / len(means) if means else None
        counts[metric + '_fixed_station_zero_undefined'] = sum(means) / len(station_values)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, default=DEFAULT)
    root = parser.parse_args().review.resolve(); analysis = root / 'analysis'
    out = root / 'verification'
    if not root.is_relative_to((ROOT / 'outputs/private').resolve()) or out.exists():
        raise ValueError('New private verification directory required')
    summary = read(analysis / 'summary.json'); signatures = read(analysis / 'input_signatures.json')
    for name, digest in summary['files'].items():
        if sha(analysis / name) != digest:
            raise ValueError('Review output changed')
    checked_inputs = {}

    def verified_read(path):
        rel = str(path.relative_to(ROOT))
        if sha(path) != signatures[rel]:
            raise ValueError('Source changed')
        checked_inputs[rel] = signatures[rel]
        return pd.read_parquet(path)

    domains = {
        'development9': verified_read(ROOT / 'outputs/private/daily_primary_transfer_20261009_v1/predictions.parquet'),
        'opened8': verified_read(ROOT / 'outputs/private/fresh_station_validation_20261009_v2/evaluation.parquet'),
        'opened4': verified_read(ROOT / 'outputs/private/temperature_blind_20261010_v1/evaluation.parquet'),
    }
    sensitivity = pd.read_csv(analysis / 'metric_sensitivity.csv')
    for row in sensitivity.itertuples():
        result = independent_days(domains[row.domain], row.prediction, row.min_valid_slots, row.undefined_policy)
        for key, value in result.items():
            close(getattr(row, key), value)
    coordinate_summary = pd.read_csv(analysis / 'coordinate_summary.csv', dtype={'station': str})
    pairs = pd.read_csv(analysis / 'coordinate_pairs.csv', dtype={'station': str})
    for row in coordinate_summary.itertuples():
        distances = []
        for pair in pairs.loc[pairs.station.eq(row.station)].itertuples():
            lat1, lat2 = map(math.radians, [row.catalog_lat, pair.response_lat])
            dlat = lat2 - lat1; dlon = math.radians(pair.response_lon - row.catalog_lon)
            distance = 6371008.8 * 2 * math.atan2(math.sqrt(math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2),
                                               math.sqrt(1 - (math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)))
            if not math.isclose(distance, pair.distance_m, rel_tol=0, abs_tol=1e-6):
                raise ValueError('Coordinate distance differs')
            distances.append(distance)
        if not math.isclose(max(distances), row.max_distance_m, abs_tol=1e-6):
            raise ValueError('Coordinate maximum differs')
        close(row.coordinate_rows, pairs.loc[pairs.station.eq(row.station), 'rows'].sum())
    envelope = pd.read_csv(analysis / 'training_feature_envelope.csv').set_index('feature')
    training = verified_read(ROOT / 'outputs/private/temperature_loss_20261010_v1/development_inputs.parquet')
    training = training.loc[np.isfinite(training.road_temp) & np.isfinite(training.asos_air_temp)]
    for feature, bounds in envelope.iterrows():
        finite = sorted(float(v) for v in training[feature] if np.isfinite(v))
        close(bounds.training_finite, len(finite)); close(bounds.minimum, finite[0]); close(bounds.maximum, finite[-1])
        close(bounds.q01, np.quantile(finite, .01)); close(bounds.q99, np.quantile(finite, .99))
    detail = pd.read_csv(analysis / 'input_support_detail.csv', dtype={'station': str})
    for station in domains['opened4'].station.unique():
        inputs = verified_read(ROOT / 'outputs/private/temperature_blind_20261010_v1' / f'inputs_{station}.parquet')
        for row in detail.loc[detail.station.eq(station)].itertuples():
            values = inputs[row.feature].to_numpy(dtype=float); bounds = envelope.loc[row.feature]
            close(row.missing_fraction, sum(np.isnan(values)) / len(values))
            close(row.outside_range_fraction, sum(np.isfinite(v) and (v < bounds.minimum or v > bounds.maximum) for v in values) / len(values))

    # 지도는 기존 거리 요약을 검사한다. max만으로 모든 시점의 범위를 보장하지 않는다.
    out.mkdir(parents=True)
    map_rows, map_sources = [], {}
    for winter in ['segment_exposure_20261009_v1', 'segment_exposure_second_winter_20261009_v1']:
        path = ROOT / 'outputs/private' / winter / 'segment_exposure_500m.csv'
        map_sources[str(path.relative_to(ROOT))] = sha(path)
        segments = pd.read_csv(path)
        if len(segments) != 843 or segments.seg_id.duplicated().any():
            raise ValueError('Expected existing 843 unique segments')
        segments['aws_max_above_training_max'] = segments.aws_distance_km_max.gt(envelope.loc['aws_distance_km', 'maximum'])
        segments['aws_max_below_training_min'] = segments.aws_distance_km_max.lt(envelope.loc['aws_distance_km', 'minimum'])
        segments['asos_above_training_max'] = segments.asos_distance_km.gt(envelope.loc['asos_distance_km', 'maximum'])
        segments['asos_below_training_min'] = segments.asos_distance_km.lt(envelope.loc['asos_distance_km', 'minimum'])
        segments['predictive_reliability_verified'] = False
        cols = ['seg_id', 'route_nm', 'flow_lbl', 'len_m', 'aws_distance_km_max', 'asos_distance_km',
                'aws_max_above_training_max', 'aws_max_below_training_min', 'asos_above_training_max',
                'asos_below_training_min', 'official_chainage_verified', 'physical_structure_extent_verified',
                'predictive_reliability_verified']
        segments[cols].to_csv(out / (winter + '_distance_review.csv'), index=False, encoding='utf-8-sig')
        high = segments.aws_max_above_training_max | segments.asos_above_training_max
        low = segments.aws_max_below_training_min | segments.asos_below_training_min
        map_rows.append(dict(winter=winter, segments=len(segments),
                             above_training_max_segments=int(high.sum()),
                             aws_max_below_training_min_segments=int(segments.aws_max_below_training_min.sum()),
                             asos_below_training_min_segments=int(segments.asos_below_training_min.sum()),
                             either_below_training_min_segments=int(low.sum()),
                             directional_length_m=float(segments.len_m.sum()),
                             official_chainage_verified_segments=int(segments.official_chainage_verified.sum()),
                             physical_structure_extent_verified_segments=int(segments.physical_structure_extent_verified.sum())))
    result = dict(status='independent_review_metrics_coordinates_support_passed',
                  audited_at_utc=datetime.now(timezone.utc).isoformat(),
                  metric_rows_verified=len(sensitivity), coordinate_stations_verified=len(coordinate_summary),
                  training_feature_bounds_verified=len(envelope), input_support_rows_verified=len(detail),
                  source_summary_sha256=sha(analysis / 'summary.json'), checked_inputs=checked_inputs,
                  map_sources=map_sources, map_distance_review=map_rows,
                  historical_location_verified=False, official_metric_confirmed=False,
                  map_distance_review_is_performance_validation=False,
                  files={p.name: sha(p) for p in out.iterdir()})
    (out / 'independent_verification.json').write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['status', 'metric_rows_verified', 'coordinate_stations_verified',
                                           'training_feature_bounds_verified', 'input_support_rows_verified']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
