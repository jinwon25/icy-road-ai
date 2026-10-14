"""새 Q&A633 기준으로 기존 개발 판정만 재집계한다. 재학습·임계값 변경 없음."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.qa633_metrics import daily_table, aggregate
from scripts.evaluate_method_blending import read, write, preservation

PRIVATE = ROOT / 'outputs/private'
OUT = PRIVATE / 'qa633_development_20261013_v1'
CONFIG = ROOT / 'config/official_requirements_20261013_v2.json'
SOURCES = [
    ('controls', 'weather_memory_controls_20261013_v1', 'ice_predictions.parquet', ['nohistory12_mse300', 'nohistory12_mae300', 'equal_nohistory_pair', 'equal_trio_nohistory', 'selected_control']),
    ('memory', 'weather_memory_temperature_20261013_v2', 'ice_predictions.parquet', ['equal_distance_mse_mae300', 'memory12_mse300', 'memory12_mae300', 'equal_memory_pair', 'equal_trio_memory', 'selected_temperature']),
    ('classifier', 'ice_methodology_20261010_v1', 'outer_predictions.parquet', ['original', 'thermal14', 'hgb_long300', 'hgb_no_distance', 'hgb_history', 'hgb_balanced', 'catboost400', 'hurdle_non_dry', 'binary100_control', 'classifier_selected']),
]


def columns(kind, methods):
    if kind in ('controls', 'memory'): return {name: 'ice_'+name for name in methods}
    return {name: {'original': 'baseline_prediction', 'thermal14': 'thermal_moisture', 'classifier_selected': 'selected_prediction'}.get(name, 'prediction_'+name) for name in methods}


def main():
    if OUT.exists(): raise FileExistsError('Preserve new daily-policy report')
    official = read(CONFIG); assert official['evaluation']['qa633_answer_present']
    freeze = preservation(); OUT.mkdir()
    pinned = [Path(__file__), ROOT / 'src/qa633_metrics.py', ROOT / 'src/validation.py', ROOT / 'src/method_blending.py', CONFIG,
              PRIVATE / 'official_updates_20261013_v2/answer_changes.json', PRIVATE / 'official_updates_20261013_v2/complete_review.json']
    frame = None; old_reports = {}; source_records = {}
    for kind, name, filename, methods in SOURCES:
        folder = PRIVATE / name; summary = read(folder / 'summary.json'); audit = read(folder / 'independent_verification.json')
        assert audit['summary_sha256'] == sha(folder / 'summary.json')
        path = folder / filename; assert sha(path) == summary['files'][filename]
        pinned.extend([path, folder / 'summary.json', folder / 'independent_verification.json'])
        mapping = columns(kind, methods)
        source = pd.read_parquet(path, columns=['station', 'time', 'ice', *mapping.values()]).sort_values(['station', 'time']).reset_index(drop=True)
        if frame is None: frame = source[['station', 'time', 'ice']].copy()
        else: pd.testing.assert_frame_equal(frame[['station', 'time', 'ice']], source[['station', 'time', 'ice']])
        for name, col in mapping.items():
            assert name not in frame; frame[name] = source[col].to_numpy()
            old = summary['ice_diagnostic'][name] if kind != 'classifier' else summary['metrics']['selected' if name == 'classifier_selected' else name]
            old_reports[name] = old
            source_records[name] = dict(source=str(path.relative_to(ROOT)), column=col, source_summary_sha256=sha(folder / 'summary.json'), predictions_changed=False)
    assert len(frame) == 155257 and frame.ice.notna().sum() == 155118
    frame.to_parquet(OUT / 'fixed_predictions.parquet', index=False, compression='zstd')
    pop = sorted(frame.station.unique()); methods = list(source_records); reports = {}; day_parts, station_parts, biases = [], [], []
    for name in methods:
        reports[name] = {}
        for minimum in [144, 130, 72, 1]:
            days = daily_table(frame, frame[name], pop, minimum); report, stations = aggregate(days, pop)
            reports[name][str(minimum)] = report
            days['method'] = name; days['minimum_valid_slots'] = minimum; day_parts.append(days)
            stations['method'] = name; stations['minimum_valid_slots'] = minimum; station_parts.append(stations)
            if minimum == 144:
                # 기존에 잠정으로 부른 전일·지점 F1과 수치가 같음을 확인한다.
                assert abs(report['f1_available_station_mean']-old_reports[name]['provisional_daily_station_f1']) < 1e-12
                joint = days.loc[days.coverage_accepted & days.actual_ice_slots.gt(0) & days.predicted_ice_slots.gt(0)]
                wrong = joint.groupby('station').f1.mean()
                biases.append(dict(method=name, correct_f1=report['f1_available_station_mean'],
                    wrong_joint_defined_f1=float(wrong.mean()) if len(wrong) else None,
                    wrongly_excluded_missed_days=report['miss_only_days'], wrongly_excluded_false_alarm_days=report['false_alarm_only_days'],
                    precision_days=report['precision_days'], recall_days=report['recall_days'], f1_days=report['f1_days']))
        print(name, reports[name]['144']['f1_available_station_mean'], 'P/R/F1 days', *[reports[name]['144'][m+'_days'] for m in ['precision', 'recall', 'f1']], flush=True)
    pd.concat(day_parts, ignore_index=True).to_csv(OUT / 'research_daily_metrics.csv', index=False)
    pd.concat(station_parts, ignore_index=True).to_csv(OUT / 'research_station_metrics.csv', index=False)
    pd.DataFrame(biases).to_csv(OUT / 'wrong_intersection_comparison.csv', index=False)
    write(OUT / 'source_records.json', source_records); write(OUT / 'input_signatures.json', {str(p.relative_to(ROOT)): sha(p) for p in pinned})
    write(OUT / 'analysis_plan.json', dict(policy='qa633_20261013_metricwise_average', min_valid_slots=[144, 130, 72, 1],
        primary_coverage_threshold=144, coverage_threshold_is_provisional=True, new_model_fits=0, changed_thresholds=0,
        scope='固定済み開発予測' if False else '기존 첫 겨울9개 개발 지점의 고정 판정21종 재집계',
        csv_schema='연구용 분모·일별·지점별 검산 표. 주최 측의 최종 CSV규격이 아님.',
        assessment_outcomes_used=False, new_independent_assessment=False, official_competition_score=False))
    assert preservation() == freeze
    result = dict(status='qa633_fixed_development_metrics_complete', completed_at_utc=datetime.now(timezone.utc).isoformat(), methods=methods,
        population=pop, rows=len(frame), valid_rows=int(frame.ice.notna().sum()), reports=reports, previous_f1_unchanged=True,
        new_model_fits=0, changed_thresholds=0, assessment_outcomes_used=False, official_competition_score=False,
        old_frozen_files=freeze[0], reserved_frozen_files=freeze[1],
        files={p.relative_to(OUT).as_posix(): sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()})
    write(OUT / 'summary.json', result)


if __name__ == '__main__': main()
