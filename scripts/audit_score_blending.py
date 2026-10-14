"""점수 평균·모든 임계값·내부 선택·AND/OR·사건 지표를 별도 계산한다."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.audit_temperature_blind_validation import reference_ice, compare, counts
from scripts.audit_joint_surface import independent_thresholds
from scripts.fresh_station_validation import old_freezes, verify_seal

SOURCES = {'equal_original_binary': ['baseline_score', 'binary_thermal_weather_score'],
           'equal_original_joint': ['baseline_score', 'joint_surface_state_score'],
           'equal_binary_joint': ['binary_thermal_weather_score', 'joint_surface_state_score'],
           'equal_three_scores': ['baseline_score', 'binary_thermal_weather_score', 'joint_surface_state_score']}
RULES = ['original_and_thermal14', 'original_or_thermal14']


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def guard(frame, column):
    candidate, baseline = reference_ice(frame, column), reference_ice(frame, 'baseline_prediction')
    positives_safe = True
    for _, station in frame.groupby('station'):
        a, b = counts(station, column), counts(station, 'baseline_prediction')
        if b['tp']+b['fn'] and a['tp'] < b['tp']:
            positives_safe = False
    metrics = ['f1', 'fixed_station_f1_zero_undefined', 'fixed_ice_day_f1', 'provisional_daily_station_f1']
    supported = all(candidate[k] is not None and baseline[k] is not None for k in metrics)
    checks = {'supported_metrics': supported, 'fp_nonincrease': candidate['fp'] <= baseline['fp'],
              'fn_nonincrease': candidate['fn'] <= baseline['fn'], 'every_positive_station_tp': positives_safe,
              'events_nonincrease_misses': candidate['detected_events'] >= baseline['detected_events'],
              'singles_nonincrease_misses': candidate['detected_single_slot_events'] >= baseline['detected_single_slot_events'],
              'f1_nonworse': supported and all(candidate[k]+1e-12 >= baseline[k] for k in metrics),
              'strict_improvement': supported and (candidate['fp'] < baseline['fp'] or candidate['fn'] < baseline['fn'] or any(candidate[k] > baseline[k]+1e-12 for k in metrics))}
    return candidate, checks


def verify_components(frame):
    for name, columns in SOURCES.items():
        # 행별 덧셈으로 생성 코드의 mean(axis=1)과 별개로 확인한다.
        expected = sum(frame[c].to_numpy()/len(columns) for c in columns)
        np.testing.assert_allclose(frame[name], expected, atol=1e-15, rtol=0)
    np.testing.assert_array_equal(frame[RULES[0]], (frame.baseline_prediction.eq(1) & frame.thermal_moisture.eq(1)).astype(int))
    np.testing.assert_array_equal(frame[RULES[1]], (frame.baseline_prediction.eq(1) | frame.thermal_moisture.eq(1)).astype(int))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, default=ROOT / 'outputs/private/score_blending_20261010_v2')
    out = parser.parse_args().experiment.resolve(); target = out / 'independent_verification.json'
    if not out.is_relative_to((ROOT / 'outputs/private').resolve()) or target.exists():
        raise ValueError('New private audit receipt required')
    summary = read(out / 'summary.json')
    for rel, digest in read(out / 'input_signatures.json').items():
        assert sha(ROOT / rel) == digest, rel
    for rel, digest in summary['files'].items():
        assert sha(out / rel) == digest, rel
    source = ROOT / 'outputs/private/joint_surface_20261009_v1'
    source_audit = read(out / 'component_reaudit.json')
    assert source_audit['status'] == 'passed' and source_audit['summary_sha256'] == sha(source / 'summary.json')
    groups = read(out / 'groups.json'); decisions = read(out / 'decisions.json'); parts = []; rows_verified = 0; grid_rows = 0
    for outer in groups:
        inner = pd.read_parquet(out / outer / 'inner_predictions.parquet'); result = pd.read_parquet(out / outer / 'outer_predictions.parquet')
        decision = decisions[outer]
        assert set(decision['selection_groups']) == set(groups)-{outer} and not decision['outer_labels_used_for_selection']
        original = pd.concat([pd.read_parquet(source / 'contexts' / '__'.join(sorted([outer, other])) / 'query_predictions.parquet').loc[lambda f: f.group.eq(other)] for other in groups if other != outer], ignore_index=True)
        pd.testing.assert_frame_equal(inner[original.columns], original)
        orig_outer = pd.read_parquet(source / 'contexts' / outer / 'query_predictions.parquet')
        pd.testing.assert_frame_equal(result[orig_outer.columns], orig_outer)
        for frame in [inner, result]:
            verify_components(frame); rows_verified += len(frame)
            assert set(frame.station) <= set('12103 12209 12210 12211 12409 23202 23203 23204 23403 33103 33206 33409 33410 33412 12207 12408 23205 23404 33205 33408 33207 33413 33414'.split())
            assert frame.time.ge('2024-11-01').all() and frame.time.lt('2025-03-01').all()
            numeric = pd.to_numeric(frame.state_raw, errors='coerce')
            labels = np.where(numeric.eq(4), 1., np.where(numeric.isin([1, 2, 3, 10, 11, 12, 13, 14, 15]), 0., np.nan))
            np.testing.assert_allclose(frame.ice, labels, rtol=0, atol=0, equal_nan=True)
        base = reference_ice(inner, 'baseline_prediction'); compare(base, decision['baseline_report'])
        for name in [*SOURCES, *RULES]:
            budget = True
            if name in SOURCES:
                table = independent_thresholds(inner, inner[name], inner.fallback, inner.baseline_prediction)
                saved = pd.read_csv(out / outer / (name+'_thresholds.csv'))
                for c in table.columns:
                    np.testing.assert_allclose(table[c], saved[c], atol=1e-12, rtol=0)
                grid_rows += len(table)
                feasible = table.loc[(table.fp <= base['fp']) & (table.fn <= base['fn'])]
                budget = bool(len(feasible)); pool = feasible if budget else table.loc[table.fp <= base['fp']]
                threshold = float(pool.sort_values(['fixed_ice_day_f1', 'f1', 'threshold'], ascending=False).iloc[0].threshold)
                np.testing.assert_allclose(threshold, decision['thresholds'][name], atol=1e-15, rtol=0)
                for frame in [inner, result]:
                    expected = np.where(frame.fallback, frame.baseline_prediction, frame[name].ge(threshold)).astype(int)
                    np.testing.assert_array_equal(frame['prediction_'+name], expected)
            else:
                for frame in [inner, result]:
                    np.testing.assert_array_equal(frame['prediction_'+name], frame[name])
            report, checks = guard(inner, 'prediction_'+name)
            compare(report, decision['candidate_reports'][name])
            compare(checks | {'threshold_fp_fn_feasible': budget, 'eligible': all(checks.values()) and budget}, decision['guards'][name])
        eligible = [c for c in decision['guards'] if decision['guards'][c]['eligible']]
        chosen = max(eligible, key=lambda c: (decision['candidate_reports'][c]['fixed_ice_day_f1'], decision['candidate_reports'][c]['f1'], c)) if eligible else 'original'
        assert chosen == decision['selected_candidate']
        np.testing.assert_array_equal(result.selected_prediction, result.baseline_prediction if chosen == 'original' else result['prediction_'+chosen])
        parts.append(result); print('점수·임계값 검산:', outer, flush=True)
    combined = pd.read_parquet(out / 'outer_predictions.parquet')
    pd.testing.assert_frame_equal(combined, pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True))
    policies = {'original': 'baseline_prediction', **{c: 'prediction_'+c for c in [*SOURCES, *RULES]}, 'selected': 'selected_prediction'}
    for name, column in policies.items():
        report, checks = guard(combined, column)
        compare(report, summary['metrics'][name]); compare(checks | {'eligible': all(checks.values())}, summary['development_guards'][name])
    mask = combined.ice.notna() & ~combined.fallback
    for c, r in summary['score_metrics'].items():
        y, scores = combined.loc[mask, 'ice'].to_numpy(), combined.loc[mask, c].to_numpy()
        compare(dict(n=len(y), positives=int(y.sum()), average_precision=float(average_precision_score(y, scores)), brier_descriptive=float(np.mean((scores-y)**2)), probability_calibration_established=False), r)
    # 논리 결합의 FP/FN 단조성을 실데이터에서도 검산한다.
    base, both, either = [summary['metrics'][c] for c in ['original', *RULES]]
    assert both['fp'] <= base['fp'] <= either['fp'] and both['fn'] >= base['fn'] >= either['fn']
    freezes = old_freezes()
    for name in ['fresh_station_validation_20261009_v2', 'temperature_blind_20261010_v1', 'temperature_mean_blind_20261010_v1']:
        verify_seal(ROOT / 'outputs/private' / name)
    assert grid_rows == 6448 and rows_verified == 621028
    audit = dict(status='independent_score_rule_blending_audit_passed', audited_at_utc=datetime.now(timezone.utc).isoformat(),
                 summary_sha256=sha(out / 'summary.json'), component_reaudit_sha256=sha(out / 'component_reaudit.json'),
                 audit_source_sha256=sha(Path(__file__)), combined_rows_verified=rows_verified, threshold_grid_rows_verified=grid_rows,
                 decisions_verified=4, ice_policies_verified=8, old_frozen_files=freezes[0], reserved_frozen_files=freezes[1], model_promoted=False)
    with target.open('x', encoding='utf-8') as f:
        json.dump(audit, f, indent=2, allow_nan=False)
    print(json.dumps(audit))


if __name__ == '__main__':
    main()
