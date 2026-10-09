"""문헌 근거 입력·양성 가중치를 내부 분할에서 선택하는 재개 가능한 실험."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive, sha256_file
from src.physical_features import ThermalContext, load_thermal_sources, CONTEXT_FEATURES
from src.ice_daily_selection import choose_daily_threshold
from src.validation import assert_training_stations
from scripts.baseline_ice_logistic import FEATURES, choose_threshold


def threshold_grid(scores):
    quantiles = np.r_[np.linspace(0, .99, 25), 1 - np.logspace(-2, -5, 51)]
    return np.unique(np.r_[0., np.logspace(-6, 0, 61), np.quantile(scores, quantiles), np.nextafter(1., np.inf)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="앞 2개 외부 분할, 원래 행·내부 분할 유지")
    args = parser.parse_args()
    private = ROOT / "outputs/private"
    config_path = ROOT / "config/physical_experiment.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    feature_path = private / "physical_features/features.parquet"
    feature_summary = json.loads((private / "physical_features/summary.json").read_text(encoding="utf-8"))
    data = pd.read_parquet(feature_path).reset_index(drop=True)
    data["station"] = data.station.astype(str)
    assert_training_stations(data.station.unique())
    if data.duplicated(["station", "time"]).any():
        raise ValueError("Duplicate development target")
    splits_path = private / "validation/splits.json"
    splits = json.loads(splits_path.read_text(encoding="utf-8"))["outer_folds"]
    if args.smoke:
        splits = splits[:2]
    archive = competition_archive(ROOT)
    source = load_thermal_sources(archive)
    metadata = pd.read_csv(private / "sensor_availability/metadata.csv", dtype={"station": str})
    metadata = metadata.loc[metadata.kind.eq("RWIS"), ["station", "route", "lat", "lon"]]
    context = ThermalContext(data, source, metadata)
    feature_sets = {"base": FEATURES, "physical": FEATURES + feature_summary["additional_features"]}
    feature_sets["thermal"] = feature_sets["physical"] + CONTEXT_FEATURES
    out = private / ("smoke_physical_ice" if args.smoke else "physical_ice")
    out.mkdir(parents=True, exist_ok=True)
    signature = {"features": sha256_file(feature_path), "config": sha256_file(config_path),
                 "splits": sha256_file(splits_path), "archive": sha256_file(archive),
                 "runner": sha256_file(Path(__file__)),
                 "context_code": sha256_file(ROOT / "src/physical_features.py")}
    manifest_path = out / "input_signature.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text(encoding="utf-8")) != signature:
        raise ValueError("Experiment inputs/code changed; use a new output location before resuming")
    manifest_path.write_text(json.dumps(signature, indent=2), encoding="utf-8")
    all_predictions, all_thresholds, all_choices = [], [], []
    with threadpool_limits(limits=config["max_compute_threads"]):
        for outer in splits:
            held = str(outer["validation_station"])
            fold_out = out / held
            fold_out.mkdir(exist_ok=True)
            final_path = fold_out / "predictions.parquet"
            if final_path.exists():
                all_predictions.append(pd.read_parquet(final_path))
                all_thresholds.extend(json.loads((fold_out / "thresholds.json").read_text(encoding="utf-8")))
                all_choices.append(json.loads((fold_out / "selection.json").read_text(encoding="utf-8")))
                print(f"{held}: completed fold reused", flush=True)
                continue
            train = data.loc[data.station.ne(held) & data.ice.notna()].copy()
            valid = data.loc[data.station.eq(held)].copy()
            if set(train.station) != set(outer["training_stations"]):
                raise ValueError("Frozen fold mismatch")
            oof = {candidate["id"]: np.full(len(train), np.nan) for candidate in config["candidates"]}
            reference_records = []
            for index, inner in enumerate(outer["inner_folds"]):
                mask = train.station.isin(inner["stations"]).to_numpy()
                fit, check = train.loc[~mask], train.loc[mask]
                forbidden = set(inner["stations"]) | {held}
                if set(fit.station) & forbidden or set(fit.station) & set(check.station):
                    raise AssertionError("Inner station leakage")
                thermal_fit, refs_fit = context.features(fit, forbidden)
                thermal_check, refs_check = context.features(check, forbidden)
                fit_x = pd.concat([fit, thermal_fit], axis=1)
                check_x = pd.concat([check, thermal_check], axis=1)
                reference_records.extend([{**r, "inner_fold": index, "role": role}
                                          for role, records in [("fit", refs_fit), ("validation", refs_check)] for r in records])
                for candidate in config["candidates"]:
                    name = candidate["id"]
                    model = HistGradientBoostingClassifier(**config["model"], class_weight={0: 1., 1: candidate["positive_weight"]})
                    columns = feature_sets[candidate["features"]]
                    model.fit(fit_x[columns], fit.ice.astype(int))
                    oof[name][mask] = model.predict_proba(check_x[columns])[:, 1]
                print(f"{held}: inner {index + 1}/3, four candidates complete", flush=True)
            thermal_train, refs_train = context.features(train, {held})
            thermal_valid, refs_valid = context.features(valid, {held})
            train_x, valid_x = pd.concat([train, thermal_train], axis=1), pd.concat([valid, thermal_valid], axis=1)
            reference_records.extend([{**r, "inner_fold": None, "role": role}
                                      for role, records in [("outer_fit", refs_train), ("outer_validation", refs_valid)] for r in records])
            result = valid[["station", "route", "time", "ice", "state_raw"]].copy()
            thresholds = []
            inner_output = train[["station", "time", "ice"]].copy()
            for candidate in config["candidates"]:
                name = candidate["id"]
                scores = oof[name]
                if not np.isfinite(scores).all():
                    raise AssertionError("Incomplete inner predictions")
                slot_t, slot_f1 = choose_threshold(train.ice.to_numpy(dtype=int), scores)
                daily_t, daily_f1, trace = choose_daily_threshold(train, scores, threshold_grid(scores))
                trace.to_csv(fold_out / f"{name}_threshold_trace.csv", index=False, encoding="utf-8-sig")
                inner_output[f"score_{name}"] = scores
                alarms = int((scores >= daily_t).sum())
                thresholds.append({"station": held, "candidate": name, "slot_threshold": slot_t,
                                   "daily_threshold": daily_t, "inner_slot_f1": slot_f1,
                                   "inner_daily_f1": daily_f1, "inner_alarm_slots": alarms,
                                   "train_rows": len(train), "train_positives": int(train.ice.sum())})
                model = HistGradientBoostingClassifier(**config["model"], class_weight={0: 1., 1: candidate["positive_weight"]})
                columns = feature_sets[candidate["features"]]
                model.fit(train_x[columns], train.ice.astype(int))
                score = model.predict_proba(valid_x[columns])[:, 1]
                if not np.isfinite(score).all():
                    raise AssertionError("Nonfinite outer score")
                result[f"score_{name}"] = score
                result[f"pred_slot_{name}"] = (score >= slot_t).astype(int)
                result[f"pred_daily_{name}"] = (score >= daily_t).astype(int)
            selected = sorted(thresholds, key=lambda r: (-r["inner_daily_f1"], r["inner_alarm_slots"], r["candidate"]))[0]
            name = selected["candidate"]
            result["pred_selected"] = result[f"pred_daily_{name}"]
            result["score_selected"] = result[f"score_{name}"]
            choice = {"station": held, "candidate": name, "inner_daily_f1": selected["inner_daily_f1"],
                      "threshold": selected["daily_threshold"], "selection_uses_outer_labels": False}
            inner_output.to_parquet(fold_out / "inner_oof.parquet", index=False, compression="zstd")
            (fold_out / "thresholds.json").write_text(json.dumps(thresholds, indent=2), encoding="utf-8")
            (fold_out / "selection.json").write_text(json.dumps(choice, indent=2), encoding="utf-8")
            (fold_out / "references.json").write_text(json.dumps(reference_records, indent=2), encoding="utf-8")
            # 완료 표시는 모든 메타데이터를 기록한 후 마지막에 만든다.
            result.to_parquet(final_path, index=False, compression="zstd")
            all_predictions.append(result)
            all_thresholds.extend(thresholds)
            all_choices.append(choice)
            print(f"{held}: outer complete, inner-selected {name}", flush=True)
    predictions = pd.concat(all_predictions, ignore_index=True)
    predictions.to_parquet(out / "predictions.parquet", index=False, compression="zstd")
    pd.DataFrame(all_thresholds).to_csv(out / "thresholds.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_choices).to_csv(out / "selection.csv", index=False, encoding="utf-8-sig")
    summary = {"status": "nested_development_physical_ice", "smoke": args.smoke,
               "rows": len(predictions), "stations": predictions.station.nunique(),
               "ice_slots": int(predictions.ice.sum()), "feature_sets": feature_sets,
               "signature": signature, "config": config,
               "score_semantics": "Uncalibrated classifier scores; threshold and candidate chosen only inside training stations."}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ["status", "smoke", "rows", "stations", "ice_slots"]}), flush=True)


if __name__ == "__main__":
    main()
