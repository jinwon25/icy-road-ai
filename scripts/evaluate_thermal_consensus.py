"""고정18개 열·수분 가설을 이중 공간 제외 입력에서 선택하고 외부 개발 그룹에 적용."""
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_method_blending import read, write, preservation
from src.data_source import sha256_file as sha
from src.method_blending import domain
from src.qa633_metrics import daily_table, aggregate
from src.thermal_ice import fixed_thermal_rule, diagnostic_report
from src.thermal_consensus import predict_consensus
from src.event_retention import compare_event_retention

PRIVATE = ROOT / 'outputs/private'
SOURCE = PRIVATE / 'weather_memory_controls_20261013_v1'
OUT = PRIVATE / 'thermal_consensus_20261013_v1'
CONFIG = ROOT / 'config/thermal_consensus_experiment.json'


def report(f, p):
    r, st, _, events = diagnostic_report(f, p)
    r['daily'] = {}
    for n in [144, 130, 72, 1]:
        r['daily'][str(n)] = aggregate(daily_table(f, p, sorted(f.station.unique()), n), sorted(f.station.unique()))[0]
    return r, st, events


def eligible(candidate, baseline, cs, bs, events):
    daily = all(candidate['daily'][n][m+'_available_station_mean'] is not None and
        candidate['daily'][n][m+'_available_station_mean']+1e-12 >= baseline['daily'][n][m+'_available_station_mean']
        for n in ['144', '1'] for m in ['precision', 'recall', 'f1'])
    station = cs.set_index('station').tp.ge(bs.set_index('station').tp).all()
    return bool(daily and station and candidate['fp'] <= baseline['fp'] and candidate['fn'] <= baseline['fn'] and events['lost_events'] == 0)


