"""Deterministic station-held-out splits; no row-level random split."""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validation import PROTECTED_STATIONS, assert_training_stations

EDA = ROOT / "outputs" / "private" / "development" / "station_eda.csv"
OUT = ROOT / "outputs" / "private" / "validation"


def inner_folds(records, folds=3):
    bins = [{"stations": [], "positive_stations": 0, "ice_slots": 0, "route_counts": {}} for _ in range(folds)]
    positive = sorted((r for r in records if r["ice_slots"] > 0),
                      key=lambda r: (-r["ice_slots"], r["station_id"]))
    negative = sorted((r for r in records if r["ice_slots"] == 0),
                      key=lambda r: (r["route"], r["station_id"]))
    for record in positive + negative:
        route = record["route"]
        if record["ice_slots"] > 0:
            index = min(range(folds), key=lambda i: (
                bins[i]["positive_stations"], bins[i]["route_counts"].get(route, 0),
                bins[i]["ice_slots"], len(bins[i]["stations"]), i))
        else:
            index = min(range(folds), key=lambda i: (
                bins[i]["route_counts"].get(route, 0), len(bins[i]["stations"]), i))
        bucket = bins[index]
        bucket["stations"].append(record["station_id"])
        bucket["positive_stations"] += int(record["ice_slots"] > 0)
        bucket["ice_slots"] += record["ice_slots"]
        bucket["route_counts"][route] = bucket["route_counts"].get(route, 0) + 1
    return bins


def main():
    rows = pd.read_csv(EDA, dtype={"station_id": str}).to_dict("records")
    ids = sorted(row["station_id"] for row in rows)
    assert_training_stations(ids)
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate development station IDs")
    outer = []
    for heldout in ids:
        training = [row for row in rows if row["station_id"] != heldout]
        bins = inner_folds(training)
        if set().union(*(set(b["stations"]) for b in bins)) != set(ids) - {heldout}:
            raise AssertionError("Inner folds do not partition outer training stations")
        if any(set(a["stations"]) & set(b["stations"]) for i, a in enumerate(bins) for b in bins[i + 1:]):
            raise AssertionError("Overlapping inner folds")
        outer.append({"validation_station": heldout,
                      "training_stations": sorted(row["station_id"] for row in training),
                      "validation_ice_slots_development_audit": next(
                          row["ice_slots"] for row in rows if row["station_id"] == heldout),
                      "inner_folds": bins})
    result = {"seed": 20260923, "outer_strategy": "leave_one_station_out",
              "outer_folds": outer,
              "supplementary_temporal_split": {
                  "train": ["2024-11-01", "2025-02-28"],
                  "validation": ["2025-11-01", "2026-02-28"],
                  "purpose": "winter transfer only, not spatial generalization"},
              "official_final_stations": sorted(PROTECTED_STATIONS),
              "score_status": "provisional_until_organizer_reply"}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "splits.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"outer_folds": len(outer),
                      "inner_fold_positive_station_counts": [
                          [b["positive_stations"] for b in fold["inner_folds"]] for fold in outer],
                      "protected_in_outer": bool(set(ids) & PROTECTED_STATIONS)}), flush=True)


if __name__ == "__main__":
    main()
