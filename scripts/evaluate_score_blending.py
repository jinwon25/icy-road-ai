"""공간 제외가 일치하는 세 분류 점수와 AND/OR 규칙을 고정 결합한다."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.method_blending import domain, combine_binary, ice_guard
from src.thermal_ice import diagnostic_report
from src.joint_surface import THRESHOLDS, threshold_table, threshold_prediction
from scripts.evaluate_method_blending import read, write, preservation, CONFIG, PRIVATE

SOURCE = PRIVATE / 'joint_surface_20261009_v1'
DEFAULT = PRIVATE / 'score_blending_20261010_v1'
SCORE_COMPONENTS = {'equal_original_binary': ['baseline_score', 'binary_thermal_weather_score'],
                    'equal_original_joint': ['baseline_score', 'joint_surface_state_score'],
                    'equal_binary_joint': ['binary_thermal_weather_score', 'joint_surface_state_score'],
                    'equal_three_scores': ['baseline_score', 'binary_thermal_weather_score', 'joint_surface_state_score']}
RULES = ('original_and_thermal14', 'original_or_thermal14')


def context(excluded, signatures):
    path = SOURCE / 'contexts' / '__'.join(sorted(excluded)) / 'query_predictions.parquet'
    signatures[str(path.relative_to(ROOT))] = sha(path)
    provenance_path = path.parent / 'auxiliary_receipts.json'
    provenance = read(provenance_path)
    if set(provenance['forbidden_groups']) != set(excluded):
        raise ValueError('Classifier context exclusion differs')
    signatures[str(provenance_path.relative_to(ROOT))] = sha(provenance_path)
    for receipt in read(SOURCE / 'fit_receipts.json'):
        if receipt['kind'] == 'classifier' and set(receipt['context_groups']) == set(excluded):
            model_path = Path(receipt['model_path'])
            if sha(model_path) != receipt['model_sha256']:
                raise ValueError('Classifier model changed')
            signatures[str(model_path.relative_to(ROOT))] = sha(model_path)
    frame = domain(pd.read_parquet(path))
    if not set(frame.group) <= set(excluded):
        raise ValueError('Score query entered its base training groups')
    for name, columns in SCORE_COMPONENTS.items():
        values = frame[columns].to_numpy(float)
        usable = ~frame.fallback.to_numpy(bool)
        if not np.isfinite(values[usable]).all() or not ((values[usable] >= 0) & (values[usable] <= 1)).all():
            raise ValueError('Unusable or out-of-range classifier score')
        # 원본 점수는 fallback 행에서 모두 기존 점수를 보관한다.
        # 판정은 점수와 무관하게 기존 binary로 복귀하므로 그 유한 값을 유지한다.
        frame[name] = values.mean(axis=1)
    frame[RULES[0]] = combine_binary(frame.baseline_prediction, frame.thermal_moisture, 'and')
    frame[RULES[1]] = combine_binary(frame.baseline_prediction, frame.thermal_moisture, 'or')
    return frame


def choose_threshold(frame, name, baseline):
    table = threshold_table(frame, frame[name], frame.fallback, frame.baseline_prediction)
    feasible = table.loc[table.fp.le(baseline['fp']) & table.fn.le(baseline['fn'])]
    # FN 개선도 함께 요구한다. 불가능한 경우 FP 예산만 충족하는 최고 후보를 보고하되 적격 처리하지 않는다.
    pool = feasible if not feasible.empty else table.loc[table.fp.le(baseline['fp'])]
    if pool.empty:
        raise ValueError('No threshold with false-alarm budget')
    t = float(pool.sort_values(['fixed_ice_day_f1', 'f1', 'threshold'], ascending=False).iloc[0].threshold)
    return t, table, bool(len(feasible))


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, default=DEFAULT)
    out = parser.parse_args().output.resolve()
    if out.exists() or not out.is_relative_to(PRIVATE.resolve()):
        raise ValueError('New private experiment directory required')
    plan = read(CONFIG)
    if plan['score_blends'] != list(SCORE_COMPONENTS) or plan['rule_blends'] != list(RULES):
        raise ValueError('Pinned score/rule library differs')
    freezes = preservation(); audit = read(SOURCE / 'independent_verification.json')
    if audit['status'] != 'passed' or audit['summary_sha256'] != sha(SOURCE / 'summary.json'):
        raise ValueError('Audited source required')
    groups = read(PRIVATE / 'weather_distance_20261010_v1/groups.json')
    signatures = {str(p.relative_to(ROOT)): sha(p) for p in [CONFIG, Path(__file__), ROOT / 'scripts/evaluate_method_blending.py', ROOT / 'src/method_blending.py', ROOT / 'src/joint_surface.py', ROOT / 'src/thermal_ice.py', SOURCE / 'summary.json', SOURCE / 'independent_verification.json', SOURCE / 'fit_receipts.json', SOURCE / 'input_signature.json', PRIVATE / 'weather_distance_20261010_v1/groups.json']}
    cache = {tuple([g]): context([g], signatures) for g in groups}
    from itertools import combinations
    for pair in combinations(sorted(groups), 2):
        cache[pair] = context(pair, signatures)
    out.mkdir(); shutil.copy2(Path(__file__), out / 'analysis_source.py'); shutil.copy2(ROOT / 'src/method_blending.py', out / 'blending_source.py')
    write(out / 'experiment_plan.json', plan | {'started_at_utc': datetime.now(timezone.utc).isoformat(),
          'threshold_selection': '고정 403후보. 내부 FP/FN 예산의 후보를 실제 결빙일 F1·micro F1·임계값 내림차순으로 하나 선택. 모든 guard에 실패한 후보는 채택하지 않고 다른 임계값으로 재탐색하지 않음.',
          'new_independent_assessment': False})
    write(out / 'input_signatures.json', signatures); write(out / 'groups.json', groups)
    decisions, parts = {}, []
    for outer in groups:
        folder = out / outer; folder.mkdir()
        inner = pd.concat([cache[tuple(sorted([outer, other]))].loc[lambda f: f.group.eq(other)] for other in groups if other != outer], ignore_index=True)
        expected = set().union(*(set(groups[g]) for g in groups if g != outer))
        if set(inner.station) != expected:
            raise ValueError('Inner class population differs')
        base, bs, _, _ = diagnostic_report(inner, inner.baseline_prediction)
        candidate_reports, thresholds, guards = {}, {}, {}
        for name in [*SCORE_COMPONENTS, *RULES]:
            if name in SCORE_COMPONENTS:
                threshold, table, budget = choose_threshold(inner, name, base); thresholds[name] = threshold
                table.to_csv(folder / (name+'_thresholds.csv'), index=False)
                pred = threshold_prediction(inner[name], threshold, inner.fallback, inner.baseline_prediction)
            else:
                pred = inner[name].to_numpy(); budget = True
            inner['prediction_'+name] = pred
            report, stations, _, _ = diagnostic_report(inner, pred)
            eligible, checks = ice_guard(report, base, stations, bs)
            candidate_reports[name] = report; guards[name] = checks | {'threshold_fp_fn_feasible': budget, 'eligible': eligible and budget}
        eligible = [c for c in guards if guards[c]['eligible']]
        chosen = max(eligible, key=lambda c: (candidate_reports[c]['fixed_ice_day_f1'], candidate_reports[c]['f1'], c)) if eligible else 'original'
        decision = dict(outer_group=outer, selection_groups=sorted(set(groups)-{outer}), selected_candidate=chosen,
                        thresholds=thresholds, baseline_report=base, candidate_reports=candidate_reports, guards=guards, outer_labels_used_for_selection=False)
        write(folder / 'decision.json', decision); decisions[outer] = decision
        inner.to_parquet(folder / 'inner_predictions.parquet', index=False, compression='zstd')
        result = cache[(outer,)].copy()
        for name in SCORE_COMPONENTS:
            result['prediction_'+name] = threshold_prediction(result[name], thresholds[name], result.fallback, result.baseline_prediction)
            result['threshold_'+name] = thresholds[name]
        for name in RULES:
            result['prediction_'+name] = result[name]
        result['selected_candidate'] = chosen
        result['selected_prediction'] = result.baseline_prediction if chosen == 'original' else result['prediction_'+chosen]
        result.to_parquet(folder / 'outer_predictions.parquet', index=False, compression='zstd'); parts.append(result)
        print('결빙 내부 선택:', outer, chosen, flush=True)
    combined = pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    combined.to_parquet(out / 'outer_predictions.parquet', index=False, compression='zstd')
    policies = {'original': 'baseline_prediction', **{c: 'prediction_'+c for c in [*SCORE_COMPONENTS, *RULES]}, 'selected': 'selected_prediction'}
    metrics, station_frames, overall_guards = {}, {}, {}
    for name, column in policies.items():
        report, stations, days, events = diagnostic_report(combined, combined[column])
        metrics[name] = report; station_frames[name] = stations
        stations.to_csv(out / (name+'_stations.csv'), index=False); days.to_csv(out / (name+'_days.csv'), index=False); events.to_csv(out / (name+'_events.csv'), index=False)
    for name in policies:
        ok, checks = ice_guard(metrics[name], metrics['original'], station_frames[name], station_frames['original'])
        overall_guards[name] = checks | {'eligible': ok}
    mask = combined.ice.notna() & ~combined.fallback
    y = combined.loc[mask, 'ice'].to_numpy(); score_metrics = {}
    for c in ['baseline_score', 'binary_thermal_weather_score', 'joint_surface_state_score', *SCORE_COMPONENTS]:
        s = combined.loc[mask, c].to_numpy()
        score_metrics[c] = dict(n=len(y), positives=int(y.sum()), average_precision=float(average_precision_score(y, s)),
                                brier_descriptive=float(np.mean((s-y)**2)), probability_calibration_established=False)
    write(out / 'decisions.json', decisions)
    for rel, digest in signatures.items():
        if sha(ROOT / rel) != digest:
            raise ValueError('Original score evidence changed')
    if preservation() != freezes or len(THRESHOLDS) != 403 or metrics['original']['n'] != 155118:
        raise ValueError('Assessment seals or fixed denominators changed')
    summary = dict(status='fixed_score_and_rule_blending_development_complete', completed_at_utc=datetime.now(timezone.utc).isoformat(),
                   outer_rows=len(combined), new_model_fits=0, learned_score_weights=0, threshold_grid_rows=4*4*len(THRESHOLDS),
                   metrics=metrics, score_metrics=score_metrics, development_guards=overall_guards,
                   choices={g: d['selected_candidate'] for g, d in decisions.items()},
                   old_frozen_files=freezes[0], reserved_frozen_files=freezes[1], assessment_outcomes_used=False,
                   new_independent_assessment=False, model_promoted=False,
                   files={p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob('*')) if p.is_file()})
    write(out / 'summary.json', summary)
    print(json.dumps({'status': summary['status'], 'choices': summary['choices'], 'development_guards': {c: v['eligible'] for c, v in overall_guards.items()}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
