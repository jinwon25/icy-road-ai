"""저장된 지역 제외 점수의 내부 임계값을 모든 서로 다른 값에서 정확 선택한다."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.exact_daily_threshold import select_exact_thresholds, choose_exact
from src.runtime_metrics import runtime_daily
from src.extended_comparison import event_retention
from src.data_source import sha256_file as sha
from scripts.evaluate_icing_transition import read, write, score_name, KEYS
from scripts.evaluate_method_blending import preservation


def summarize(out, frame):
    """각 후보의 날짜·지점·겨울 지표와 고정 채택 기준을 기록한다."""
    methods = [c for c in frame if c not in [*KEYS, 'available']]
    reports, stations_all, days_all, regions = {}, [], [], []
    for name in methods:
        reports[name] = {}
        for year in ['all', 2024, 2025]:
            f = frame if year == 'all' else frame.loc[frame.winter.eq(year)]
            r, st, days = runtime_daily(f, f[name]); reports[name][str(year)] = r
            if year == 'all':
                stations_all.append(st.assign(method=name)); days_all.append(days.assign(method=name))
        retention, events = event_retention(frame, frame[name], frame.current)
        reports[name]['events'] = retention; events.to_csv(out / (name + '_events.csv'), index=False)
        for group, part in frame.groupby('group'):
            r, _, _ = runtime_daily(part, part[name]); regions.append(dict(method=name, group=group, **r))
    stations = pd.concat(stations_all, ignore_index=True)
    old_st = stations.loc[stations.method.eq('current')].set_index('station').f1.fillna(0)
    old = reports['current']['all']
    for name, r in reports.items():
        new = r['all']; st = stations.loc[stations.method.eq(name)].set_index('station').f1.fillna(0)
        gates = dict(
            f1_improves=new['f1_fixed_population'] >= old['f1_fixed_population'] * 1.01,
            precision_noninferior=new['precision_available_station_mean'] is not None and new['precision_available_station_mean'] >= old['precision_available_station_mean'],
            recall_noninferior=new['recall_available_station_mean'] is not None and new['recall_available_station_mean'] >= old['recall_available_station_mean'],
            each_winter=all(r[str(y)]['f1_fixed_population'] >= reports['current'][str(y)]['f1_fixed_population'] for y in [2024, 2025]),
            each_station=bool(st.ge(old_st).all()), events_preserved=r['events']['lost_events'] == 0,
            beats_asos=new['f1_fixed_population'] > reports['asos_zero']['all']['f1_fixed_population'])
        r['gates'], r['eligible'] = gates, all(gates.values())
        print('RESULT', name, round(new['f1_fixed_population'], 8), gates, flush=True)
    stations.to_csv(out / 'stations.csv', index=False)
    pd.concat(days_all, ignore_index=True).to_csv(out / 'daily.csv', index=False)
    pd.DataFrame(regions).to_csv(out / 'regions.csv', index=False)
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', required=True, type=Path)
    out = parser.parse_args().output.resolve()
    if not out.is_relative_to((ROOT / 'outputs/private').resolve()): raise ValueError('Private output required')
    config = ROOT / 'config/icing_threshold_refinement_20261025.json'; plan = read(config)
    source = ROOT / plan['source_experiment']; original = read(source / 'summary.json')
    assert original['status'] == 'icing_transition_development_complete'
    signatures = {p.relative_to(ROOT).as_posix(): sha(p) for p in [config, Path(__file__), ROOT / 'src/exact_daily_threshold.py', source / 'summary.json', source / 'plan.json']}
    if out.exists():
        assert read(out / 'plan.json')['signatures'] == signatures
        if (out / 'summary.json').exists(): raise FileExistsError('Completed experiment is preserved')
    else:
        out.mkdir(parents=True); write(out / 'plan.json', dict(settings=plan, signatures=signatures, started_at_utc=datetime.now(timezone.utc).isoformat()))
    frozen = preservation(); groups = sorted(read(source / 'decisions.json'))
    models = {name+'_m'+str(round(a*100)): (name, score_name(a)) for name in plan['models'] for a in plan['memory_strengths']}
    cache = {}
    def load(name, key):
        model, column = models[name]
        path = model + '/' + '__'.join(key) + '.parquet'
        if path not in cache:
            assert sha(source / path) == original['files'][path]
            cache[path] = pd.read_parquet(source / path)
        return cache[path], column
    decisions, parts = {}, []
    for outer in groups:
        table_path = out / (outer + '_selection.json')
        if table_path.exists():
            table = pd.DataFrame(read(table_path))
        else:
            rows = []
            for name in models:
                chunks = []
                for held in groups:
                    if held == outer: continue
                    f, column = load(name, tuple(sorted([outer, held])))
                    q = f.loc[f.group.eq(held)].copy(); q['score'] = q[column]; chunks.append(q)
                inner = pd.concat(chunks, ignore_index=True)
                best = select_exact_thresholds(inner, inner.score)
                rows.extend(dict(candidate=name, track=track, **record) for track, record in best.items())
                print('내부 모든 점수 비교', outer, name, best['mean_f1']['unique_thresholds'], flush=True)
            # ASOS 비교는 고정 규칙 자체이며 임계값을 재선택하지 않는다.
            air = np.where(inner.available, inner.asos_air_temp.le(0), np.nan)
            all_r, _, _ = runtime_daily(inner, air)
            winter_r = [runtime_daily(inner.loc[inner.winter.eq(y)], air[inner.winter.eq(y)])[0]['f1_fixed_population'] for y in [2024, 2025]]
            valid = inner.ice.isin([0, 1]).to_numpy() & np.isfinite(air)
            fp = int((valid & inner.ice.eq(0).to_numpy() & (air == 1)).sum())
            for track in plan['tracks']:
                rows.append(dict(candidate='asos_zero', track=track, threshold=.5, mean_f1=all_r['f1_fixed_population'], worst_winter_f1=min(winter_r), fp=fp))
            write(table_path, rows); table = pd.DataFrame(rows)
        reference, _ = load(next(iter(models)), (outer,))
        result = reference[[*KEYS, 'available']].copy()
        result['asos_zero'] = np.where(result.available, result.asos_air_temp.le(0), np.nan)
        decisions[outer] = {'held_stations': sorted(result.station.unique()), 'outer_labels_used_for_selection': False, 'choices': {}}
        for track in plan['tracks']:
            t = table.loc[table.track.eq(track)]
            for name in [*models, 'selected']:
                choice = choose_exact(t if name == 'selected' else t.loc[t.candidate.eq(name)], track)
                choice = {k: v for k, v in choice.items() if not (isinstance(v, float) and np.isnan(v))}
                chosen = choice['candidate']; key = name + '_' + track
                if chosen == 'asos_zero': scores = result.asos_air_temp.le(0).to_numpy(float)
                else:
                    q, column = load(chosen, (outer,)); pd.testing.assert_frame_equal(q[['station','time']], result[['station','time']])
                    scores = q[column].to_numpy()
                result[key] = np.where(result.available, scores >= choice['threshold'], np.nan)
                decisions[outer]['choices'][key] = choice
        parts.append(result)
    f = pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    base = pd.read_parquet(source / 'predictions.parquet').sort_values(['station', 'time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(f[['station', 'time', 'ice', 'available']], base[['station', 'time', 'ice', 'available']])
    f['current'] = base.current.to_numpy()
    reports = summarize(out, f)
    f.to_parquet(out / 'predictions.parquet', index=False, compression='zstd'); write(out / 'decisions.json', decisions)
    assert preservation() == frozen
    write(out / 'summary.json', dict(status='exact_icing_threshold_development_complete', rows=len(f), reports=reports, new_model_fits=0,
          protected_labels_read=False, new_independent_assessment=False, frozen_counts=frozen,
          files={p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*') if p.is_file()}))


if __name__ == '__main__': main()
