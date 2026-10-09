"""고정 예측을 변경하지 않고 외부 다음 겨울 원문을 감사·한 번 평가한다."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_external_augmentation import json_write, metrics
from src.data_source import sha256_file
from src.external_reserved import verify_reserved_freeze, reserved_request_plan
from src.external_temperature import paired_temperature_metrics
from src.frozen_assessment import verify_freeze
from src.kma_rwis_download import daily_requests, validate_development_request, parse_observations, exact_ten_minute_grid
from src.validation import daily_scores


def classification_report(frame, prefix):
    result = metrics(frame, frame[f'{prefix}_prediction'].to_numpy(), .5)
    gold = frame.ice.notna().to_numpy()
    from sklearn.metrics import average_precision_score
    result['average_precision'] = float(average_precision_score(frame.loc[gold, 'ice'], frame.loc[gold, f'{prefix}_ice_score'])) if gold.any() and frame.loc[gold, 'ice'].sum() else None
    return result


def assess_predictions(predictions, observations):
    if observations.duplicated(['station', 'time']).any():
        raise ValueError('Duplicate reserved outcomes')
    keys = predictions[['station', 'time']]
    membership = observations.merge(keys, on=['station', 'time'], how='left', indicator=True, validate='one_to_one')
    if not membership['_merge'].eq('both').all():
        raise ValueError('Outcomes outside fixed prediction grid')
    combined = predictions.merge(observations[['station', 'time', 'ice', 'state_raw', 'road_temp']],
                                 on=['station', 'time'], how='left', validate='one_to_one')
    results = {}
    for prefix in ('baseline', 'selected'):
        # The choices have group-specific thresholds. The stored binary decisions
        # already passed the frozen-score/threshold check; daily metrics use them.
        results[prefix] = classification_report(combined, prefix)
    base, selected = results['baseline']['slot_micro'], results['selected']['slot_micro']
    assert base['n'] == selected['n'] and base['tp'] + base['fn'] == selected['tp'] + selected['fn']
    daily = daily_scores([(r.station, r.time, int(r.ice) if pd.notna(r.ice) else None, int(r.selected_prediction))
                          for r in combined.itertuples()], minimum_coverage=1.)
    coverage = pd.DataFrame(daily)
    full = set(zip(coverage.loc[coverage.accepted, 'station'], coverage.loc[coverage.accepted, 'date_kst']))
    on_full_day = np.array([(r.station, r.time.date().isoformat()) in full for r in combined.itertuples()])
    subgroup = {}
    for name, mask in [('full_state_days', on_full_day), ('partial_or_unknown_state_days', ~on_full_day)]:
        part = combined.loc[mask]
        subgroup[name] = {'predicted_slots': len(part), 'valid_state_slots': int(part.ice.notna().sum()),
                         'actual_ice_slots': int(part.ice.eq(1).sum()),
                         'temperature': paired_temperature_metrics(part, part.baseline_temperature_c, part.selected_temperature_c)}
    station_temperature = []
    for station, part in combined.groupby('station'):
        station_temperature.append({'station': station, **paired_temperature_metrics(part, part.baseline_temperature_c, part.selected_temperature_c)})
    temperature_macro = {prefix: {metric: float(np.mean([row[key][metric] for row in station_temperature if row[key][metric] is not None]))
                                  if any(row[key][metric] is not None for row in station_temperature) else None
                                  for metric in ('mae', 'rmse', 'bias')}
                         for prefix, key in [('baseline', 'baseline'), ('selected', 'candidate')]}
    report = {'prediction_rows': len(combined), 'observed_exact_ten_minute_rows': len(observations),
              'valid_state_rows': int(combined.ice.notna().sum()), 'actual_ice_rows': int(combined.ice.eq(1).sum()),
              'classification': results, 'both_fp_fn_improved': bool(selected['fp'] < base['fp'] and selected['fn'] < base['fn']),
              'classification_by_group': {group: {prefix: classification_report(part, prefix) for prefix in ('baseline','selected')}
                                          for group, part in combined.groupby('group')},
              'classification_by_station': {station: {prefix: classification_report(part, prefix) for prefix in ('baseline','selected')}
                                            for station, part in combined.groupby('station')},
              'temperature': paired_temperature_metrics(combined, combined.baseline_temperature_c, combined.selected_temperature_c),
              'temperature_station_macro': temperature_macro, 'temperature_by_station': station_temperature,
              'coverage': {'planned_station_days': len(coverage), 'full_valid_state_days': int(coverage.accepted.sum()),
                           'partial_or_unknown_state_days': int((~coverage.accepted).sum())},
              'coverage_subgroups': subgroup,
              'scope': 'External nine-station reserved winter. This is not the official three-station competition score or calibrated operating risk.'}
    return combined, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    private = ROOT / 'outputs/private'; freeze = private / 'external_reserved_predictions_v1'
    source = private / 'external/kma_rwis_reserved_v1'
    if not (freeze / 'predictions_receipt.json').exists() or not (source / 'download_manifest.json').exists():
        if args.prepare_only:
            print(json.dumps({'status': 'awaiting_fixed_predictions_and_reserved_collection', 'outcomes_loaded': False}), flush=True)
            return
        raise ValueError('Frozen predictions and complete reserved acquisition required')
    receipt = verify_reserved_freeze(ROOT, freeze)
    plan = reserved_request_plan(receipt)
    manifest_bytes = (source / 'download_manifest.json').read_bytes(); manifest = json.loads(manifest_bytes)
    expected = {f'{station}/{start:%Y%m%d%H%M}' for station, start, end in daily_requests(
        plan, plan['development_start_kst'], plan['development_end_kst'], window_minutes=720)}
    complete = set(manifest['records']) == expected
    if args.prepare_only:
        print(json.dumps({'status': 'ready_for_single_reserved_assessment' if complete else 'awaiting_complete_reserved_collection',
                          'windows': len(manifest['records']), 'expected_windows': len(expected), 'outcomes_loaded': False}), flush=True)
        return
    if not complete:
        raise ValueError('Every planned reserved request must complete before assessment')
    receipt_hash = sha256_file(freeze / 'predictions_receipt.json')
    collection = json.loads((source / 'collection_receipt.json').read_text(encoding='utf-8'))
    assert manifest['prediction_receipt_sha256'] == collection['prediction_receipt_sha256'] == receipt_hash
    assert datetime.fromisoformat(collection['collection_started_at_utc']) >= datetime.fromisoformat(receipt['sealed_at_utc'])
    out = private / 'external_reserved_assessment_v1'; out.mkdir(exist_ok=True)
    if (out / 'summary.json').exists():
        raise FileExistsError('Reserved assessment already completed; do not reevaluate for tuning')
    signature = {'prediction_receipt_sha256': receipt_hash, 'download_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
                 'runner_sha256': sha256_file(Path(__file__))}
    started = out / 'assessment_started.json'
    if started.exists():
        previous = json.loads(started.read_text(encoding='utf-8'))
        if previous['signature'] != signature:
            raise ValueError('Assessment interrupted with different fixed inputs; preserve previous evidence')
    else:
        json_write(started, {'signature': signature, 'started_at_utc': datetime.now(timezone.utc).isoformat(),
                             'policy': 'Identical deterministic recovery only; no model or threshold changes permitted.'})
    (out / 'input_download_manifest.json').write_bytes(manifest_bytes)
    frames, invalid_times = [], 0
    for identifier, record in manifest['records'].items():
        station, start, end = validate_development_request(plan, record['station'], record['start_kst'], record['end_kst'])
        assert identifier == f'{station}/{start:%Y%m%d%H%M}'
        assert datetime.fromisoformat(record['downloaded_at_utc']) >= datetime.fromisoformat(collection['collection_started_at_utc'])
        raw = source / 'raw' / f'{identifier}.txt'; ten_path = source / 'ten_minute' / f'{identifier}.parquet'
        assert sha256_file(raw) == record['raw_sha256'] and sha256_file(ten_path) == record['ten_minute_sha256']
        minute = parse_observations(raw.read_text(encoding='utf-8'), station, start, end)
        excluded = int(minute.attrs.get('invalid_timestamp_rows_excluded', 0))
        assert excluded == record['invalid_timestamp_rows_excluded']; invalid_times += excluded
        assert len(minute) == record['rows_one_minute']
        pieces = []; cursor = start; cache = (source / 'transport').resolve()
        for request in record['transport_requests']:
            sid, begin, finish = validate_development_request(plan, request['station'], request['start_kst'], request['end_kst'])
            assert sid == station and begin == cursor and finish <= end
            path = (cache / request['transport_cache_path']).resolve(); assert path.is_relative_to(cache)
            assert sha256_file(path) == request['transport_response_sha256']
            piece = parse_observations(path.read_text(encoding='utf-8'), sid, begin, finish)
            assert len(piece) == request['one_minute_rows']; pieces.append(piece)
            cursor = finish + pd.Timedelta(minutes=1)
        assert pieces and cursor == end + pd.Timedelta(minutes=1)
        pd.testing.assert_frame_equal(minute, pd.concat(pieces, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True), check_dtype=False)
        ten = exact_ten_minute_grid(minute)
        pd.testing.assert_frame_equal(ten, pd.read_parquet(ten_path), check_dtype=False)
        assert len(ten) == record['rows_exact_ten_minute']
        frames.append(ten)
    observations = pd.concat(frames, ignore_index=True)
    predictions = pd.read_parquet(freeze / 'predictions.parquet')
    combined, report = assess_predictions(predictions, observations)
    combined.to_parquet(out / 'assessment.parquet', index=False, compression='zstd')
    report.update(status='reserved_winter_single_assessment_complete_no_retuning', signature=signature,
                  invalid_timestamp_rows_excluded=invalid_times, protected_outcomes_used=False,
                  completed_at_utc=datetime.now(timezone.utc).isoformat(), frozen_files_unchanged=len(verify_freeze(ROOT)['files']))
    verify_reserved_freeze(ROOT, freeze)
    json_write(out / 'summary.json', report)
    print(json.dumps({k: report[k] for k in ['status', 'valid_state_rows', 'actual_ice_rows', 'both_fp_fn_improved', 'temperature']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
