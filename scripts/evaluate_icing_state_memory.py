"""현재 결빙 예측의 고정 시간 상태 14가지를 비교하고 일별 지표를 별도 검산한다."""
from datetime import datetime, timezone
from itertools import product
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.two_winter import validate
from src.icing_state_memory import causal_ice_state
from src.runtime_metrics import runtime_daily
from src.extended_comparison import event_retention
from scripts.audit_extended_classification import independently_count
from scripts.evaluate_method_blending import preservation


def read(p):
    return json.loads(p.read_text('utf-8'))


def write(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', 'utf-8')


def main():
    config = ROOT / 'config/icing_state_memory_20261024.json'
    out = ROOT / 'outputs/private/icing_state_memory_20261024_v1'
    if out.exists():
        raise FileExistsError('Preserve previous state-memory study')
    plan = read(config)
    source = ROOT / plan['baseline']
    assert sha(source) == read(source.parent / 'audit_runtime.json')['runtime_prediction_sha256']
    frozen = preservation()
    f = validate(pd.read_parquet(source)).sort_values(['station', 'time']).reset_index(drop=True)
    specs = {f'confirm{c}_hold{h}_release{r:g}': dict(confirmation=c, hold_minutes=h, release_c=r)
             for c, h, r in product(plan['confirmation_slots'], plan['hold_minutes'], plan['release_c'])
             if h or r == 0}
    assert len(specs) == 15
    out.mkdir(parents=True)
    write(out / 'plan.json', dict(settings=plan, policies=specs,
        started_at_utc=datetime.now(timezone.utc).isoformat(), signatures={str(p.relative_to(ROOT)): sha(p)
        for p in [config, source, Path(__file__), ROOT / 'src/icing_state_memory.py',
                  ROOT / 'src/runtime_metrics.py', ROOT / 'src/qa633_metrics.py']}))
    base = f.physical_both.to_numpy(float)
    all_reports, station_tables, day_tables = {}, [], []
    outputs = f[['station', 'time', 'winter', 'group', 'ice']].copy()
    baseline = {}; baseline_stations = None
    for year in ['all', 2024, 2025]:
        q = f if year == 'all' else f.loc[f.winter.eq(year)]
        report, stations, _ = runtime_daily(q, q.physical_both)
        baseline[str(year)] = report
        if year == 'all': baseline_stations = stations.set_index('station')
    for name, spec in specs.items():
        pred = causal_ice_state(f, base, f.temperature_both, **spec)
        np.testing.assert_array_equal(np.isfinite(pred), np.isfinite(base))
        if name == 'confirm1_hold0_release0': np.testing.assert_array_equal(pred, base)
        outputs[name] = pred
        reports = {}; st = None
        for year in ['all', 2024, 2025]:
            mask = np.ones(len(f), bool) if year == 'all' else f.winter.eq(year).to_numpy()
            q = f.loc[mask, ['station', 'time', 'ice', 'winter']].copy()
            report, stations, days = runtime_daily(q, pred[mask])
            reports[str(year)] = report
            if year == 'all':
                st = stations.set_index('station')
                stations['policy'] = name; station_tables.append(stations)
                days['policy'] = name; day_tables.append(days)
            q.loc[~np.isfinite(pred[mask]), 'ice'] = np.nan
            independent = independently_count(q, np.nan_to_num(pred[mask]), np.array([.5]))
            assert abs(float(independent.f1_fixed_population.iloc[0]) - report['f1_fixed_population']) < 1e-12
        retention, events = event_retention(f, pred, base)
        events.to_csv(out / (name + '_events.csv'), index=False)
        old, new = baseline['all'], reports['all']
        gates = dict(f1_improves=new['f1_fixed_population'] >= old['f1_fixed_population'] * 1.01,
            precision_noninferior=new['precision_available_station_mean'] is not None and new['precision_available_station_mean'] >= old['precision_available_station_mean'],
            recall_noninferior=new['recall_available_station_mean'] is not None and new['recall_available_station_mean'] >= old['recall_available_station_mean'],
            each_winter=all(reports[str(y)]['f1_fixed_population'] >= baseline[str(y)]['f1_fixed_population'] for y in [2024, 2025]),
            each_station=bool((st.f1.fillna(0) >= baseline_stations.f1.fillna(0)).all()),
            events_preserved=retention['lost_events'] == 0)
        all_reports[name] = dict(periods=reports, gates=gates, eligible=all(gates.values()), events=retention)
        print(name, new['f1_fixed_population'], gates, flush=True)
    outputs.to_parquet(out / 'predictions.parquet', index=False, compression='zstd')
    pd.concat(station_tables, ignore_index=True).to_csv(out / 'station_metrics.csv', index=False)
    pd.concat(day_tables, ignore_index=True).to_csv(out / 'daily_metrics.csv', index=False)
    # 정답 온도 구간은 오류 진단층에만 사용한다. 추론 정책에는 들어가지 않는다.
    valid = f.ice.isin([0, 1]) & np.isfinite(base)
    d = f.loc[valid, ['station', 'winter', 'road_temp']].copy()
    y, p = f.loc[valid, 'ice'].to_numpy(), base[valid]
    for label, mask in {'tp': (y == 1) & (p == 1), 'fp': (y == 0) & (p == 1),
                        'fn': (y == 1) & (p == 0), 'tn': (y == 0) & (p == 0)}.items(): d[label] = mask.astype(int)
    d['observed_temperature_bin'] = pd.cut(d.road_temp, [-np.inf, -3, 0, 3, np.inf],
        labels=['below_-3', '-3_to_0', '0_to_3', 'above_3']).astype('object').fillna('missing')
    d.groupby(['station', 'winter', 'observed_temperature_bin'])[['tp', 'fp', 'fn', 'tn']].sum().reset_index().to_csv(out / 'baseline_confusion_by_observed_temperature.csv', index=False)
    assert preservation() == frozen
    write(out / 'summary.json', dict(status='fixed_icing_state_comparison_complete', reports=all_reports,
        baseline=baseline, new_policies=14, independent_daily_f1_checks=45, rows=len(f),
        protected_labels_read=False, new_independent_assessment=False, model_promoted=False,
        eligible=[n for n, r in all_reports.items() if r['eligible']],
        frozen_counts=list(frozen), files={p.name: sha(p) for p in out.iterdir() if p.is_file()}))


if __name__ == '__main__': main()
