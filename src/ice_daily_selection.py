"""Inner-OOF daily threshold selection with explicit station/day denominators."""
import numpy as np
import pandas as pd


def choose_daily_threshold(frame, scores, candidates=None, expected_slots=144):
    """Only pass inner validation predictions; no outer labels enter selection.

    Zero-event station-days are undefined and omitted, matching current policy.
    Incomplete days remain excluded under the project's provisional coverage rule.
    """
    y = frame.ice.to_numpy(dtype=float)
    scores = np.asarray(scores, dtype=float)
    if len(y) != len(scores) or not np.isfinite(scores).all():
        raise ValueError("Incomplete inner OOF predictions")
    if not np.isin(y, [0, 1]).all() or y.sum() == 0:
        raise ValueError("Threshold selection requires defined labels and Ice positives")
    time = pd.to_datetime(frame.time)
    if time.dt.tz is not None:
        time = time.dt.tz_convert("Asia/Seoul").dt.tz_localize(None)
    if ((time.dt.minute % 10 != 0) | time.dt.second.ne(0) | time.dt.microsecond.ne(0)).any():
        raise ValueError("Not a ten-minute timestamp")
    keys = pd.DataFrame({"station": frame.station.astype(str).to_numpy(),
                         "time": time.to_numpy()})
    if keys.duplicated().any():
        raise ValueError("Duplicate inner OOF station/time")
    groups, index = pd.factorize(pd.MultiIndex.from_arrays([keys.station, time.dt.date]))
    sizes = np.bincount(groups)
    complete = sizes == expected_slots
    positives = np.bincount(groups, weights=y)
    if not (complete & (positives > 0)).any():
        raise ValueError("No complete positive days for daily selection")
    station_codes, _ = pd.factorize(index.get_level_values(0))
    candidates = np.asarray(candidates if candidates is not None else
                            np.r_[np.linspace(0, 1, 101), np.nextafter(1., np.inf)], dtype=float)
    if len(candidates) == 0 or not np.isfinite(candidates).all():
        raise ValueError("Invalid candidate thresholds")
    rows = []
    for threshold in np.unique(candidates):
        predicted = scores >= threshold
        predicted_counts = np.bincount(groups, weights=predicted)
        tp = np.bincount(groups, weights=predicted * y)
        denominator = positives + predicted_counts
        defined = complete & (denominator > 0)
        values = np.divide(2 * tp, denominator, out=np.zeros_like(tp), where=denominator > 0)
        count = np.bincount(station_codes[defined], minlength=station_codes.max() + 1)
        total = np.bincount(station_codes[defined], weights=values[defined], minlength=len(count))
        macro = float((total[count > 0] / count[count > 0]).mean())
        rows.append({"threshold": float(threshold), "station_daily_f1": macro,
                     "defined_days": int(defined.sum()), "defined_stations": int((count > 0).sum()),
                     "predicted_slots": int(predicted.sum())})
    trace = pd.DataFrame(rows)
    best_score = trace.station_daily_f1.max()
    best = trace.loc[np.isclose(trace.station_daily_f1, best_score, rtol=0, atol=1e-12)].iloc[-1]
    return float(best.threshold), float(best.station_daily_f1), trace
