"""Paired development comparison of direct Ice models with two AWS inputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validation import PROTECTED_STATIONS, binary_metrics, macro_scores


def main() -> None:
    private = ROOT / "outputs" / "private"
    nearest = pd.read_parquet(private / "ice_logistic" / "predictions.parquet")
    fallback = pd.read_parquet(private / "ice_fallback_logistic" / "predictions.parquet")
    for frame in (nearest, fallback):
        frame["station"] = frame.station.astype(str)
        if set(frame.station) & PROTECTED_STATIONS:
            raise AssertionError("Protected RWIS entered Ice comparison")
    paired = nearest.merge(fallback, on=["station", "time"], how="outer",
                           validate="one_to_one", indicator=True,
                           suffixes=("_nearest", "_fallback"))
    if len(paired) != len(nearest) or len(paired) != len(fallback) or not paired._merge.eq("both").all():
        raise AssertionError("Ice models evaluated on different rows")
    if not paired.ice_nearest.equals(paired.ice_fallback):
        raise AssertionError("Ice truth differs between input variants")
    station_rows = []
    for station, part in paired.groupby("station"):
        valid = part.loc[part.ice_nearest.notna()]
        first = binary_metrics(valid.ice_nearest.astype(int),
                               valid.predicted_ice_nearest.astype(int))
        second = binary_metrics(valid.ice_nearest.astype(int),
                                valid.predicted_ice_fallback.astype(int))
        station_rows.append({"station": station, "valid_slots": len(valid),
                             "ice_slots": int(valid.ice_nearest.sum()),
                             "nearest_tp": first["tp"], "nearest_fp": first["fp"],
                             "nearest_fn": first["fn"], "nearest_f1": first["f1"],
                             "fallback_tp": second["tp"], "fallback_fp": second["fp"],
                             "fallback_fn": second["fn"], "fallback_f1": second["f1"]})
    table = pd.DataFrame(station_rows)
    a = pd.read_csv(private / "ice_logistic" / "daily_10min_metrics.csv",
                    dtype={"station": str, "date_kst": str})
    b = pd.read_csv(private / "ice_fallback_logistic" / "daily_10min_metrics.csv",
                    dtype={"station": str, "date_kst": str})
    day = a.merge(b, on=["station", "date_kst"], how="outer", validate="one_to_one",
                  indicator=True, suffixes=("_nearest", "_fallback"))
    if len(day) != len(a) or len(day) != len(b) or not day._merge.eq("both").all():
        raise AssertionError("Daily station/date sets differ")
    if not day.accepted_nearest.equals(day.accepted_fallback):
        raise AssertionError("Daily coverage differs")
    accepted = day.loc[day.accepted_nearest].copy()
    observed_ice = accepted.loc[(accepted.tp_nearest + accepted.fn_nearest).gt(0)].copy()
    if not (observed_ice.tp_nearest + observed_ice.fn_nearest).equals(
            observed_ice.tp_fallback + observed_ice.fn_fallback):
        raise AssertionError("Observed Ice day counts differ")
    fixed_days = {}
    for variant in ("nearest", "fallback"):
        field = f"f1_{variant}"
        fixed_days[variant] = {
            "ice_station_days": len(observed_ice),
            "mean_f1_equal_days": float(observed_ice[field].mean()),
            "mean_f1_station_first": float(observed_ice.groupby("station")[field].mean().mean()),
            "false_alarm_nonice_station_days": int(accepted.loc[
                (accepted.tp_nearest + accepted.fn_nearest).eq(0),
                f"fp_{variant}"].gt(0).sum()),
        }
    n = pd.read_parquet(private / "ice_logistic" / "predictions.parquet")
    f = pd.read_parquet(private / "ice_fallback_logistic" / "predictions.parquet")
    valid_n = n.loc[n.ice.notna()]
    valid_f = f.loc[f.ice.notna()]
    summary = {"status": "provisional_development_paired_ice_ablation",
               "paired_target_slots": len(paired),
               "paired_valid_labels": int(paired.ice_nearest.notna().sum()),
               "ice_slots": int(paired.ice_nearest.eq(1).sum()),
               "nearest_slot_micro": binary_metrics(valid_n.ice.astype(int),
                                                     valid_n.predicted_ice.astype(int)),
               "fallback_slot_micro": binary_metrics(valid_f.ice.astype(int),
                                                      valid_f.predicted_ice.astype(int)),
               "fixed_observed_ice_days": fixed_days,
               "accepted_station_days": len(accepted),
               "nearest_defined_f1_days_all": int(a.f1.notna().sum()),
               "fallback_defined_f1_days_all": int(b.f1.notna().sum()),
               "note": "Same model family and outer station folds; each variant selects threshold on its own inner OOF. Daily policy remains provisional."}
    out = private / "ice_variant_comparison"
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "station_metrics.csv", index=False, encoding="utf-8-sig")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
