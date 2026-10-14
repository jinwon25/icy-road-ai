"""기존 점수의 공식 지점별 일평균 F1 임계값 이전을 새 개발 버전에서 진단한다."""
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
from src.data_source import sha256_file
from src.external_reserved import verify_reserved_freeze
from src.frozen_assessment import verify_freeze
from src.ice_daily_selection import choose_daily_threshold
from src.ice_event_metrics import event_metrics
from src.temperature_transfer import validate_development
from src.validation import binary_metrics, daily_scores, macro_scores

PLAN = {
    'experiment_id': '20261009_daily_primary_threshold_transfer_v1',
    'scope': '기존 첫 겨울 9개 지점의 반복 개발 비교. 새 독립 평가·공식 점수가 아님.',
    'model': '기존 대회14 전용 HGB 점수 그대로. 추가9·평가그룹 정답은 모델 학습에 쓰지 않음.',
    'threshold_grid': '0, 고정 401개 logspace(1e-6,1), nextafter(1,+inf)',
    'policies': ['daily_primary', 'daily_primary_fp_budget'],
    'primary': '완전일별 F1 -> 지점 평균 -> 지점 단순 평균. 무실제·무예측 결빙일 제외.',
    'budget': '다른3 내부그룹의 음성 시점 FP율이 기존 임계값보다 높아지지 않도록 제한.',
    'ties': '1e-12 이내 동률이면 높은 임계값',
    'unresolved': '부분 날짜·한쪽 미정의 Precision/Recall 정책은 잠정. 무정의 지점의 제외 효과도 함께 보고.',
    'safety_diagnostics': '동일 유효행, 고정 실제 결빙일, 고정 지점의 null=0 F1, 단일 사건, 지점별 Recall, 음성일 오경보.',
    'promotion': False,
    'protected_or_reserved_outcomes_used': False,
}


def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)


def select_inner_threshold(frame, held_stations, budget=False):
    """이미 제외한 내부 OOF만 받으며 외부 지점이 섞이면 중단한다."""
    validate_development(frame)
    if set(frame.station) & set(held_stations):
        raise ValueError('Outer outcomes entered threshold selection')
    valid = frame.loc[frame.ice.isin([0, 1])].copy()
    thresholds = np.r_[0., np.logspace(-6, 0, 401), np.nextafter(1., np.inf)]
    _, _, trace = choose_daily_threshold(valid, valid.baseline_score, thresholds)
    negatives = np.sort(valid.loc[valid.ice.eq(0), 'baseline_score'].to_numpy())
    if not len(negatives): raise ValueError('No negative comparison rows')
    trace['fpr'] = (len(negatives) - np.searchsorted(negatives, trace.threshold, side='left')) / len(negatives)
    limit = float(valid.loc[valid.ice.eq(0), 'baseline_prediction'].mean())
    feasible = trace.loc[trace.fpr.le(limit + 1e-12)] if budget else trace
    top = feasible.loc[np.isclose(feasible.station_daily_f1, feasible.station_daily_f1.max(), rtol=0, atol=1e-12)]
    chosen = top.sort_values('threshold').iloc[-1]
    return float(chosen.threshold), trace, limit


