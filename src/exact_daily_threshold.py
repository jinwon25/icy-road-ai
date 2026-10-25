"""모든 서로 다른 점수를 순회하여 날짜→지점 F1 임계값을 고른다.

F1은 임계값에 대해 단조롭지 않으므로 이분탐색하지 않는다. 예측 양성을
높은 점수부터 하나씩 추가하며 바뀐 날짜·지점의 합계만 갱신한다.
"""
import numpy as np
import pandas as pd
from src.icing_transition import _keys

TOLERANCE = 1e-12


def select_exact_thresholds(frame, scores, minimum=144):
    f = _keys(frame)
    s = np.asarray(scores, float)
    y = np.asarray(frame.ice, float)
    if s.shape != (len(f),) or np.isinf(s).any() or np.isinf(y).any() or not np.isin(y[np.isfinite(y)], [0., 1.]).all():
        raise ValueError('Aligned finite-or-missing scores and binary-or-missing outcomes required')
    if not set(frame.winter) <= {2024, 2025} or not 1 <= minimum <= 144:
        raise ValueError('Declared winters and valid minimum required')
    population = sorted(f.station.unique())
    valid = np.isfinite(s) & np.isfinite(y)
    if not valid.any():
        raise ValueError('At least one valid score/outcome pair required')
    original = f.loc[valid].copy()
    original['winter'] = np.asarray(frame.winter)[valid]
    day, keys = pd.factorize(pd.MultiIndex.from_arrays([original.station, original.time.dt.normalize()]), sort=True)
    station = np.array([population.index(k) for k in keys.get_level_values(0)])
    day_winter = np.zeros(len(keys), int)
    day_winter[day] = original.winter.to_numpy(int) - 2024
    s, y = s[valid], y[valid].astype(int)
    n = np.bincount(day, minlength=len(keys))
    positive = np.bincount(day, weights=y, minlength=len(keys)).astype(int)
    accepted = n >= minimum
    counts = np.zeros((3, len(population)), int)
    sums = np.zeros_like(counts, dtype=float)
    for d in np.flatnonzero(accepted & (positive > 0)):
        counts[0, station[d]] += 1
        counts[1 + day_winter[d], station[d]] += 1
    sizes = np.array([len(population), *[frame.loc[frame.winter.eq(w), 'station'].nunique() for w in [2024, 2025]]])
    if (sizes == 0).any():
        raise ValueError('Both winters required for the worst-winter objective')
    totals = np.zeros(3)
    predicted = np.zeros(len(keys), int)
    tp_day = np.zeros(len(keys), int)
    tp = fp = 0
    positives = int(y.sum())
    initial = dict(threshold=float(np.nextafter(s.max(), np.inf)), mean_f1=0., worst_winter_f1=0., fp=0, tp=0, fn=positives)
    best = {track: initial.copy() for track in ['mean_f1', 'worst_winter_f1']}
    order = np.argsort(-s, kind='stable')
    distinct = 1
    for position, index in enumerate(order):
        d = day[index]; st = station[d]
        tp += int(y[index]); fp += int(1 - y[index])
        if accepted[d]:
            denominator = positive[d] + predicted[d]
            before = 2 * tp_day[d] / denominator if denominator else 0.
            predicted[d] += 1; tp_day[d] += y[index]
            after = 2 * tp_day[d] / (denominator + 1)
            for group in [0, 1 + day_winter[d]]:
                prior = sums[group, st] / counts[group, st] if counts[group, st] else 0.
                sums[group, st] += after - before
                counts[group, st] += int(denominator == 0)
                totals[group] += sums[group, st] / counts[group, st] - prior
        # 같은 점수 중 일부만 양성인 판정은 불가능하므로 묶음 전체를 처리한 뒤 비교한다.
        if position + 1 < len(order) and s[order[position + 1]] == s[index]:
            continue
        distinct += 1
        values = np.clip(totals / sizes, 0., 1.)
        row = dict(threshold=float(s[index]), mean_f1=float(values[0]), worst_winter_f1=float(min(values[1:])), fp=fp, tp=tp, fn=positives - tp)
        for track, current in best.items():
            delta = row[track] - current[track]
            better_tie = (row['fp'], -row['threshold']) < (current['fp'], -current['threshold'])
            if delta > TOLERANCE or (abs(delta) <= TOLERANCE and better_tie):
                best[track] = row.copy()
    for row in best.values():
        row.update(unique_thresholds=distinct, scored_pairs=len(s), minimum_valid_pairs=minimum)
    return best


def choose_exact(table, track):
    """부동소수점 오차 범위의 차이는 사전에 고정한 허용치로 동률 처리한다."""
    best = table[track].max()
    tied = table.loc[table[track].ge(best - TOLERANCE)]
    return tied.sort_values(['fp', 'threshold', 'candidate'], ascending=[True, False, True], kind='stable').iloc[0].to_dict()
