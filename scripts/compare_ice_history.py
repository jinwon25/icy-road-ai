"""Compare baseline and prior-history Ice predictions on identical rows/days."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validation import PROTECTED_STATIONS, binary_metrics


def main() -> None:
    private = ROOT / "outputs" / "private"
    folders = {"fallback": "ice_fallback_logistic", "history": "ice_history_logistic"}
    prediction = {name: pd.read_parquet(private / folder / "predictions.parquet")
                  for name, folder in folders.items()}
    for frame in prediction.values():
        frame["station"] = frame.station.astype(str)
        if set(frame.station) & PROTECTED_STATIONS:
            raise AssertionError("Protected RWIS entered Ice history comparison")
    left, right = prediction.values()
    paired = left.merge(right, on=["station", "time"], how="outer", validate="one_to_one",
                        indicator=True, suffixes=("_fallback", "_history"))
    if (len(paired) != len(left) or len(paired) != len(right)
            or not paired._merge.eq("both").all()
            or not paired.ice_fallback.equals(paired.ice_history)):
        raise AssertionError("Ice models are not paired on identical target rows/outcomes")
    station_rows = []
    for station, part in paired.groupby("station"):
        part = part.loc[part.ice_fallback.notna()]
        record = {"station": station, "valid_slots": len(part),
                  "ice_slots": int(part.ice_fallback.sum())}
        for name in folders:
            m = binary_metrics(part.ice_fallback.astype(int),
                               part[f"predicted_ice_{name}"].astype(int))
            record.update({f"{name}_{key}": m[key] for key in ("tp", "fp", "fn", "f1")})
        station_rows.append(record)
    days = {name: pd.read_csv(private / folder / "daily_10min_metrics.csv",
                              dtype={"station": str, "date_kst": str})
            for name, folder in folders.items()}
    day = days["fallback"].merge(days["history"], on=["station", "date_kst"],
                                  how="outer", validate="one_to_one", indicator=True,
                                  suffixes=("_fallback", "_history"))
    if (len(day) != len(days["fallback"]) or len(day) != len(days["history"])
            or not day._merge.eq("both").all()
            or not day.accepted_fallback.equals(day.accepted_history)):
        raise AssertionError("Daily evaluation sets differ")
    accepted = day.loc[day.accepted_fallback].copy()
    observed_ice = accepted.loc[(accepted.tp_fallback + accepted.fn_fallback).gt(0)].copy()
    if not (observed_ice.tp_fallback + observed_ice.fn_fallback).equals(
            observed_ice.tp_history + observed_ice.fn_history):
        raise AssertionError("Observed positive days differ")
    fixed = {}
    for name in folders:
        fixed[name] = {"ice_station_days": len(observed_ice),
                       "mean_f1_equal_days": float(observed_ice[f"f1_{name}"].mean()),
                       "mean_f1_station_first": float(observed_ice.groupby("station")[f"f1_{name}"].mean().mean()),
                       "false_alarm_nonice_station_days": int(accepted.loc[
                           (accepted.tp_fallback + accepted.fn_fallback).eq(0),
                           f"fp_{name}"].gt(0).sum())}
    summary = {"status": "provisional_development_paired_history_ablation",
               "paired_target_slots": len(paired),
               "paired_valid_labels": int(paired.ice_fallback.notna().sum()),
               "ice_slots": int(paired.ice_fallback.eq(1).sum()),
               "accepted_station_days": len(accepted),
               "fixed_observed_ice_days": fixed,
               "defined_f1_days_all": {name: int(days[name].f1.notna().sum()) for name in folders},
               "note": "Same outer LOSO folds, rows and logistic family; each threshold from its own inner station OOF. Daily policy provisional."}
    for name, frame in prediction.items():
        valid = frame.loc[frame.ice.notna()]
        summary[f"{name}_slot_micro"] = binary_metrics(valid.ice.astype(int),
                                                       valid.predicted_ice.astype(int))
    out = private / "ice_history_comparison"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(station_rows).to_csv(out / "station_metrics.csv", index=False,
                                      encoding="utf-8-sig")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
