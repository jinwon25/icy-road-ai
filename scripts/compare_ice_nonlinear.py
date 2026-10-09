"""Paired classification diagnostics; never selects thresholds on outer labels."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.metrics import average_precision_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validation import assert_training_stations, binary_metrics, daily_scores, macro_scores
from src.ice_event_metrics import event_metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    private = ROOT / 'outputs/private'
    nonlinear = pd.read_parquet(private / ('smoke_ice_nonlinear' if args.smoke else 'ice_nonlinear') / 'predictions.parquet')
    baseline = pd.read_parquet(private / 'ice_fallback_logistic/predictions.parquet')
    for data in (nonlinear, baseline):
        data['station'] = data.station.astype(str)
        assert_training_stations(data.station.unique())
    if args.smoke:
        baseline = baseline.loc[baseline.station.isin(nonlinear.station.unique())].copy()
    paired = baseline.merge(nonlinear, on=['station', 'time'], how='outer',
                            suffixes=('_logistic', '_hgb'), indicator=True, validate='one_to_one')
    if not paired._merge.eq('both').all() or not paired.ice_logistic.equals(paired.ice_hgb):
        raise ValueError('Target rows or truth differ')
    paired['pred_none'] = 0
    variants = {'logistic_slot': ('predicted_ice', 'model_score_logistic'),
                'hgb_slot': ('pred_slot', 'model_score_hgb'),
                'hgb_daily': ('pred_daily', 'model_score_hgb'),
                'always_nonice': ('pred_none', None)}
    station_rows, day_frames, state_rows, summaries = [], [], [], {}
    valid = paired.loc[paired.ice_logistic.notna()].copy()
    for variant, (prediction_col, score_col) in variants.items():
        records = [(row.station, row.time, int(row.ice_logistic) if pd.notna(row.ice_logistic) else None,
                    int(getattr(row, prediction_col))) for row in paired.itertuples(index=False)]
        daily = daily_scores(records, minimum_coverage=1.0)
        table = pd.DataFrame(daily)
        for column in ('tp', 'fp', 'fn', 'tn', 'precision', 'recall', 'f1'):
            table[column] = pd.to_numeric(table[column], errors='coerce').astype(float)
        table['variant'] = variant
        day_frames.append(table)
        accepted = table.loc[table.accepted]
        fixed = accepted.loc[(accepted.tp + accepted.fn).gt(0)]
        nonice = accepted.loc[(accepted.tp + accepted.fn).eq(0)]
        per_station = []
        for station, part in valid.groupby('station'):
            metrics = binary_metrics(part.ice_logistic.astype(int), part[prediction_col].astype(int))
            pday = [row for row in daily if row['station'] == station]
            fixed_station = fixed.loc[fixed.station.eq(station)]
            row = {'variant': variant, 'station': station, 'positive_slots': int(part.ice_logistic.sum()),
                   **metrics, 'daily_station_f1': macro_scores(pday)['f1'],
                   'fixed_ice_day_f1': float(fixed_station.f1.mean()) if len(fixed_station) else None,
                   'false_alarm_nonice_days': int(nonice.loc[nonice.station.eq(station)].fp.gt(0).sum()),
                   'average_precision': float(average_precision_score(part.ice_logistic, part[score_col]))
                                        if score_col and part.ice_logistic.sum() else None}
            per_station.append(row)
            station_rows.append(row)
        per_station = pd.DataFrame(per_station)
        for state, part in valid.groupby('state_raw_hgb'):
            state_rows.append({'variant': variant, 'state_raw': state,
                               **binary_metrics(part.ice_logistic.astype(int), part[prediction_col].astype(int))})
        # Date coverage sensitivity is diagnostic, not a second official metric.
        partial = daily_scores(records, minimum_coverage=1 / 144)
        winter = {}
        for year in (2024, 2025):
            start, end = pd.Timestamp(f'{year}-11-01'), pd.Timestamp(f'{year+1}-03-01')
            part = valid.loc[valid.time.ge(start) & valid.time.lt(end)]
            winter[str(year)] = binary_metrics(part.ice_logistic.astype(int), part[prediction_col].astype(int))
        summaries[variant] = {
            'slot_micro': binary_metrics(valid.ice_logistic.astype(int), valid[prediction_col].astype(int)),
            'exact_episode_diagnostic': event_metrics(paired, observed='ice_logistic', predicted=prediction_col),
            'daily_station_macro': macro_scores(daily),
            'fixed_observed_ice_days': len(fixed),
            'fixed_ice_day_f1_equal_days': float(fixed.f1.mean()),
            'fixed_ice_day_f1_station_first': float(fixed.groupby('station').f1.mean().mean()),
            'false_alarm_nonice_days': int(nonice.fp.gt(0).sum()),
            'positive_stations': int(per_station.positive_slots.gt(0).sum()),
            'stations_with_true_positives': int(per_station.tp.gt(0).sum()),
            'macro_average_precision_positive_stations': float(per_station.average_precision.mean()) if score_col else None,
            'positive_slots_in_complete_days': int((accepted.tp + accepted.fn).sum()),
            'positive_slots_excluded_by_complete_day_policy': int(valid.ice_logistic.sum() - (accepted.tp + accepted.fn).sum()),
            'partial_day_sensitivity': macro_scores(partial),
            'winter_strata_not_temporal_holdout': winter}
    stations = pd.DataFrame(station_rows)
    # Paired station bootstrap on fixed observed-Ice days; exploratory, not a p-value.
    wide = stations.pivot(index='station', columns='variant', values='fixed_ice_day_f1').dropna()
    rng = np.random.default_rng(20260923)
    draws = rng.integers(0, len(wide), size=(2000, len(wide)))
    bootstrap = {}
    for variant in ('hgb_slot', 'hgb_daily'):
        delta = (wide[variant] - wide.logistic_slot).to_numpy()
        samples = delta[draws].mean(axis=1)
        bootstrap[variant] = {'positive_stations': len(wide), 'mean_delta': float(delta.mean()),
                              'percentile_95_interval': [float(x) for x in np.quantile(samples, [.025, .975])],
                              'limitations': 'Exploratory 2000 station resamples; shared LOSO training sets and few stations; not independent confirmation.'}
    source_config = json.loads((ROOT / 'config/data_source.json').read_text(encoding='utf-8'))
    summary = {'status': 'development_only_paired_nonlinear_comparison', 'smoke': args.smoke,
               'data_release': source_config['release'], 'archive_sha256': source_config['sha256'],
               'target_rows': len(paired), 'valid_label_rows': len(valid), 'ice_slots': int(valid.ice_logistic.sum()),
               'variants': summaries, 'fixed_positive_day_station_bootstrap': bootstrap,
               'limitations': ['Compare only within the pinned archive release.',
                               'Daily coverage and singly undefined precision/recall remain provisional.',
                               'Daily-macro threshold objective and candidate grid differ from pooled slot policy.',
                               'Threshold policies compared on the same fitted HGB scores; outer labels never tune thresholds.',
                               'Both winters participate in spatial training; winter strata are not forward validation.',
                               'Class-weighted scores are not calibrated probabilities.']}
    out = private / ('smoke_ice_nonlinear_comparison' if args.smoke else 'ice_nonlinear_comparison')
    out.mkdir(parents=True, exist_ok=True)
    stations.to_csv(out / 'station_metrics.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(state_rows).to_csv(out / 'raw_state_errors.csv', index=False, encoding='utf-8-sig')
    pd.concat(day_frames).to_csv(out / 'daily_metrics.csv', index=False, encoding='utf-8-sig')
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    labels = ['Logistic / slot', 'HGB / slot', 'HGB / daily']
    names = ['logistic_slot', 'hgb_slot', 'hgb_daily']
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), layout='constrained')
    for ax, field, title in zip(axes,
                               ['tp', 'fp', 'fixed_ice_day_f1_station_first'],
                               ['Detected Ice slots', 'False alarm slots', 'F1 on fixed Ice days\n(equal station weighting)']):
        values = [summaries[name]['slot_micro'][field] if field in ('tp', 'fp')
                  else summaries[name][field] for name in names]
        bars = ax.bar(labels, values, color=['#8d99ae', '#3b82a0', '#d77b42'])
        ax.bar_label(bars, fmt='%.4f' if field not in ('tp', 'fp') else '%.0f', padding=3)
        ax.set_title(title, fontsize=10)
        ax.tick_params(axis='x', labelrotation=25)
        ax.margins(y=.2)
        ax.spines[['top', 'right']].set_visible(False)
    fig.suptitle(f"Development-only Ice benchmark | {source_config['release']} data | thresholds from inner folds", fontsize=11)
    fig.savefig(out / 'tradeoffs.png', dpi=180)
    plt.close(fig)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
