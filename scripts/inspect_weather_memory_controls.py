import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/private/weather_memory_controls_20261013_v1'


def main():
    s = json.loads((OUT / 'summary.json').read_text('utf-8'))
    for name, r in s['metrics'].items():
        base = s['metrics']['equal_distance_mse_mae300']
        harm = {st: 100*(v['mae']/base['stations'][st]['mae']-1) for st, v in r['stations'].items()}
        print(name, r['pooled']['mae'], r['pooled']['rmse'], r['near_freezing']['mae'], 'macro', r['station_macro']['mae'], 'gate', s['gate_vs_original_trio'].get(name), 'worst', max(harm, key=harm.get), max(harm.values()))
    print('matched gates', s['memory_gate_vs_matched_control']); print('choices', s['choices'])
    for name, m in s['ice_diagnostic'].items(): print(name, m['tp'], m['fp'], m['fn'], m['detected_events'], m['fixed_ice_day_f1'])
    for name in ['equal_nohistory_pair', 'equal_trio_nohistory']:
        print('f1 variants', name, {k: s['ice_diagnostic'][name][k] for k in ['f1', 'fixed_station_f1_zero_undefined', 'fixed_ice_day_f1', 'provisional_daily_station_f1', 'detected_single_slot_events']})
        b = pd.read_csv(ROOT / 'outputs/private/weather_memory_temperature_20261013_v2/ice_stations_equal_distance_mse_mae300.csv', dtype={'station': str}).set_index('station')
        c = pd.read_csv(OUT / f'ice_stations_{name}.csv', dtype={'station': str}).set_index('station')
        print('station TP/FP changes', name, (c[['tp', 'fp']]-b[['tp', 'fp']]).to_dict('index'))
    for memory, control in zip(['memory12_mse300', 'memory12_mae300', 'equal_memory_pair', 'equal_trio_memory'], ['nohistory12_mse300', 'nohistory12_mae300', 'equal_nohistory_pair', 'equal_trio_nohistory']):
        m, c = s['metrics'][memory], s['metrics'][control]
        print('matched', memory, 'MAE decrease %', 100*(1-m['pooled']['mae']/c['pooled']['mae']), 'near decrease %', 100*(1-m['near_freezing']['mae']/c['near_freezing']['mae']), 'station changes %', {st: round(100*(r['mae']/c['stations'][st]['mae']-1), 2) for st, r in m['stations'].items()})


if __name__ == '__main__': main()