def main():
    if OUT.exists(): raise FileExistsError('Preserve completed policy experiment')
    freezes = preservation(); plan = read(CONFIG); audit = read(SOURCE / 'independent_verification.json')
    assert audit['summary_sha256'] == sha(SOURCE / 'summary.json')
    for name, h in read(SOURCE / 'input_signatures.json').items(): assert sha(ROOT / name) == h
    OUT.mkdir(); write(OUT / 'experiment_plan.json', plan | {'started_at_utc': datetime.now(timezone.utc).isoformat()})
    pinned = [CONFIG, Path(__file__), ROOT / 'src/thermal_consensus.py', ROOT / 'src/qa633_metrics.py',
        SOURCE / 'summary.json', SOURCE / 'independent_verification.json', SOURCE / 'fit_receipts.json',
        SOURCE / 'groups.json', PRIVATE / 'weather_distance_20261010_v1/development_inputs.parquet',
        PRIVATE / 'qa633_development_20261013_v1/fixed_predictions.parquet']
    groups = read(SOURCE / 'groups.json'); write(OUT / 'groups.json', groups)
    water = domain(pd.read_parquet(pinned[-2], columns=['station', 'time', 'aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']))
    labels = domain(pd.read_parquet(pinned[-1], columns=['station', 'time', 'ice', 'original']))
    policies = {f'{a}_cold{t:+.1f}_dew{d:+.1f}': dict(aggregation=a, cold_threshold=t, dewpoint_margin=d)
        for a, t, d in product(plan['temperature_aggregation'], plan['cold_threshold_celsius'], plan['dewpoint_margin_celsius'])}
    policies['current_pair'] = dict(aggregation='mean', cold_threshold=0., dewpoint_margin=0.)
    write(OUT / 'policies.json', policies)
    decisions, outputs, all_inner, all_outer = {}, [], {}, {}
    for g in sorted(groups):
        frames = {}
        for kind in ['inner_oof', 'outer_predictions']:
            path = SOURCE / g / (kind+'.parquet'); pinned.append(path)
            f = pd.read_parquet(path, columns=['station', 'time', 'equal_distance_mse_mae300', 'nohistory12_mse300', 'nohistory12_mae300'])
            f = f.merge(labels, on=['station', 'time'], validate='one_to_one').merge(water, on=['station', 'time'], validate='one_to_one')
            assert set(f.station) == (set(groups[g]) if kind == 'outer_predictions' else set().union(*(set(v) for h,v in groups.items() if h != g)))
            f['original_trio'] = fixed_thermal_rule(f.equal_distance_mse_mae300, f, f.original, True)[0]
            w = f[['aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']].to_numpy()
            for name, spec in policies.items():
                f[name] = predict_consensus(f.nohistory12_mse300, f.nohistory12_mae300, w, f.original, **spec)[0]
            frames[kind] = f
        inner = frames['inner_oof']; baseline, bs, be = report(inner, inner.original_trio)
        candidates = {}; accepted = []
        for name in policies:
            r, st, ev = report(inner, inner[name]); retention = compare_event_retention(be, ev)
            ok = eligible(r, baseline, st, bs, retention)
            candidates[name] = dict(report=r, retention=retention, eligible=ok)
            if ok: accepted.append(name)
        chosen = min(accepted, key=lambda name: (-candidates[name]['report']['daily']['144']['f1_available_station_mean'], candidates[name]['report']['fp'], name)) if accepted else 'original_trio'
        decisions[g] = dict(chosen=chosen, accepted=accepted, baseline_report=baseline, candidates=candidates,
                            excluded_outer_group=g, selection_groups=sorted(set(groups)-{g}), outer_labels_used=False)
        outer = frames['outer_predictions']; outer['nested_selected'] = outer[chosen]
        outer['outer_group'] = g; outer['selected_policy'] = chosen
        outputs.append(outer); all_inner[g] = decisions[g]
        print(g, '적격', len(accepted), '선택', chosen, flush=True)
    combined = pd.concat(outputs, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    combined.to_parquet(OUT / 'predictions.parquet', index=False, compression='zstd')
    baseline, bs, be = report(combined, combined.original_trio)
    day_rows, station_rows = [], []
    for name in ['original_trio', *policies, 'nested_selected']:
        r, st, ev = report(combined, combined[name]); ret = compare_event_retention(be, ev)
        all_outer[name] = dict(report=r, retention=ret, eligible=eligible(r, baseline, st, bs, ret))
        for n in [144,130,72,1]:
            days = daily_table(combined, combined[name], sorted(combined.station.unique()), n)
            _, stations = aggregate(days, sorted(combined.station.unique()))
            for table, dest in [(days, day_rows), (stations, station_rows)]:
                table['policy'] = name; table['minimum_valid_slots'] = n; dest.append(table)
        ev.to_csv(OUT / (name+'_events.csv'), index=False)
        print(name, 'F1', r['daily']['144']['f1_available_station_mean'], 'P', r['daily']['144']['precision_available_station_mean'], 'FP/FN', r['fp'], r['fn'], '손실', ret['lost_events'], '적격', all_outer[name]['eligible'], flush=True)
    pd.concat(day_rows).to_csv(OUT / 'daily_metrics.csv', index=False)
    pd.concat(station_rows).to_csv(OUT / 'station_metrics.csv', index=False)
    write(OUT / 'decisions.json', decisions)
    write(OUT / 'input_signatures.json', {str(p.relative_to(ROOT)):sha(p) for p in pinned})
    assert preservation() == freezes
    write(OUT / 'summary.json', dict(status='thermal_consensus_development_complete', finished_at_utc=datetime.now(timezone.utc).isoformat(),
        reports=all_outer, choices={g:d['chosen'] for g,d in decisions.items()}, rows=len(combined),
        candidate_policies=len(policies), new_model_fits=0, repeated_development=True,
        new_independent_assessment=False, assessment_outcomes_used=False, model_promoted=False,
        old_frozen_files=freezes[0], reserved_frozen_files=freezes[1],
        files={p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file()}))


if __name__ == '__main__': main()
