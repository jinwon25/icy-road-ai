"""같은 열·수분 입력에서 대칭 트리 CatBoost를 겨울·공간 제외로 검증한다."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import catboost
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier

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
    config_path = ROOT / "config/catboost_forward_experiment.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    feature_path = private / "physical_features/features.parquet"
    data = pd.read_parquet(feature_path).reset_index(drop=True)
    assert_training_stations(data.station.unique())
    info = json.loads((private / "physical_features/summary.json").read_text(encoding="utf-8"))
    columns = FEATURES + info["additional_features"] + CONTEXT_FEATURES
    splits_path = private / "validation/splits.json"
    splits = json.loads(splits_path.read_text(encoding="utf-8"))["outer_folds"]
    archive = competition_archive(ROOT)
    metadata = pd.read_csv(private / "sensor_availability/metadata.csv", dtype={"station": str})
    metadata = metadata.loc[metadata.kind.eq("RWIS"), ["station", "route", "lat", "lon"]]
    context = ThermalContext(data, load_thermal_sources(archive), metadata)
    out = private / "catboost_forward"
    out.mkdir(parents=True, exist_ok=True)
    signature = {"features": sha256_file(feature_path), "splits": sha256_file(splits_path), "config": sha256_file(config_path),
                 "runner": sha256_file(Path(__file__)), "context": sha256_file(ROOT / "src/physical_features.py"),
                 "threshold": sha256_file(ROOT / "src/ice_daily_selection.py"), "archive": sha256_file(archive), "catboost_version": catboost.__version__}
    path = out / "input_signature.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != signature:
        raise ValueError("Experiment signature changed; preserve outputs")
    path.write_text(json.dumps(signature, indent=2), encoding="utf-8")
    frames, choices = [], []
    for outer in splits:
        held = str(outer["validation_station"])
        folder = out / held
        folder.mkdir(exist_ok=True)
        path = folder / "predictions.parquet"
        if path.exists():
            frames.append(pd.read_parquet(path))
            choices.append(json.loads((folder / "thresholds.json").read_text(encoding="utf-8")))
            print(f"{held}: reused", flush=True)
            continue
        train = data.loc[data.station.ne(held) & data.time.lt(config["train_before"]) & data.ice.notna()].copy()
        valid = data.loc[data.station.eq(held) & data.time.ge(config["validate_from"])].copy()
        if train.time.max() >= valid.time.min() or set(train.station) != set(outer["training_stations"]):
            raise AssertionError("Space/time partition mismatch")
        scores = np.full(len(train), np.nan)
        refs = []
        for k, inner in enumerate(outer["inner_folds"]):
            mask = train.station.isin(inner["stations"]).to_numpy()
            fit, check = train.loc[~mask], train.loc[mask]
            forbidden = set(inner["stations"]) | {held}
            tx, r1 = context.features(fit, forbidden)
            vx, r2 = context.features(check, forbidden)
            fit_x, check_x = pd.concat([fit, tx], axis=1), pd.concat([check, vx], axis=1)
            model = CatBoostClassifier(**config["model"])
            model.fit(fit_x[columns], fit.ice.astype(int))
            scores[mask] = model.predict_proba(check_x[columns])[:, 1]
            refs.extend([{**r, "fold": k, "role": role} for role, rows in [("fit", r1), ("check", r2)] for r in rows])
            print(f"{held}: CatBoost inner {k+1}/3 complete", flush=True)
        if not np.isfinite(scores).all():
            raise AssertionError("Missing OOF")
        slot_t, slot_f1 = choose_threshold(train.ice.to_numpy(dtype=int), scores)
        daily_t, daily_f1, trace = choose_daily_threshold(train, scores, threshold_grid(scores))
        choice = {"station": held, "slot_threshold": slot_t, "daily_threshold": daily_t, "inner_slot_f1": slot_f1, "inner_daily_f1": daily_f1}
        tx, r1 = context.features(train, {held})
        vx, r2 = context.features(valid, {held})
        train_x, valid_x = pd.concat([train, tx], axis=1), pd.concat([valid, vx], axis=1)
        refs.extend([{**r, "fold": None, "role": role} for role, rows in [("outer_fit", r1), ("outer_check", r2)] for r in rows])
        model = CatBoostClassifier(**config["model"])
        model.fit(train_x[columns], train.ice.astype(int))
        score = model.predict_proba(valid_x[columns])[:, 1]
        result = valid[["station", "time", "ice"]].copy()
        result["score_catboost"] = score
        result["pred_catboost_slot"] = (score >= slot_t).astype(int)
        result["pred_catboost_daily"] = (score >= daily_t).astype(int)
        model.save_model(str(folder / "development_model.cbm"))
        pd.DataFrame({"feature": columns, "importance": model.feature_importances_}).to_csv(folder / "feature_importance.csv", index=False)
        inner_output = train[["station", "time", "ice"]].copy()
        inner_output["score_catboost"] = scores
        inner_output.to_parquet(folder / "inner_oof.parquet", index=False, compression="zstd")
        trace.to_csv(folder / "threshold_trace.csv", index=False)
        (folder / "thresholds.json").write_text(json.dumps(choice, indent=2), encoding="utf-8")
        (folder / "references.json").write_text(json.dumps(refs, indent=2), encoding="utf-8")
        result.to_parquet(path, index=False, compression="zstd")
        frames.append(result)
        choices.append(choice)
        print(f"{held}: CatBoost next-winter complete", flush=True)
    result = pd.concat(frames, ignore_index=True).sort_values(["station", "time"]).reset_index(drop=True)
    reference = pd.read_parquet(private / "forward_physics/predictions.parquet").sort_values(["station", "time"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(result[["station", "time", "ice"]], reference[["station", "time", "ice"]])
    result["pred_hgb_daily"] = reference.pred_daily_thermal
    metrics, day_frames = {}, []
    for variant in ["catboost_slot", "catboost_daily", "hgb_daily"]:
        col = "pred_" + variant
        valid = result.loc[result.ice.notna()]
        records = [(r.station, r.time, int(r.ice) if pd.notna(r.ice) else None, int(getattr(r, col))) for r in result.itertuples()]
        daily = daily_scores(records, minimum_coverage=1.)
        days = pd.DataFrame(daily)
        accepted = days.loc[days.accepted]
        fixed = accepted.loc[(accepted.tp + accepted.fn).gt(0)]
        metrics[variant] = {"slot_micro": binary_metrics(valid.ice.astype(int), valid[col]), "daily_station_macro": macro_scores(daily),
                            "fixed_ice_day_f1": float(fixed.groupby("station").f1.mean().mean()),
                            "false_alarm_nonice_days": int(accepted.loc[(accepted.tp + accepted.fn).eq(0), "fp"].gt(0).sum())}
        days["variant"] = variant
        day_frames.append(days)
    result.to_parquet(out / "predictions.parquet", index=False, compression="zstd")
    pd.DataFrame(choices).to_csv(out / "thresholds.csv", index=False)
    pd.concat(day_frames).to_csv(out / "daily_metrics.csv", index=False, encoding="utf-8-sig")
    summary = {"status": "catboost_space_winter_forward", "rows": len(result), "metrics": metrics, "features": columns, "signature": signature, "config": config}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics), flush=True)


if __name__ == "__main__":
    main()
