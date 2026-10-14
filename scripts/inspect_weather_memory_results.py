"""후속 연구의 지점·온도·범위·결빙 결과를 작은 표로 출력한다."""
import json
from pathlib import Path
import pandas as pd
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/private' / (sys.argv[1] if len(sys.argv) > 1 else 'weather_memory_temperature_20261013_v2')


def main():
    s = json.loads((OUT / 'summary.json').read_text('utf-8'))
    b = s['metrics']['equal_distance_mse_mae300']
    print('choices', s['choices'])
    for name, m in s['metrics'].items():
        harms = {st: (r['mae']/b['stations'][st]['mae']-1)*100 for st, r in m['stations'].items()}
        print(name, 'MAE/RMSE', m['pooled']['mae'], m['pooled']['rmse'], 'macro', m['station_macro'], 'near', m['near_freezing']['mae'], 'gate', s['temperature_gate_vs_trio'].get(name), 'worst', max(harms, key=harms.get), max(harms.values()))
        print('station changes (%)', {st: round(v, 2) for st, v in harms.items()})
    for name, r in s['ranges'].items():
        worst = min(r['stations'], key=lambda st: r['stations'][st]['coverage'])
        print(name, 'coverage', r['pooled_coverage'], r['station_macro_coverage'], 'width/score', r['mean_width'], r['mean_interval_score'], 'worst', worst, r['stations'][worst]['coverage'], 'near', r['near_freezing']['coverage'])
    for name, m in s['ice_diagnostic'].items():
        print(name, 'TP FP FN events singles', m['tp'], m['fp'], m['fn'], m['detected_events'], m['detected_single_slot_events'], 'guard', s['ice_guard_vs_trio'].get(name))
        print('f1 variants', {k: m[k] for k in ['f1', 'fixed_station_f1_zero_undefined', 'fixed_ice_day_f1', 'provisional_daily_station_f1']})
    baseline_stations = pd.read_csv(OUT / 'ice_stations_equal_distance_mse_mae300.csv', dtype={'station': str}).set_index('station')
    candidate_stations = pd.read_csv(OUT / 'ice_stations_equal_trio_memory.csv', dtype={'station': str}).set_index('station')
    print('ice station TP/FP differences', (candidate_stations[['tp', 'fp']]-baseline_stations[['tp', 'fp']]).to_dict('index'))
    old_events = pd.read_csv(OUT / 'ice_events_equal_distance_mse_mae300.csv').set_index(['station', 'start_kst'])
    new_events = pd.read_csv(OUT / 'ice_events_equal_trio_memory.csv').set_index(['station', 'start_kst'])
    assert old_events.index.equals(new_events.index)
    lost = old_events.detected_slots.gt(0) & new_events.detected_slots.eq(0)
    gained = old_events.detected_slots.eq(0) & new_events.detected_slots.gt(0)
    print('event losses/gains', int(lost.sum()), int(gained.sum()), 'lost stations', old_events.loc[lost].reset_index().station.tolist())
    print('fit seconds', sum(r['fit_seconds'] for r in json.loads((OUT / 'fit_receipts.json').read_text('utf-8'))))


if __name__ == '__main__': main()
