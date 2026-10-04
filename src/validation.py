"""Leakage-safe evaluation primitives. No official score is claimed by this module."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from math import isfinite, sqrt
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")
ICE = "04"
KNOWN_NON_ICE = frozenset(("01", "02", "03", "10", "11", "12", "13", "14", "15"))
PROTECTED_STATIONS = frozenset(("12410", "33411", "23402"))



def canonical_station_id(raw: object) -> str:
    """Normalize integer IDs exported as decimals; keep missing IDs separate."""
    if raw is None:
        return "<missing>"
    value = str(raw).strip()
    if value.lower() in ("", "nan", "none", "null"):
        return "<missing>"
    if value.endswith(".0") and value[:-2].isdigit():
        return value[:-2]
    return value


def normalize_state(raw: object) -> int | None:
    """1=Ice, 0=defined non-Ice, None=missing or undefined."""
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    if value.endswith(".0") and value[:-2].isdigit():
        value = value[:-2]
    if value.isdigit():
        value = value.zfill(2)
    if value == ICE:
        return 1
    if value in KNOWN_NON_ICE:
        return 0
    return None


def regression_metrics(observed, predicted):
    """BIAS = mean(predicted - observed); invalid pairs are omitted."""
    valid = []
    for obs, pred in zip(observed, predicted, strict=True):
        try:
            a, b = float(obs), float(pred)
        except (TypeError, ValueError):
            continue
        if isfinite(a) and isfinite(b):
            valid.append(b - a)
    if not valid:
        return {"n": 0, "bias": None, "mae": None, "rmse": None}
    n = len(valid)
    return {"n": n, "bias": sum(valid) / n,
            "mae": sum(abs(x) for x in valid) / n,
            "rmse": sqrt(sum(x * x for x in valid) / n)}


def binary_metrics(observed, predicted):
    """Undefined precision/recall/F1 remains None rather than forced to 0 or 1."""
    pairs = [(a, b) for a, b in zip(observed, predicted, strict=True)
             if a in (0, 1) and b in (0, 1)]
    tp = sum(a == 1 and b == 1 for a, b in pairs)
    fp = sum(a == 0 and b == 1 for a, b in pairs)
    fn = sum(a == 1 and b == 0 for a, b in pairs)
    tn = sum(a == 0 and b == 0 for a, b in pairs)
    return {"n": len(pairs), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None}


def kst_datetime(value):
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return dt.replace(tzinfo=KST) if dt.tzinfo is None else dt.astimezone(KST)


def daily_scores(records, unit="10_minute_observations", expected_slots=144,
                 minimum_coverage=1.0):
    """Records: (station_id, timestamp, observed, predicted). Duplicate slots error."""
    if unit not in ("10_minute_observations", "any_ice_per_day"):
        raise ValueError(unit)
    grouped = defaultdict(dict)
    for station, timestamp, observed, predicted in records:
        dt = kst_datetime(timestamp)
        if dt.minute % 10 or dt.second or dt.microsecond:
            raise ValueError(f"Not a 10-minute KST slot: {dt}")
        key = (str(station), dt.date().isoformat())
        if dt in grouped[key]:
            raise ValueError(f"Duplicate station/time: {key} {dt}")
        grouped[key][dt] = (observed, predicted)
    result = []
    for (station, date), slots in sorted(grouped.items()):
        valid = [(a, b) for a, b in slots.values() if a in (0, 1) and b in (0, 1)]
        coverage = len(valid) / expected_slots
        accepted = coverage >= minimum_coverage
        if accepted and unit == "any_ice_per_day":
            valid = [(int(any(a for a, _ in valid)), int(any(b for _, b in valid)))]
        metrics = binary_metrics((a for a, _ in valid), (b for _, b in valid)) if accepted else None
        result.append({"station": station, "date_kst": date,
                       "observed_slots": len(slots), "valid_slots": len(valid) if unit == "10_minute_observations" or not accepted else sum(a in (0, 1) and b in (0, 1) for a, b in slots.values()),
                       "coverage": coverage, "accepted": accepted,
                       **(metrics or {"n": 0, "tp": None, "fp": None, "fn": None,
                                      "tn": None, "precision": None, "recall": None, "f1": None})})
    return result


def mean_defined(values):
    usable = [x for x in values if x is not None]
    return sum(usable) / len(usable) if usable else None


def macro_scores(rows, station_first=True):
    """Daily macro or station-then-daily macro; reports denominator of defined days."""
    accepted = [r for r in rows if r["accepted"]]
    output = {"accepted_days": len(accepted)}
    for metric in ("f1", "precision", "recall"):
        output[f"defined_{metric}_days"] = sum(r[metric] is not None for r in accepted)
        if station_first:
            stations = sorted({r["station"] for r in accepted})
            station_means = [mean_defined(r[metric] for r in accepted if r["station"] == station)
                             for station in stations]
            output[metric] = mean_defined(station_means)
            output[f"defined_{metric}_stations"] = sum(x is not None for x in station_means)
        else:
            output[metric] = mean_defined(r[metric] for r in accepted)
    return output


def route_macro_scores(rows, station_to_route):
    """Equal-weight routes after daily and station means; a provisional alternative."""
    stations = {r["station"] for r in rows}
    missing = stations - set(station_to_route)
    if missing:
        raise ValueError(f"Missing route for stations: {sorted(missing)}")
    route_names = sorted({station_to_route[s] for s in stations})
    per_route = {}
    for route in route_names:
        subset = [r for r in rows if station_to_route[r["station"]] == route]
        per_route[route] = macro_scores(subset, station_first=True)
    overall = {"routes": len(route_names), "per_route": per_route}
    for metric in ("f1", "precision", "recall"):
        overall[metric] = mean_defined(per_route[route][metric] for route in route_names)
    return overall


def assert_training_stations(station_ids):
    overlap = PROTECTED_STATIONS.intersection(map(canonical_station_id, station_ids))
    if overlap:
        raise ValueError(f"Protected station in training: {sorted(overlap)}")

