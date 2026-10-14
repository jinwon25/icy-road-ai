"""21개 개봉 지점의 위치와 고정 판정의 지표 민감도, 새4 입력 범위를 검토한다."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.evidence_review import (review_domain, coordinate_review, day_counts, aggregate_days,
                                 fit_feature_envelope, feature_support)
from src.point_inputs import PointInputBuilder
from src.temperature_transfer import WEATHER_FEATURES
from scripts.fresh_station_validation import old_freezes, verify_seal

PRIVATE = ROOT / 'outputs/private'
SOURCE = PRIVATE / 'releases/20261007/outputs/private'
BLIND = PRIVATE / 'temperature_blind_20261010_v1'
FRESH = PRIVATE / 'fresh_station_validation_20261009_v2'
DAILY = PRIVATE / 'daily_primary_transfer_20261009_v1'
DEFAULT = PRIVATE / 'unresolved_review_20261010_v1/analysis'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, data):
    if path.exists():
        raise FileExistsError('Preserve previous review')
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT)
    out = parser.parse_args().output.resolve()
    if not out.is_relative_to(PRIVATE.resolve()) or out.exists():
        raise ValueError('New private output directory required')
    freezes = old_freezes()
    verify_seal(BLIND); verify_seal(FRESH)
    out.mkdir(parents=True)
    # 사후 원인 진단의 계산 범위를 고정한다. 독립 평가·새 후보 등록이 아니다.
    write(out / 'review_plan.json', dict(
        status='post_opening_diagnostic_only', created_at_utc=datetime.now(timezone.utc).isoformat(),
        periods=['2024-11-01', '2025-03-01'], protected_outcomes_used=False,
        train_new_models=False, rescore_models=False, change_predictions=False,
        coordinate_tolerance_m=20, coverage_thresholds=[1, 72, 130, 144],
        undefined_policies=['metricwise_omit', 'undefined_zero', 'joint_defined_only'],
        feature_envelope='training marginal min/max and 1/99 percentiles; not AOA or calibrated confidence',
        coordinate_input_comparison='all four targets; response pair, without outcome-based choice',
        official_metric_confirmed=False))
    signatures = {}

    def track(path, expected=None):
        digest = sha(path)
        if expected is not None and digest != expected:
            raise ValueError('Source signature changed: ' + str(path))
        signatures[str(path.relative_to(ROOT))] = digest
        return path

    track(Path(__file__))
    track(ROOT / 'src/evidence_review.py')
    track(ROOT / 'src/point_inputs.py')
    public_root = out.parent
    public_manifest = public_root / 'source_manifest.json'
    if public_manifest.exists():
        for entry in read(track(public_manifest)):
            track(public_root / entry['path'], entry['sha256'])
    catalog = pd.read_csv(track(SOURCE / 'external/kma_rwis_reference/station_catalog.csv'), dtype={'station': str})
    external_root = SOURCE / 'external/kma_rwis_development_v1'
    manifest = read(track(external_root / 'download_manifest.json'))
    if manifest['protected_observations_requested'] or manifest['reserved_validation_opened']:
        raise ValueError('Development collection scope differs')
    coordinate_frames = []
    for identifier, record in manifest['records'].items():
        if Path(identifier).is_absolute() or '..' in Path(identifier).parts:
            raise ValueError('Unsafe manifest path')
        track(external_root / 'raw' / (identifier + '.txt'), record['raw_sha256'])
        part = pd.read_parquet(track(external_root / 'ten_minute' / (identifier + '.parquet'), record['ten_minute_sha256']))
        if len(part) != record['rows_exact_ten_minute'] or not part.station.astype(str).eq(record['station']).all():
            raise ValueError('Observation manifest differs')
        coordinate_frames.append(part[['station', 'time', 'lat', 'lon']])
    development_coords = review_domain(pd.concat(coordinate_frames, ignore_index=True))
    eight = review_domain(pd.read_parquet(track(FRESH / 'evaluation.parquet')))
    four = review_domain(pd.read_parquet(track(BLIND / 'evaluation.parquet')))
    daily = review_domain(pd.read_parquet(track(DAILY / 'predictions.parquet')))
    track(BLIND / 'independent_verification.json'); track(FRESH / 'independent_verification.json')
    all_coords = pd.concat([development_coords, eight[['station', 'time', 'lat', 'lon']],
                            four[['station', 'time', 'lat', 'lon']]], ignore_index=True)
    coordinate_summary, coordinate_pairs = coordinate_review(all_coords, catalog)
    if len(coordinate_summary) != 21:
        raise ValueError('Expected nine plus eight plus four opened stations')
    coordinate_summary.to_csv(out / 'coordinate_summary.csv', index=False, encoding='utf-8-sig')
    coordinate_pairs.to_csv(out / 'coordinate_pairs.csv', index=False, encoding='utf-8-sig')

    sensitivities, canonical = [], []
    domains = [
        ('development9', daily, ['baseline_prediction', 'daily_primary', 'daily_primary_fp_budget']),
        ('opened8', eight, ['original_ice', 'thermal_moisture']),
        ('opened4', four, ['original_ice', 'thermal_hgb100', 'thermal_hgb300']),
    ]
    for domain, frame, policies in domains:
        for policy in policies:
            days = day_counts(frame, policy)
            days.to_csv(out / f'days_{domain}_{policy}.csv', index=False, encoding='utf-8-sig')
            for coverage in [1, 72, 130, 144]:
                for undefined in ['metricwise_omit', 'undefined_zero', 'joint_defined_only']:
                    row = dict(domain=domain, prediction=policy,
                               **aggregate_days(days, coverage, undefined, sorted(frame.station.unique())))
                    sensitivities.append(row)
                    if coverage == 144 and undefined == 'metricwise_omit':
                        canonical.append(row)
    pd.DataFrame(sensitivities).to_csv(out / 'metric_sensitivity.csv', index=False, encoding='utf-8-sig')

    training = review_domain(pd.read_parquet(track(PRIVATE / 'temperature_loss_20261010_v1/development_inputs.parquet')))
    train_mask = np.isfinite(training.road_temp) & np.isfinite(training.asos_air_temp)
    receipts = read(track(BLIND / 'fit_receipts.json'))
    if set(training.station) & set(four.station) or any(int(train_mask.sum()) != r['training_rows'] for r in receipts):
        raise ValueError('Training domain differs from sealed models')
    envelope = fit_feature_envelope(training.loc[train_mask], WEATHER_FEATURES)
    envelope.to_csv(out / 'training_feature_envelope.csv', encoding='utf-8-sig')
    inputs = pd.concat([pd.read_parquet(track(BLIND / f'inputs_{s}.parquet')) for s in sorted(four.station.unique())], ignore_index=True)
    support, support_detail = feature_support(inputs, envelope)
    support.to_csv(out / 'input_support.csv', index=False, encoding='utf-8-sig')
    support_detail.to_csv(out / 'input_support_detail.csv', index=False, encoding='utf-8-sig')

    # 위치만 바꾼 입력을 별도 재구축한다. 봉인 모델을 다시 추론하거나 평가하지 않는다.
    point_source = SOURCE / 'point_sources'
    aws = pd.read_parquet(track(point_source / 'aws.parquet'))
    asos = pd.read_parquet(track(point_source / 'asos.parquet'))
    rwis = pd.read_parquet(track(point_source / 'rwis.parquet'))
    metadata = pd.read_csv(track(SOURCE / 'sensor_availability/metadata.csv'), dtype={'station': str})
    cutoff = pd.Timestamp('2025-03-01')
    builder = PointInputBuilder(aws.loc[aws.source_time.lt(cutoff)], asos.loc[asos.source_time.lt(cutoff)],
                               rwis.loc[rwis.time.lt(cutoff)],
                               pd.read_csv(track(point_source / 'weather_coordinates.csv'), dtype={'station_id': str}),
                               metadata.loc[metadata.kind.eq('RWIS'), ['station', 'route', 'lat', 'lon']])
    points = pd.read_csv(track(BLIND / 'points.csv'), dtype={'station': str}).set_index('station')
    refs = {r['station']: r['references'] for r in read(track(BLIND / 'point_references.json'))}
    changes, reference_changes = [], []
    for station, original in inputs.groupby('station', sort=True):
        pairs = coordinate_pairs.loc[coordinate_pairs.station.eq(station)]
        if len(pairs) != 1:
            raise ValueError('Location diagnostic requires a unique observed coordinate pair')
        point = points.loc[station].to_dict(); point['station'] = station
        point['lat'] = float(pairs.iloc[0].response_lat); point['lon'] = float(pairs.iloc[0].response_lon)
        alternate, new_refs = builder.build(point, original.time)
        original = original.sort_values('time').reset_index(drop=True)
        if not original.time.equals(alternate.time):
            raise ValueError('Location input time alignment differs')
        for feature in WEATHER_FEATURES:
            left = original[feature].to_numpy(dtype=float); right = alternate[feature].to_numpy(dtype=float)
            finite = np.isfinite(left) & np.isfinite(right)
            delta = np.abs(left[finite] - right[finite])
            changes.append(dict(station=station, feature=feature, compared_finite_rows=int(finite.sum()),
                                missing_mask_changed_rows=int((np.isnan(left) != np.isnan(right)).sum()),
                                changed_finite_rows=int((delta > 1e-12).sum()),
                                maximum_absolute_change=float(delta.max()) if len(delta) else None))
        for key in ['aws_candidates', 'asos_station', 'near_source', 'moisture_source']:
            before, after = refs[station][key], new_refs[key]
            before_ids = [r['station'] for r in before] if key == 'aws_candidates' else before
            after_ids = [r['station'] for r in after] if key == 'aws_candidates' else after
            reference_changes.append(dict(station=station, reference=key, before=before_ids,
                                          after=after_ids, station_selection_changed=before_ids != after_ids))
    pd.DataFrame(changes).to_csv(out / 'coordinate_input_changes.csv', index=False, encoding='utf-8-sig')
    write(out / 'coordinate_reference_changes.json', reference_changes)

    # 개봉 결과에서의 온도/상태 불일치와 놓친 사건을 고정 정책 그대로 집계한다.
    bins = pd.cut(four.road_temp, [-np.inf, -2, 0, 2, np.inf], labels=['<=-2', '(-2,0]', '(0,2]', '>2'])
    failure_rows = []
    for station, part in four.groupby('station'):
        for label in ['<=-2', '(-2,0]', '(0,2]', '>2', 'missing']:
            mask = part.ice.eq(1) & (bins.loc[part.index].eq(label) if label != 'missing' else part.road_temp.isna())
            subset = part.loc[mask]
            failure_rows.append(dict(station=station, measured_temperature_bin=label, ice_rows=len(subset),
                                     original_hits=int(subset.original_ice.sum()),
                                     thermal100_hits=int(subset.thermal_hgb100.sum()),
                                     thermal300_hits=int(subset.thermal_hgb300.sum())))
    pd.DataFrame(failure_rows).to_csv(out / 'ice_temperature_failure.csv', index=False, encoding='utf-8-sig')
    bias_rows = []
    for station, part in four.groupby('station'):
        for prediction in ['weather_hgb100', 'weather_hgb300']:
            valid = np.isfinite(part.road_temp) & np.isfinite(part[prediction])
            errors = (part.loc[valid, prediction] - part.loc[valid, 'road_temp']).to_numpy()
            bias_rows.append(dict(station=station, model=prediction, n=len(errors), bias=float(errors.mean()),
                                  residual_p10=float(np.quantile(errors, .1)), residual_p90=float(np.quantile(errors, .9))))
    pd.DataFrame(bias_rows).to_csv(out / 'temperature_bias.csv', index=False, encoding='utf-8-sig')

    for rel, digest in signatures.items():
        if sha(ROOT / rel) != digest:
            raise ValueError('Read-only source changed during review')
    if old_freezes() != freezes:
        raise ValueError('Original freeze population differs')
    verify_seal(BLIND); verify_seal(FRESH)
    write(out / 'input_signatures.json', signatures)
    summary = dict(status='post_opening_review_completed', completed_at_utc=datetime.now(timezone.utc).isoformat(),
                   original_frozen_files=freezes[0], reserved_frozen_files=freezes[1], input_files_verified=len(signatures),
                   coordinate_stations=len(coordinate_summary), coordinate_rows=len(all_coords),
                   discrepancy_stations=coordinate_summary.loc[coordinate_summary.status.eq('catalogue_response_discrepancy'), 'station'].tolist(),
                   metric_sensitivity_rows=len(sensitivities), canonical_complete_day_rows=canonical,
                   model_predictions_changed=False, new_models_fit=0, official_metric_confirmed=False,
                   files={p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()})
    write(out / 'summary.json', summary)
    print(json.dumps({k: summary[k] for k in ['status', 'coordinate_stations', 'discrepancy_stations',
                                            'metric_sensitivity_rows', 'input_files_verified', 'new_models_fit']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
