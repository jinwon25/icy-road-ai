from itertools import product
import numpy as np
import pandas as pd
import pytest
from src.exact_daily_threshold import select_exact_thresholds


def brute(frame, scores, threshold, minimum):
    f = frame.copy(); f['p'] = np.asarray(scores) >= threshold
    f = f.loc[np.isfinite(scores) & f.ice.notna()]
    records = []
    for (station, day), g in f.groupby(['station', f.time.dt.normalize()]):
        tp = int((g.ice.eq(1) & g.p).sum()); fp = int((g.ice.eq(0) & g.p).sum()); fn = int((g.ice.eq(1) & ~g.p).sum())
        if len(g) >= minimum and 2*tp+fp+fn:
            records.append((station, int(g.winter.iloc[0]), 2*tp/(2*tp+fp+fn)))
    def metric(year):
        pop = frame if year is None else frame.loc[frame.winter.eq(year)]
        values = []
        for station in pop.station.unique():
            v = [r[2] for r in records if r[0] == station and (year is None or r[1] == year)]
            values.append(np.mean(v) if v else 0)
        return float(np.mean(values))
    return metric(None), min(metric(2024), metric(2025)), int((f.ice.eq(0) & f.p).sum())


@pytest.mark.parametrize('seed', [11, 17, 29])
def test_exact_sweep_matches_brute_force_every_unique_threshold(seed):
    rows = []
    for station, winter in product(['a', 'b'], [2024, 2025]):
        for i in range(36):
            rows.append((station, pd.Timestamp(f'{winter}-12-01') + pd.Timedelta(days=i//12, minutes=(i%12)*10), winter))
    f = pd.DataFrame(rows, columns=['station', 'time', 'winter'])
    rng = np.random.default_rng(seed); f['ice'] = rng.choice([0., 1., np.nan], len(f), p=[.7, .25, .05])
    scores = rng.choice([0., .2, .35, .8, 1., np.nan], len(f))
    output = select_exact_thresholds(f, scores, minimum=5)
    valid = np.isfinite(scores) & f.ice.notna()
    thresholds = np.r_[np.nextafter(scores[valid].max(), np.inf), np.unique(scores[valid])]
    truth = [(t, *brute(f, scores, t, 5)) for t in thresholds]
    for name, column in [('mean_f1', 1), ('worst_winter_f1', 2)]:
        maximum = max(r[column] for r in truth)
        chosen = sorted([r for r in truth if r[column] >= maximum-1e-12], key=lambda r:(r[3], -r[0]))[0]
        assert output[name]['threshold'] == chosen[0]
        assert output[name][name] == pytest.approx(chosen[column], abs=1e-12)
        assert output[name]['fp'] == chosen[3]


def test_negative_only_ties_prefer_no_false_alarm_and_largest_threshold():
    f = pd.DataFrame({'station':['a','a'], 'time':pd.to_datetime(['2024-12-01','2025-12-01']), 'winter':[2024,2025], 'ice':[0,0]})
    r = select_exact_thresholds(f, [.2, .8], minimum=1)
    assert r['mean_f1']['threshold'] > .8
    assert r['mean_f1']['fp'] == 0


def test_missing_predictions_are_excluded_from_coverage():
    f = pd.DataFrame({'station':['a']*4, 'time':pd.to_datetime(['2024-12-01','2024-12-01 00:10','2025-12-01','2025-12-01 00:10'],format='mixed'), 'winter':[2024,2024,2025,2025], 'ice':[1,0,1,0]})
    r = select_exact_thresholds(f, [.8, np.nan, .8, np.nan], minimum=2)
    assert r['mean_f1']['mean_f1'] == 0
    assert r['mean_f1']['scored_pairs'] == 2