def report(frame, predictions):
    frame = frame.copy(); frame['predicted_ice'] = np.asarray(predictions, dtype=int)
    records = [(r.station, r.time, int(r.ice) if pd.notna(r.ice) else None, int(r.predicted_ice))
               for r in frame.itertuples()]
    days = daily_scores(records)
    table = pd.DataFrame(days)
    accepted = table.loc[table.accepted].copy()
    actual = accepted.loc[(accepted.tp + accepted.fn).gt(0)]
    fixed = accepted.groupby('station').f1.mean().reindex(sorted(frame.station.unique())).astype(float).fillna(0)
    all_events = event_metrics(frame)
    # 독립 단일 양성은 관측 공백·음성·미정의로 구분하며 정답을 수정하지 않는다.
    singleton_tp = singleton_events = 0
    station_rows = []
    for st, part in frame.groupby('station'):
        part = part.sort_values('time')
        active = part.ice.eq(1)
        contiguous = part.time.diff().eq(pd.Timedelta(minutes=10))
        starts = active & ~(active.shift(fill_value=False) & contiguous)
        event = starts.cumsum()
        size = event[active].value_counts()
        single = active & event.map(size).eq(1)
        singleton_events += int(single.sum())
        singleton_tp += int((single & part.predicted_ice.eq(1)).sum())
        station_rows.append({'station': str(st), **binary_metrics(part.ice, part.predicted_ice)})
    return {'slot': binary_metrics(frame.ice, frame.predicted_ice), 'daily': macro_scores(days),
            'fixed_station_daily_f1_undefined_zero': float(fixed.mean()),
            'actual_ice_day_f1': float(actual.groupby('station').f1.mean().mean()) if len(actual) else None,
            'actual_ice_days': len(actual), 'accepted_nonice_days': int((accepted.tp + accepted.fn).eq(0).sum()),
            'false_alarm_nonice_days': int(((accepted.tp + accepted.fn).eq(0) & accepted.fp.gt(0)).sum()),
            'events': {**all_events, 'singleton_events': singleton_events, 'singleton_detected': singleton_tp},
            'stations': station_rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'outputs/private/daily_primary_transfer_20261009_v1')
    args = parser.parse_args(); out = args.output.resolve()
    if not out.is_relative_to((ROOT / 'outputs/private').resolve()): raise ValueError('Private output required')
    if out.exists(): raise FileExistsError('Preserve completed run; choose new version')
    release = ROOT / 'outputs/private/releases/20261007'; private = release / 'outputs/private'
    sources = {'scores': ROOT / 'outputs/private/ice_group_balanced_20261009_v1/outer_predictions.parquet',
               'baseline': private / 'external_augmentation_nested_v1/baseline/fit_manifest.json',
               'groups': release / 'config/kma_external_validation_plan.json',
               'runner': Path(__file__), 'selector': ROOT / 'src/ice_daily_selection.py'}
    frozen = verify_reserved_freeze(release, private / 'external_reserved_predictions_v1')
    original = verify_freeze(release)
    frame = pd.read_parquet(sources['scores']); validate_development(frame)
    groups = {k: set(v) for k, v in read(sources['groups'])['station_groups'].items()}
    if set(frame.station) != set().union(*groups.values()): raise ValueError('Pinned development population required')
    threshold = read(sources['baseline'])['threshold']
    if not np.array_equal(frame.baseline_prediction, (frame.baseline_score >= threshold).astype(int)):
        raise ValueError('Original prediction changed')
    out.mkdir(); write(out / 'experiment_plan.json', PLAN)
    write(out / 'input_signature.json', {k: {'path': str(p), 'sha256': sha256_file(p)} for k, p in sources.items()})
    shutil.copy2(__file__, out / 'analysis_source.py')
    decision_rows = []
    frame['daily_primary'] = -1; frame['daily_primary_fp_budget'] = -1
    for outer, held in groups.items():
        check = frame.station.isin(held)
        inner = frame.loc[~check].copy()
        for policy in PLAN['policies']:
            selected, trace, limit = select_inner_threshold(inner, held, budget=policy.endswith('budget'))
            trace.to_csv(out / (outer + '__' + policy + '__threshold_trace.csv'), index=False)
            decision = {'outer_group': outer, 'policy': policy, 'threshold': selected,
                        'excluded_stations': sorted(held), 'selection_stations': sorted(inner.station.unique()),
                        'inner_fpr_budget': limit, 'outer_outcomes_used_for_selection': False,
                        'inner_report': report(inner, (inner.baseline_score >= selected).astype(int))}
            write(out / (outer + '__' + policy + '__decision.json'), decision)
            frame.loc[check, policy] = (frame.loc[check, 'baseline_score'] >= selected).astype(int)
            decision_rows.append(decision)
    metrics = {'original': report(frame, frame.baseline_prediction)}
    for policy in PLAN['policies']: metrics[policy] = report(frame, frame[policy])
    frame[['station', 'time', 'ice', 'baseline_score', 'baseline_prediction', *PLAN['policies']]].to_parquet(out / 'predictions.parquet', index=False)
    rows = [{'policy': policy, **row} for policy, r in metrics.items() for row in r['stations']]
    pd.DataFrame(rows).to_csv(out / 'station_metrics.csv', index=False, encoding='utf-8-sig')
    if verify_reserved_freeze(release, private / 'external_reserved_predictions_v1') != frozen or verify_freeze(release) != original:
        raise ValueError('Frozen assessment changed')
    summary = {'status': 'daily_primary_transfer_diagnostic_complete', 'plan': PLAN, 'metrics': metrics,
               'thresholds': [{k: r[k] for k in ['outer_group', 'policy', 'threshold']} for r in decision_rows],
               'created_at_utc': datetime.now(timezone.utc).isoformat(),
               'frozen_external_files': len(frozen['files']), 'frozen_original_files': len(original['files']),
               'files': {p.relative_to(out).as_posix(): sha256_file(p) for p in out.rglob('*') if p.is_file()}}
    write(out / 'summary.json', summary)
    print(json.dumps({'metrics': {k: {m: v[m] for m in ['slot', 'daily', 'actual_ice_day_f1', 'false_alarm_nonice_days', 'events']}
                                  for k, v in metrics.items()}, 'thresholds': summary['thresholds']}, ensure_ascii=False), flush=True)


if __name__ == '__main__': main()
