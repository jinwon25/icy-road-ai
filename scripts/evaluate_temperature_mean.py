"""감사된 두 성분을 1:1로 평균하고 동일 내부 OOF에서 선택한다. 새 학습은 없다."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.evidence_review import review_domain
from src.temperature_transfer import regression_report, select_temperature
from src.temperature_mean import equal_mean, component_error_diagnostics, CANDIDATE, COMPONENTS
from src.thermal_ice import fixed_thermal_rule, diagnostic_report
from scripts.fresh_station_validation import old_freezes, verify_seal

PRIVATE = ROOT / 'outputs/private'
SOURCE = PRIVATE / 'weather_distance_20261010_v1'
DEFAULT = PRIVATE / 'temperature_mean_20261010_v1'
CONFIG = ROOT / 'config/temperature_mean_experiment.json'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False); handle.write('\n')


def preservation():
    count = old_freezes()
    for name in ['temperature_blind_20261010_v1', 'fresh_station_validation_20261009_v2']:
        verify_seal(PRIVATE / name)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT)
    out = parser.parse_args().output.resolve()
    if out.exists() or not out.is_relative_to(PRIVATE.resolve()):
        raise ValueError('New private experiment directory required')
    config = read(CONFIG)
    if config['candidate'] != CANDIDATE or config['components'] != list(COMPONENTS) or config['weights'] != [.5, .5]:
        raise ValueError('Fixed equal-mean contract differs')
    freezes = preservation()
    source_summary = read(SOURCE / 'summary.json'); source_audit = read(SOURCE / 'independent_verification.json')
    if source_audit['status'] != 'independent_distance_ablation_audit_passed' or source_audit['summary_sha256'] != sha(SOURCE / 'summary.json'):
        raise ValueError('Audited source experiment required')
    for rel, digest in source_summary['files'].items():
        if sha(SOURCE / rel) != digest:
            raise ValueError('Component evidence changed')
    data = review_domain(pd.read_parquet(SOURCE / 'development_inputs.parquet'))
    groups = {name: set(ids) for name, ids in read(SOURCE / 'groups.json').items()}
    external = set().union(*groups.values())
    if len(external) != 9 or len(set(data.station)) != 23 or len(groups) != 4:
        raise ValueError('Existing 23 development stations and four groups required')
    signatures = {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__), ROOT / 'src/temperature_mean.py', CONFIG,
                  ROOT / 'src/temperature_transfer.py', ROOT / 'src/thermal_ice.py', SOURCE / 'summary.json', SOURCE / 'independent_verification.json']}
    labels_path = PRIVATE / 'daily_primary_transfer_20261009_v1/predictions.parquet'
    signatures[str(labels_path.relative_to(ROOT))] = sha(labels_path)
    out.mkdir(); shutil.copy2(Path(__file__), out / 'analysis_source.py'); shutil.copy2(ROOT / 'src/temperature_mean.py', out / 'mean_source.py')
    write(out / 'experiment_plan.json', config | {'started_at_utc': datetime.now(timezone.utc).isoformat(), 'new_independent_assessment': False})
    write(out / 'component_source_receipt.json', {'source_summary_sha256': sha(SOURCE / 'summary.json'), 'source_files': source_summary['files']})
    write(out / 'groups.json', {g: sorted(ids) for g, ids in groups.items()})
    decisions, parts = {}, []
    for group, held in groups.items():
        inner = review_domain(pd.read_parquet(SOURCE / group / 'inner_oof.parquet'))
        if set(inner.station) != external-held:
            raise ValueError('Inner population changed')
        inner[CANDIDATE] = equal_mean(inner[COMPONENTS[0]], inner[COMPONENTS[1]])
        reports = {name: regression_report(inner, inner[name]) for name in [COMPONENTS[0], CANDIDATE]}
        selected = select_temperature(reports, candidate_names=[CANDIDATE], maximum_station_harm=config['maximum_station_harm'])
        decision = dict(outer_group=group, selected_candidate=selected, excluded_stations=sorted(held),
                        selection_groups=sorted(set(groups)-{group}), outer_labels_used_for_selection=False, inner_reports=reports)
        folder = out / group; folder.mkdir(); write(folder / 'decision.json', decision)
        inner.to_parquet(folder / 'inner_oof.parquet', index=False, compression='zstd'); decisions[group] = decision
        outer = review_domain(pd.read_parquet(SOURCE / group / 'outer_predictions.parquet'))
        if set(outer.station) != held:
            raise ValueError('Outer population changed')
        outer = outer[['station', 'time', 'group', 'road_temp', *COMPONENTS]].copy()
        outer[CANDIDATE] = equal_mean(outer[COMPONENTS[0]], outer[COMPONENTS[1]])
        outer['selected_temperature'] = outer[selected]; outer['selected_candidate'] = selected
        outer.to_parquet(folder / 'outer_predictions.parquet', index=False, compression='zstd'); parts.append(outer)
        print(group, '선택:', selected, flush=True)
    combined = pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    combined.to_parquet(out / 'outer_predictions.parquet', index=False, compression='zstd')
    names = [*COMPONENTS, CANDIDATE, 'selected_temperature']
    reports = {name: regression_report(combined, combined[name]) for name in names}
    write(out / 'decisions.json', decisions)
    pd.DataFrame([dict(variant=n, station=s, **values) for n, report in reports.items() for s, values in report['stations'].items()]).to_csv(out / 'station_metrics.csv', index=False, encoding='utf-8-sig')
    labels = review_domain(pd.read_parquet(labels_path))
    moisture = combined[['station', 'time']].merge(data[['station', 'time', 'aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']], on=['station', 'time'], validate='one_to_one')
    classified = combined.merge(labels[['station', 'time', 'ice', 'baseline_prediction']], on=['station', 'time'], validate='one_to_one')
    if len(classified) != len(combined) or not classified[['station', 'time']].equals(moisture[['station', 'time']]):
        raise ValueError('Diagnostic alignment changed')
    ice = {}
    for name in names:
        p, fallback, _ = fixed_thermal_rule(classified[name].to_numpy(), moisture, classified.baseline_prediction.to_numpy(), True)
        classified['ice_'+name] = p
        report, stations, days, events = diagnostic_report(classified, p)
        ice[name] = report | {'fallback_rows': int(fallback.sum())}
        for suffix, frame in [('stations', stations), ('days', days), ('events', events)]:
            frame.to_csv(out / f'ice_{suffix}_{name}.csv', index=False, encoding='utf-8-sig')
    classified.to_parquet(out / 'ice_diagnostic_predictions.parquet', index=False, compression='zstd')
    diagnostics = component_error_diagnostics(combined, combined[COMPONENTS[0]], combined[COMPONENTS[1]])
    pd.DataFrame([dict(station=s, **component_error_diagnostics(part, part[COMPONENTS[0]], part[COMPONENTS[1]]))
                  for s, part in combined.groupby('station')]).to_csv(out / 'component_error_by_station.csv', index=False, encoding='utf-8-sig')
    if preservation() != freezes:
        raise ValueError('Assessment preservation changed')
    for rel, digest in signatures.items():
        if sha(ROOT / rel) != digest:
            raise ValueError('Input/source changed')
    write(out / 'input_signatures.json', signatures)
    result = dict(status='equal_mean_nested_development_complete', completed_at_utc=datetime.now(timezone.utc).isoformat(),
                  input_rows=len(data), outer_rows=len(combined), metrics=reports, ice_diagnostic=ice, component_error_diagnostics=diagnostics,
                  choices={g: d['selected_candidate'] for g, d in decisions.items()}, new_model_fits=0, weight_search_performed=False,
                  development_overall_temperature_gate_passed=select_temperature(reports, candidate_names=[CANDIDATE]) == CANDIDATE,
                  old_frozen_files=freezes[0], reserved_frozen_files=freezes[1], final_model_promoted=False,
                  protected_or_assessment_outcomes_used=False, files={p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*') if p.is_file()})
    write(out / 'summary.json', result)
    print(json.dumps({key:result[key] for key in ['status', 'new_model_fits', 'development_overall_temperature_gate_passed', 'choices']}))


if __name__ == '__main__':
    main()
