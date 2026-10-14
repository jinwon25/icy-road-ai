"""일별 임계값 이전의 모든 탐색 지점을 날짜별 정렬·독립 집계로 검산한다."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file


def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))


def reference_trace(frame, thresholds):
    valid = frame.loc[frame.ice.isin([0, 1])].copy()
    valid['day'] = valid.time.dt.date
    daily = {}; day_count = np.zeros(len(thresholds), dtype=int)
    for (st, _), part in valid.groupby(['station', 'day']):
        if len(part) != 144: continue
        pos = np.sort(part.loc[part.ice.eq(1), 'baseline_score'].to_numpy())
        neg = np.sort(part.loc[part.ice.eq(0), 'baseline_score'].to_numpy())
        tp = len(pos) - np.searchsorted(pos, thresholds, side='left')
        fp = len(neg) - np.searchsorted(neg, thresholds, side='left')
        denominator = len(pos) + tp + fp
        f1 = np.full(len(thresholds), np.nan)
        np.divide(2 * tp, denominator, out=f1, where=denominator > 0)
        daily.setdefault(st, []).append(f1)
        day_count += np.isfinite(f1)
    station_means = []
    for values in daily.values():
        values = np.array(values); count = np.isfinite(values).sum(axis=0)
        station_means.append(np.divide(np.nansum(values, axis=0), count,
                                       out=np.full(len(thresholds), np.nan), where=count > 0))
    means = np.array(station_means); supported = np.isfinite(means).sum(axis=0)
    macro = np.divide(np.nansum(means, axis=0), supported, out=np.zeros(len(thresholds)), where=supported > 0)
    negative = np.sort(valid.loc[valid.ice.eq(0), 'baseline_score'].to_numpy())
    all_scores = np.sort(valid.baseline_score.to_numpy())
    return {'station_daily_f1': macro, 'defined_days': day_count, 'defined_stations': supported,
            'fpr': (len(negative) - np.searchsorted(negative, thresholds, side='left')) / len(negative),
            'predicted_slots': len(all_scores) - np.searchsorted(all_scores, thresholds, side='left')}


def reference_events(frame, prediction):
    total = {'observed_events': 0, 'detected_events': 0, 'predicted_events': 0,
             'false_alarm_events': 0, 'max_predicted_event_slots': 0,
             'singleton_events': 0, 'singleton_detected': 0}
    data = frame.copy(); data['prediction'] = prediction
    for _, part in data.groupby('station'):
        rows = list(part.sort_values('time').itertuples())
        for gold_side in [True, False]:
            episodes = []; episode = []; previous = None
            for row in rows:
                active = row.ice in [0, 1] and (row.ice == 1 if gold_side else row.prediction == 1)
                if not active or (previous is not None and row.time - previous != pd.Timedelta(minutes=10)):
                    if episode: episodes.append(episode); episode = []
                if active: episode.append(row)
                previous = row.time
            if episode: episodes.append(episode)
            for episode in episodes:
                match = any((r.prediction if gold_side else r.ice) == 1 for r in episode)
                if gold_side:
                    total['observed_events'] += 1; total['detected_events'] += int(match)
                    if len(episode) == 1:
                        total['singleton_events'] += 1; total['singleton_detected'] += int(match)
                else:
                    total['predicted_events'] += 1; total['false_alarm_events'] += int(not match)
                    total['max_predicted_event_slots'] = max(total['max_predicted_event_slots'], len(episode))
    total['event_recall'] = total['detected_events'] / total['observed_events'] if total['observed_events'] else None
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True, type=Path)
    args = parser.parse_args(); out = args.experiment.resolve()
    if not out.is_relative_to((ROOT / 'outputs/private').resolve()): raise ValueError('Private experiment required')
    if (out / 'independent_verification.json').exists(): raise FileExistsError('Preserve prior audit')
    summary = read(out / 'summary.json')
    for rel, digest in summary['files'].items():
        path = (out / rel).resolve()
        if not path.is_relative_to(out) or sha256_file(path) != digest: raise ValueError('Artifact changed')
    for name, source in read(out / 'input_signature.json').items():
        path = out / 'analysis_source.py' if name == 'runner' else Path(source['path'])
        if sha256_file(path) != source['sha256']: raise ValueError('Input changed')
    frame = pd.read_parquet(out / 'predictions.parquet'); checks = 0
    for item in summary['thresholds']:
        outer, policy = item['outer_group'], item['policy']
        decision = read(out / (outer + '__' + policy + '__decision.json'))
        inner = frame.loc[frame.station.isin(decision['selection_stations'])]
        if set(inner.station) & set(decision['excluded_stations']): raise ValueError('Outer selection leak')
        trace = pd.read_csv(out / (outer + '__' + policy + '__threshold_trace.csv'))
        reference = reference_trace(inner, trace.threshold.to_numpy())
        for col, values in reference.items(): np.testing.assert_allclose(trace[col], values, rtol=0, atol=1e-12)
        feasible = reference['fpr'] <= decision['inner_fpr_budget'] + 1e-12 if policy.endswith('budget') else np.ones(len(trace), bool)
        maximum = reference['station_daily_f1'][feasible].max()
        selected = trace.loc[feasible & np.isclose(reference['station_daily_f1'], maximum, rtol=0, atol=1e-12), 'threshold'].max()
        np.testing.assert_allclose(selected, decision['threshold'], rtol=0, atol=1e-12)
        held = frame.station.isin(decision['excluded_stations'])
        np.testing.assert_array_equal(frame.loc[held, policy], (frame.loc[held, 'baseline_score'] >= decision['threshold']).astype(int))
        checks += len(trace)
    for policy, metrics in summary['metrics'].items():
        pred = frame.baseline_prediction if policy == 'original' else frame[policy]
        y = frame.ice.to_numpy(); p = pred.to_numpy(); valid = np.isin(y, [0, 1])
        counts = {'tp': int(((y == 1) & (p == 1)).sum()), 'fp': int(((y == 0) & (p == 1)).sum()),
                  'fn': int(((y == 1) & (p == 0)).sum()), 'tn': int(((y == 0) & (p == 0)).sum()), 'n': int(valid.sum())}
        for key, value in counts.items():
            if metrics['slot'][key] != value: raise ValueError('Confusion count differs')
        events = reference_events(frame, p)
        for key, value in events.items():
            if value != metrics['events'][key]: raise ValueError('Independent event count differs')
    result = {'status': 'independent_daily_threshold_audit_passed', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'threshold_points_recomputed': checks, 'decisions': len(summary['thresholds']),
              'event_policies': len(summary['metrics']), 'valid_state_rows': int(frame.ice.isin([0, 1]).sum()),
              'summary_sha256': sha256_file(out / 'summary.json'), 'new_independent_outcome_evaluation': False}
    with (out / 'independent_verification.json').open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__': main()
