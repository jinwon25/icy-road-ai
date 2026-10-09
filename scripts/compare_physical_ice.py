"""동일 정답에서 새 후보·내부 선택 절차와 기존 모델을 비교한다."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validation import assert_training_stations, binary_metrics, daily_scores, macro_scores
from src.ice_event_metrics import event_metrics
from src.data_source import sha256_file


def main():
    private = ROOT / "outputs/private"
    data = pd.read_parquet(private / "physical_ice/predictions.parquet").sort_values(["station", "time"]).reset_index(drop=True)
    assert_training_stations(data.station.unique())
    predictions = {}
    config = json.loads((ROOT / "config/physical_experiment.json").read_text(encoding="utf-8"))
    for candidate in config["candidates"]:
        name = candidate["id"]
        for policy in ["slot", "daily"]:
            predictions[f"{name}_{policy}"] = (data[f"pred_{policy}_{name}"], data[f"score_{name}"])
    predictions["inner_selected"] = (data.pred_selected, data.score_selected)
    for folder, prefix, columns in [("ice_fallback_logistic", "logistic", [("predicted_ice", "slot")]),
                                    ("ice_nonlinear", "hgb_balanced", [("pred_slot", "slot"), ("pred_daily", "daily")])]:
        reference = pd.read_parquet(private / folder / "predictions.parquet").sort_values(["station", "time"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(data[["station", "time", "ice"]], reference[["station", "time", "ice"]])
        for column, policy in columns:
            predictions[f"{prefix}_{policy}"] = (reference[column], reference.model_score)
    metadata = pd.read_csv(private / "sensor_availability/metadata.csv", dtype={"station": str}).set_index("station")
    summaries, station_rows, daily_frames = {}, [], []
    for name, (predicted, scores) in predictions.items():
        frame = data[["station", "route", "time", "ice"]].copy()
        frame["predicted"] = predicted.to_numpy()
        frame["score"] = scores.to_numpy()
        valid = frame.loc[frame.ice.notna()]
        records = [(r.station, r.time, int(r.ice) if pd.notna(r.ice) else None, int(r.predicted))
                   for r in frame.itertuples(index=False)]
        daily = daily_scores(records, minimum_coverage=1.)
        days = pd.DataFrame(daily)
        accepted = days.loc[days.accepted]
        fixed = accepted.loc[(accepted.tp + accepted.fn).gt(0)]
        dry = accepted.loc[(accepted.tp + accepted.fn).eq(0)]
        local = []
        for station, part in valid.groupby("station"):
            positive = int(part.ice.sum())
            row = {"variant": name, "station": station, "station_type": metadata.loc[station, "station_type"],
                   "route": part.route.iloc[0].strip(), "ice_slots": positive,
                   **binary_metrics(part.ice.astype(int), part.predicted.astype(int)),
                   "fixed_ice_day_f1": float(fixed.loc[fixed.station.eq(station), "f1"].mean()),
                   "false_alarm_nonice_days": int(dry.loc[dry.station.eq(station), "fp"].gt(0).sum()),
                   "average_precision": float(average_precision_score(part.ice, part.score)) if positive else None}
            local.append(row)
        station_rows.extend(local)
        local = pd.DataFrame(local)
        summaries[name] = {"slot_micro": binary_metrics(valid.ice.astype(int), valid.predicted.astype(int)),
                           "daily_station_macro": macro_scores(daily),
                           "fixed_observed_ice_days": len(fixed),
                           "fixed_ice_day_f1_station_first": float(fixed.groupby("station").f1.mean().mean()),
                           "false_alarm_nonice_days": int(dry.fp.gt(0).sum()),
                           "macro_average_precision_positive_stations": float(local.average_precision.mean()),
                           "stations_with_true_positives": int(local.tp.gt(0).sum()),
                           "events": event_metrics(frame, observed="ice", predicted="predicted")}
        days["variant"] = name
        daily_frames.append(days)
        print(name, json.dumps(summaries[name]["slot_micro"]), flush=True)
    station_table = pd.DataFrame(station_rows)
    wide = station_table.pivot(index="station", columns="variant", values="fixed_ice_day_f1").dropna()
    rng = np.random.default_rng(20260923)
    draws = rng.integers(0, len(wide), (2000, len(wide)))
    delta = (wide.inner_selected - wide.logistic_slot).to_numpy()
    bootstrap = {"positive_stations": len(wide), "mean_difference": float(delta.mean()),
                 "percentile_95_interval": np.quantile(delta[draws].mean(axis=1), [.025, .975]).tolist(),
                 "meaning": "Exploratory shared-LOSO station resampling; not an independent confidence guarantee."}
    out = private / "physical_ice_comparison"
    out.mkdir(parents=True, exist_ok=True)
    station_table.to_csv(out / "station_metrics.csv", index=False, encoding="utf-8-sig")
    pd.concat(daily_frames).to_csv(out / "daily_metrics.csv", index=False, encoding="utf-8-sig")
    group = station_table.groupby(["variant", "station_type"], as_index=False)[["n", "tp", "fp", "fn", "tn"]].sum()
    group.to_csv(out / "sensor_type_metrics.csv", index=False, encoding="utf-8-sig")
    summary = {"status": "paired_development_physical_comparison", "rows": len(data),
               "variants": summaries, "fixed_ice_day_station_resampling": bootstrap,
               "prediction_sha256": sha256_file(private / "physical_ice/predictions.parquet"),
               "limitations": ["Same observed target rows and frozen spatial splits.",
                               "Every candidate and threshold selected on inner stations; official heldout remains unopened.",
                               "Both winters participate in spatial training; this is not winter-forward validation.",
                               "New daily threshold grid includes small-score values; historical HGB used 0.01 grid.",
                               "Only 239 Ice slots and 14 development stations; results need temporal confirmation."]}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
