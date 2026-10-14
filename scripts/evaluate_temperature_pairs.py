"""기존300회 단독을 기준으로 세 가지 고정 균등 결합을 추가 비교한다."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.method_blending import domain, convex_predict, temperature_gate
from src.temperature_transfer import regression_report
from src.thermal_ice import fixed_thermal_rule, diagnostic_report
from scripts.evaluate_method_blending import read, write, preservation, PRIVATE

SOURCE = PRIVATE / 'method_blending_20261010_v2'
CONFIG = ROOT / 'config/temperature_pair_blending_experiment.json'
DEFAULT = PRIVATE / 'temperature_pair_blending_20261010_v1'


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, default=DEFAULT)
    out = parser.parse_args().output.resolve()
    if out.exists() or not out.is_relative_to(PRIVATE.resolve()):
        raise ValueError('New private directory required')
    plan = read(CONFIG); baseline = plan['primary_baseline']; blends = plan['blends']
    if baseline != 'weather_mse300' or len(blends) != 3:
        raise ValueError('Pinned fixed pair/trio contract required')
    audit = read(SOURCE / 'independent_verification.json'); summary = read(SOURCE / 'summary.json')
    if audit['status'] != 'independent_three_level_blending_audit_passed' or audit['summary_sha256'] != sha(SOURCE / 'summary.json'):
        raise ValueError('Audited source required')
    freezes = preservation(); out.mkdir()
    write(out / 'experiment_plan.json', plan | {'started_at_utc': datetime.now(timezone.utc).isoformat(), 'new_independent_assessment': False})
    shutil.copy2(Path(__file__), out / 'analysis_source.py')
    signatures = {str(p.relative_to(ROOT)): sha(p) for p in [CONFIG, Path(__file__), ROOT / 'src/method_blending.py',
                  ROOT / 'src/temperature_transfer.py', ROOT / 'src/thermal_ice.py', ROOT / 'scripts/evaluate_method_blending.py',
                  SOURCE / 'summary.json', SOURCE / 'independent_verification.json', SOURCE / 'groups.json']}
    groups = read(SOURCE / 'groups.json'); write(out / 'groups.json', groups); parts, decisions = [], {}
    for outer in groups:
        folder = out / outer; folder.mkdir(); frames = {}
        for kind in ['inner_oof', 'outer_predictions']:
            path = SOURCE / outer / (kind+'.parquet'); digest = sha(path)
            if digest != summary['files'][path.relative_to(SOURCE).as_posix()]:
                raise ValueError('Component source changed')
            signatures[str(path.relative_to(ROOT))] = digest
            frame = domain(pd.read_parquet(path)).drop(columns=['selected_candidate', 'selected_temperature'], errors='ignore')
            for name, columns in blends.items():
                frame[name] = convex_predict(frame[columns].to_numpy(), np.ones(len(columns))/len(columns))
            frames[kind] = frame
        inner, result = frames['inner_oof'], frames['outer_predictions']
        reports = {c: regression_report(inner, inner[c]) for c in [baseline, *blends]}
        eligible = [c for c in blends if temperature_gate(reports[c], reports[baseline], plan['maximum_station_harm'])]
        chosen = min(eligible, key=lambda c: (reports[c]['station_macro']['mae'], reports[c]['station_macro']['rmse'], c)) if eligible else baseline
        decision = dict(outer_group=outer, selection_groups=sorted(set(groups)-{outer}), selected_candidate=chosen,
                        inner_reports=reports, outer_labels_used_for_selection=False)
        write(folder / 'decision.json', decision); decisions[outer] = decision
        inner.to_parquet(folder / 'inner_oof.parquet', index=False, compression='zstd')
        result['selected_candidate'] = chosen; result['selected_temperature'] = result[chosen]
        result.to_parquet(folder / 'outer_predictions.parquet', index=False, compression='zstd'); parts.append(result)
    combined = pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    metrics = {c: regression_report(combined, combined[c]) for c in ['direct_weather14', baseline, *blends, 'selected_temperature']}
    classified_source = SOURCE / 'ice_predictions.parquet'; data_source = PRIVATE / 'weather_distance_20261010_v1/development_inputs.parquet'
    for path in [classified_source, data_source]:
        signatures[str(path.relative_to(ROOT))] = sha(path)
    labels = pd.read_parquet(classified_source, columns=['station', 'time', 'ice', 'baseline_prediction'])
    classified = combined.merge(labels, on=['station', 'time'], validate='one_to_one')
    if len(classified) != len(combined) or not classified[['station', 'time']].equals(combined[['station', 'time']]):
        raise ValueError('Classification row alignment changed')
    inputs = pd.read_parquet(data_source, columns=['station', 'time', 'aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm'])
    water = combined[['station', 'time']].merge(inputs, on=['station', 'time'], validate='one_to_one'); ice = {}
    for c in [baseline, *blends, 'selected_temperature']:
        p, fallback, _ = fixed_thermal_rule(classified[c].to_numpy(), water, classified.baseline_prediction.to_numpy(), True)
        classified['ice_'+c] = p
        report, stations, days, events = diagnostic_report(classified, p); ice[c] = report | {'fallback_rows': int(fallback.sum())}
        stations.to_csv(out / ('ice_stations_'+c+'.csv'), index=False); days.to_csv(out / ('ice_days_'+c+'.csv'), index=False); events.to_csv(out / ('ice_events_'+c+'.csv'), index=False)
    combined.to_parquet(out / 'outer_predictions.parquet', index=False, compression='zstd'); classified.to_parquet(out / 'ice_predictions.parquet', index=False, compression='zstd')
    write(out / 'input_signatures.json', signatures); write(out / 'decisions.json', decisions)
    assert preservation() == freezes
    result = dict(status='fixed_strong_pairs_development_complete', completed_at_utc=datetime.now(timezone.utc).isoformat(),
                  new_base_fits=0, learned_weights=0, metrics=metrics, ice_diagnostic=ice, choices={g: d['selected_candidate'] for g, d in decisions.items()},
                  development_gate_vs_mse300={c: temperature_gate(metrics[c], metrics[baseline]) for c in [*blends, 'selected_temperature']},
                  assessment_outcomes_used=False, new_independent_assessment=False, model_promoted=False,
                  files={p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob('*')) if p.is_file()})
    write(out / 'summary.json', result); print(result['choices'], result['development_gate_vs_mse300'])


if __name__ == '__main__':
    main()
