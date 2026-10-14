"""완료 후 지표·실패 조건·지점별 탐지를 비교해 연구 인계 자료를 만든다."""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/private/ice_methodology_20261010_v1'


def main():
    summary = json.loads((OUT / 'summary.json').read_text('utf-8'))
    table = []
    for name, r in summary['metrics'].items():
        row = {'method': name, **{k: r[k] for k in ['tp', 'fp', 'fn', 'f1', 'fixed_ice_day_f1', 'provisional_daily_station_f1', 'detected_events', 'detected_single_slot_events']}}
        row['AP'] = summary['score_metrics'].get(name, {}).get('average_precision')
        row['original_guard'] = summary['development_guards'][name]['original']['eligible']; row['thermal_guard'] = summary['development_guards'][name]['thermal14']['eligible']
        table.append(row)
    frame = pd.DataFrame(table); print(frame.to_string(index=False))
    for name in summary['score_metrics']:
        st = pd.read_csv(OUT / (name+'_stations.csv'), dtype={'station': str})
        original = pd.read_csv(OUT / 'original_stations.csv', dtype={'station': str})
        original = original.set_index('station'); st = st.set_index('station')
        print(name, 'TP 변화', (st.tp-original.tp).to_dict())
        print(name, '실패 조건', {b: [k for k, v in g.items() if v is False and k != 'eligible'] for b, g in summary['development_guards'][name].items()})
    print('thresholds', {g: d['thresholds'] for g, d in json.loads((OUT / 'decisions.json').read_text('utf-8')).items()})
    target = OUT / 'post_selection_metrics.csv'
    if target.exists():
        raise FileExistsError('Preserve completed inspection')
    frame.to_csv(target, index=False)


if __name__ == '__main__':
    main()
