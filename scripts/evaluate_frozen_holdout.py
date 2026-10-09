"""저장된 보호 지점 예측을 1회 평가한다. 재학습·임계값 변경 경로가 없다."""
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive, sha256_file
from src.observation_io import daily_members, read_columns, numeric_observations
from src.validation import PROTECTED_STATIONS, canonical_station_id, normalize_state, regression_metrics, binary_metrics, daily_scores, macro_scores, mean_defined
from src.frozen_assessment import verify_freeze


def main():
    frozen = verify_freeze(ROOT)
    out = ROOT / 'outputs/private/frozen_assessment_v1'
    if (out / 'assessment_started.json').exists():
        raise FileExistsError('Assessment already opened; no silent repeat or overwrite')
    receipt = json.loads((out / 'predictions_receipt.json').read_text(encoding='utf-8'))
    assert receipt['freeze_sha256'] == sha256_file(out / 'freeze.json')
    assert receipt['predictions_sha256'] == sha256_file(out / 'predictions.parquet')
    assert receipt['protected_outcomes_loaded'] is False
    (out / 'assessment_started.json').write_text(json.dumps({'opened_at_utc': datetime.now(timezone.utc).isoformat(), 'freeze_sha256': receipt['freeze_sha256'], 'rule': 'No changes selected from these outcomes.'}, indent=2), encoding='utf-8')
    columns = ['관측시각 (KST)', '관측 지점번호', '노면온도 (광학)', '노면상태']
    parts = []
    with zipfile.ZipFile(competition_archive(ROOT)) as archive:
        for member in daily_members(archive, 'RWIS'):
            frame = read_columns(archive, member, columns, ['time', 'station', 'road_temp', 'state_raw'])
            frame['station'] = frame.station.map(canonical_station_id)
            parts.append(frame.loc[frame.station.isin(PROTECTED_STATIONS)].copy())
    targets = pd.concat(parts, ignore_index=True)
    targets['time'] = pd.to_datetime(targets.time, errors='raise')
    targets['observed_road_temp_c'] = numeric_observations(targets.road_temp)
    targets.loc[~targets.observed_road_temp_c.between(-60, 70), 'observed_road_temp_c'] = float('nan')
    targets['observed_ice'] = targets.state_raw.map(normalize_state)
    if targets.duplicated(['station', 'time']).any(): raise ValueError('Duplicate protected outcome timestamps')
    predictions = pd.read_parquet(out / 'predictions.parquet')
    joined = predictions.merge(targets[['station', 'time', 'observed_road_temp_c', 'observed_ice']], on=['station', 'time'], how='left', validate='one_to_one', indicator=True)
    days = daily_scores(joined[['station', 'time', 'observed_ice', 'predicted_ice']].itertuples(index=False, name=None), expected_slots=144, minimum_coverage=1.)
    station_results = []
    for sid, part in joined.groupby('station'):
        station_results.append({'station': sid, 'temperature': regression_metrics(part.observed_road_temp_c, part.estimated_road_temp_c),
                                'ice_slot': binary_metrics(part.observed_ice, part.predicted_ice),
                                'ice_daily': macro_scores([d for d in days if d['station'] == sid])})
    macro = {key: mean_defined(s['temperature'][key] for s in station_results) for key in ('mae', 'rmse', 'bias')}
    report = {'status': 'frozen_protected_station_assessment_not_organizer_score', 'stations': station_results,
              'temperature_station_macro': macro, 'ice_slot_micro': binary_metrics(joined.observed_ice, joined.predicted_ice),
              'ice_daily_station_macro': macro_scores(days), 'prediction_rows': len(joined),
              'missing_target_rows': int(joined['_merge'].eq('left_only').sum()),
              'valid_ice_targets': int(joined.observed_ice.notna().sum()), 'ice_targets': int(joined.observed_ice.eq(1).sum()),
              'threshold': frozen['ice_threshold'], 'threshold_changed_after_opening': False,
              'freeze_sha256': receipt['freeze_sha256'], 'predictions_sha256': receipt['predictions_sha256'],
              'limitations': ['Official daily aggregation edge cases remain provisional: complete 144-slot days; undefined metrics are null.',
                             'This is our frozen assessment on organizer-designated stations, not an organizer-issued score.',
                             'No protected station is used as a reference input; final model was fitted on both winters at 14 development stations.',
                             'Scores do not establish accuracy at all unobserved road segments or future operational warning performance.']}
    joined.drop(columns='_merge').to_parquet(out / 'assessment_pairs.parquet', index=False)
    pd.DataFrame(days).to_csv(out / 'daily_scores.csv', index=False, encoding='utf-8-sig')
    (out / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
