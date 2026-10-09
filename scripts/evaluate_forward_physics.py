"""공간 제외와 겨울 순서를 함께 지키는 물리·지형·사후 복사 입력 비교."""
from __future__ import annotations
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
from src.validation import assert_training_stations, binary_metrics, daily_scores, macro_scores
from scripts.baseline_ice_logistic import FEATURES, choose_threshold
from scripts.evaluate_physical_ice import threshold_grid


def main():
    private = ROOT / "outputs/private"
    config_path = ROOT / "config/forward_physics_experiment.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    feature_path = private / "solar_terrain_features/features.parquet"
    physical_summary = json.loads((private / "physical_features/summary.json").read_text(encoding="utf-8"))
    extra_summary = json.loads((private / "solar_terrain_features/summary.json").read_text(encoding="utf-8"))
    data = pd.read_parquet(feature_path).reset_index(drop=True)
    data["station"] = data.station.astype(str)
    assert_training_stations(data.station.unique())
    archive = competition_archive(ROOT)
    metadata = pd.read_csv(private / "sensor_availability/metadata.csv", dtype={"station": str})
    metadata = metadata.loc[metadata.kind.eq("RWIS"), ["station", "route", "lat", "lon"]]
    context = ThermalContext(data, load_thermal_sources(archive), metadata)
    feature_sets = {"thermal": FEATURES + physical_summary["additional_features"] + CONTEXT_FEATURES}
    feature_sets["terrain"] = feature_sets["thermal"] + extra_summary["terrain_solar_features"]
    feature_sets["radiation"] = feature_sets["terrain"] + extra_summary["retrospective_radiation_features"]
    splits_path = private / "validation/splits.json"
    splits = json.loads(splits_path.read_text(encoding="utf-8"))["outer_folds"]
    out = private / "forward_physics"
    out.mkdir(parents=True, exist_ok=True)
    signature = {"features": sha256_file(feature_path), "config": sha256_file(config_path), "splits": sha256_file(splits_path),
                 "archive": sha256_file(archive), "runner": sha256_file(Path(__file__)),
                 "context_code": sha256_file(ROOT / "src/physical_features.py"),
                 "threshold_code": sha256_file(ROOT / "src/ice_daily_selection.py")}
    manifest = out / "input_signature.json"
    if manifest.exists() and json.loads(manifest.read_text(encoding="utf-8")) != signature:
        raise ValueError("Experiment signature changed; preserve completed outputs")
    manifest.write_text(json.dumps(signature, indent=2), encoding="utf-8")
    frames, threshold_rows = [], []
    with threadpool_limits(limits=config["max_compute_threads"]):
        for outer in splits:
            held = str(outer["validation_station"])
            folder = out / held
            folder.mkdir(exist_ok=True)
            final = folder / "predictions.parquet"
            if final.exists():
                frames.append(pd.read_parquet(final))
                threshold_rows.extend(json.loads((folder / "thresholds.json").read_text(encoding="utf-8")))
                print(f"{held}: completed fold reused", flush=True)
                continue
            train = data.loc[data.station.ne(held) & data.time.lt(config["train_before"]) & data.ice.notna()].copy()
            valid = data.loc[data.station.eq(held) & data.time.ge(config["validate_from"])].copy()
            if train.time.max() >= valid.time.min() or set(train.station) != set(outer["training_stations"]):
                raise ValueError("Space/time partition mismatch")
            oof = {c["id"]: np.full(len(train), np.nan) for c in config["candidates"]}
            refs = []
            for k, inner in enumerate(outer["inner_folds"]):
                mask = train.station.isin(inner["stations"]).to_numpy()
                fit, check = train.loc[~mask], train.loc[mask]
                forbidden = set(inner["stations"]) | {held}
                tx, r1 = context.features(fit, forbidden)
                vx, r2 = context.features(check, forbidden)
                fit_x, check_x = pd.concat([fit, tx], axis=1), pd.concat([check, vx], axis=1)
                refs.extend([{**r, "inner_fold": k, "role": role} for role, rows in [("fit", r1), ("check", r2)] for r in rows])
                for c in config["candidates"]:
                    model = HistGradientBoostingClassifier(**config["model"], class_weight={0: 1., 1: config["positive_weight"]})
                    columns = feature_sets[c["features"]]
                    model.fit(fit_x[columns], fit.ice.astype(int))
                    oof[c["id"]][mask] = model.predict_proba(check_x[columns])[:, 1]
                print(f"{held}: first-winter inner {k+1}/3 complete", flush=True)
            tx, r1 = context.features(train, {held})
            vx, r2 = context.features(valid, {held})
            train_x, valid_x = pd.concat([train, tx], axis=1), pd.concat([valid, vx], axis=1)
            refs.extend([{**r, "inner_fold": None, "role": role} for role, rows in [("outer_fit", r1), ("outer_check", r2)] for r in rows])
            result = valid[["station", "route", "time", "ice"]].copy()
            inner_output = train[["station", "time", "ice"]].copy()
            thresholds = []
            for c in config["candidates"]:
                name, scores = c["id"], oof[c["id"]]
                if not np.isfinite(scores).all():
                    raise AssertionError("Incomplete OOF")
                slot_t, slot_f1 = choose_threshold(train.ice.to_numpy(dtype=int), scores)
                daily_t, daily_f1, trace = choose_daily_threshold(train, scores, threshold_grid(scores))
                trace.to_csv(folder / f"{name}_trace.csv", index=False, encoding="utf-8-sig")
                thresholds.append({"station": held, "candidate": name, "slot_threshold": slot_t, "daily_threshold": daily_t,
                                   "inner_slot_f1": slot_f1, "inner_daily_f1": daily_f1, "train_rows": len(train), "train_ice": int(train.ice.sum())})
                inner_output[f"score_{name}"] = scores
                model = HistGradientBoostingClassifier(**config["model"], class_weight={0: 1., 1: config["positive_weight"]})
                columns = feature_sets[c["features"]]
                model.fit(train_x[columns], train.ice.astype(int))
                score = model.predict_proba(valid_x[columns])[:, 1]
                if not np.isfinite(score).all():
                    raise AssertionError("Nonfinite prediction")
                result[f"score_{name}"] = score
                result[f"pred_slot_{name}"] = (score >= slot_t).astype(int)
                result[f"pred_daily_{name}"] = (score >= daily_t).astype(int)
            inner_output.to_parquet(folder / "inner_oof.parquet", index=False, compression="zstd")
            (folder / "thresholds.json").write_text(json.dumps(thresholds, indent=2), encoding="utf-8")
            (folder / "references.json").write_text(json.dumps(refs, indent=2), encoding="utf-8")
            result.to_parquet(final, index=False, compression="zstd")
            frames.append(result)
            threshold_rows.extend(thresholds)
            print(f"{held}: second-winter outer complete", flush=True)
    result = pd.concat(frames, ignore_index=True)
    result.to_parquet(out / "predictions.parquet", index=False, compression="zstd")
    pd.DataFrame(threshold_rows).to_csv(out / "thresholds.csv", index=False, encoding="utf-8-sig")
    metrics = {}
    all_days = []
    for c in config["candidates"]:
        for policy in ["slot", "daily"]:
            name = f"{c['id']}_{policy}"
            col = f"pred_{policy}_{c['id']}"
            valid = result.loc[result.ice.notna()]
            records = [(r.station, r.time, int(r.ice) if pd.notna(r.ice) else None, int(getattr(r, col))) for r in result.itertuples()]
            daily = daily_scores(records, minimum_coverage=1.)
            days = pd.DataFrame(daily)
            accepted = days.loc[days.accepted]
            fixed = accepted.loc[(accepted.tp + accepted.fn).gt(0)]
            metrics[name] = {"slot_micro": binary_metrics(valid.ice.astype(int), valid[col]), "daily_station_macro": macro_scores(daily),
                             "fixed_ice_day_f1": float(fixed.groupby("station").f1.mean().mean()),
                             "false_alarm_nonice_days": int(accepted.loc[(accepted.tp + accepted.fn).eq(0), "fp"].gt(0).sum())}
            days["variant"] = name
            all_days.append(days)
            print(name, json.dumps(metrics[name]), flush=True)
    pd.concat(all_days).to_csv(out / "daily_metrics.csv", index=False, encoding="utf-8-sig")
    summary = {"status": "development_space_and_winter_forward", "rows": len(result), "ice_slots": int(result.ice.sum()),
               "metrics": metrics, "feature_sets": feature_sets, "config": config, "signature": signature}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
