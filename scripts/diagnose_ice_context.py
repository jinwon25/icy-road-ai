"""Describe existing OOF errors against prior neighbor context; no prediction edits."""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validation import assert_training_stations, binary_metrics


def main():
    private = ROOT / 'outputs/private'
    context = pd.read_parquet(private / 'rwis_context/outer_context.parquet')
    predictions = pd.read_parquet(private / 'ice_nonlinear/predictions.parquet')
    for data in [context, predictions]:
        data['station'] = data.station.astype(str)
        assert_training_stations(data.station.unique())
    joined = context.merge(predictions[['station', 'time', 'ice', 'pred_daily']],
                           on=['station', 'time'], how='outer', validate='one_to_one',
                           indicator=True, suffixes=('', '_prediction'))
    if not joined._merge.eq('both').all() or not joined.ice.equals(joined.ice_prediction):
        raise ValueError('Prediction/context target mismatch')
    valid = joined.loc[joined.ice.notna()].copy()
    valid['humidity_group'] = 'missing'
    valid.loc[valid.moisture_humidity.lt(90), 'humidity_group'] = 'below_90'
    valid.loc[valid.moisture_humidity.ge(90), 'humidity_group'] = 'at_least_90'
    valid['rain_group'] = 'missing'
    valid.loc[valid.moisture_rain_10m.eq(0), 'rain_group'] = 'zero_increment'
    valid.loc[valid.moisture_rain_10m.gt(0), 'rain_group'] = 'positive_increment'
    rows = []
    for field in ['humidity_group', 'rain_group']:
        for (station, condition), group in valid.groupby(['station', field]):
            rows.append({'station': station, 'condition_type': field, 'condition': condition,
                         **binary_metrics(group.ice.astype(int), group.pred_daily.astype(int))})
    table = pd.DataFrame(rows)
    aggregate = table.groupby(['condition_type', 'condition'])[['n', 'tp', 'fp', 'fn', 'tn']].sum().reset_index()
    worst = []
    for station, group in valid.groupby('station'):
        metric = binary_metrics(group.ice.astype(int), group.pred_daily.astype(int))
        worst.append({'station': station, **metric,
                      'false_alarm_rows_humidity_below90': int((group.pred_daily.eq(1) & group.ice.eq(0)
                                                              & group.moisture_humidity.lt(90)).sum()),
                      'humidity_distance_km': float(group.moisture_distance_km.iloc[0])})
    worst = sorted(worst, key=lambda row: (-row['fp'], row['station']))
    summary = {'status': 'descriptive_error_context_not_threshold_tuning',
               'valid_rows': len(valid), 'condition_groups': aggregate.to_dict('records'),
               'top_false_alarm_stations': worst[:5],
               'interpretation': 'High/low humidity and rain increments describe exposure, not a calibrated alarm rule. Missing rain is not zero.',
               'next_step': 'Use only fully excluded reference plans in future learned models; do not use these outer errors to select a humidity cutoff.'}
    out = private / 'rwis_context'
    table.to_csv(out / 'hgb_error_context_by_station.csv', index=False, encoding='utf-8-sig')
    aggregate.to_csv(out / 'hgb_error_context_aggregate.csv', index=False, encoding='utf-8-sig')
    (out / 'error_context_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
