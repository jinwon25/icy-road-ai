"""동일 겨울·제외 지점·정답에서 물리 입력 비선형 노면온도 후보를 비교한다."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive, sha256_file
from src.physical_features import ThermalContext, load_thermal_sources, CONTEXT_FEATURES
from src.validation import assert_training_stations, regression_metrics
from scripts.baseline_ice_logistic import FEATURES


def main():
    private = ROOT / "outputs/private"
    config_path = ROOT / "config/temperature_physics_experiment.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    feature_path = private / "solar_terrain_features/features.parquet"
    data = pd.read_parquet(feature_path)
    target = pd.read_parquet(private / "aws_fallback_features/features.parquet")
    data = data.merge(target[["station", "time", "road_temp"]], on=["station", "time"], how="inner", validate="one_to_one")
    data = data.loc[data.road_temp.notna() & data.asos_air_temp.notna()].copy().reset_index(drop=True)
    assert_training_stations(data.station.unique())
    base = pd.read_parquet(private / "neighbor_transfer/predictions.parquet")
    base = base.loc[base.delay_minutes.eq(0), ["station", "time", "road_temp", "pred_weather", "pred_blend"]]
    expected = data.loc[data.time.ge(config["validate_from"]), ["station", "time", "road_temp"]]
    keys = ["station", "time", "road_temp"]
    pd.testing.assert_frame_equal(expected[keys].sort_values(keys[:2]).reset_index(drop=True), base[keys].sort_values(keys[:2]).reset_index(drop=True))
    physical = json.loads((private / "physical_features/summary.json").read_text(encoding="utf-8"))
    extra = json.loads((private / "solar_terrain_features/summary.json").read_text(encoding="utf-8"))
    feature_sets = {"weather_physical": FEATURES + physical["additional_features"]}
    feature_sets["thermal"] = feature_sets["weather_physical"] + CONTEXT_FEATURES
    feature_sets["terrain"] = feature_sets["thermal"] + extra["terrain_solar_features"]
    feature_sets["radiation"] = feature_sets["terrain"] + extra["retrospective_radiation_features"]
    for cols in feature_sets.values():
        if set(cols) & {"road_temp", "ice", "state_raw", "station", "time"}:
            raise AssertionError("Target included in predictors")
    metadata = pd.read_csv(private / "sensor_availability/metadata.csv", dtype={"station": str})
    metadata = metadata.loc[metadata.kind.eq("RWIS"), ["station", "route", "lat", "lon"]]
    archive = competition_archive(ROOT)
    context = ThermalContext(data, load_thermal_sources(archive), metadata)
    out = private / "temperature_physics"
    out.mkdir(parents=True, exist_ok=True)
    signature = {"features": sha256_file(feature_path), "config": sha256_file(config_path), "runner": sha256_file(Path(__file__)),
                 "context_code": sha256_file(ROOT / "src/physical_features.py"), "archive": sha256_file(archive),
                 "target_features": sha256_file(private / "aws_fallback_features/features.parquet"),
                 "baseline": sha256_file(private / "neighbor_transfer/predictions.parquet")}
    path = out / "input_signature.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != signature:
        raise ValueError("Signature changed; preserve completed outputs")
    path.write_text(json.dumps(signature, indent=2), encoding="utf-8")
    frames = []
    with threadpool_limits(limits=config["max_compute_threads"]):
        for held in sorted(data.station.unique()):
            path = out / f"{held}.parquet"
            if path.exists():
                frames.append(pd.read_parquet(path))
                print(f"{held}: reused", flush=True)
                continue
            train = data.loc[data.station.ne(held) & data.time.lt(config["train_before"])].copy()
            valid = data.loc[data.station.eq(held) & data.time.ge(config["validate_from"])].copy()
            if train.time.max() >= valid.time.min():
                raise AssertionError("Time leakage")
            tx, r1 = context.features(train, {held})
            vx, r2 = context.features(valid, {held})
            train_x, valid_x = pd.concat([train, tx], axis=1), pd.concat([valid, vx], axis=1)
            result = valid[["station", "time", "road_temp"]].copy()
            for name in config["candidates"]:
                model = HistGradientBoostingRegressor(**config["model"])
                model.fit(train_x[feature_sets[name]], train.road_temp)
                result[f"pred_{name}"] = model.predict(valid_x[feature_sets[name]])
            if not np.isfinite(result.filter(like="pred_").to_numpy()).all():
                raise AssertionError("Missing predictions")
            refs = {"held_station": held, "train_rows": len(train), "train_last_time": str(train.time.max()),
                    "validation_first_time": str(valid.time.min()), "fit_references": r1, "validation_references": r2}
            (out / f"{held}_references.json").write_text(json.dumps(refs, indent=2), encoding="utf-8")
            result.to_parquet(path, index=False, compression="zstd")
            frames.append(result)
            print(f"{held}: four temperature candidates complete", flush=True)
    result = pd.concat(frames, ignore_index=True).merge(base, on=keys, how="inner", validate="one_to_one")
    if len(result) != len(base):
        raise AssertionError("Paired comparison lost rows")
    scores = []
    for station, part in result.groupby("station"):
        near = part.road_temp.between(-2, 2)
        for col in result.filter(like="pred_").columns:
            scores.append({"station": station, "variant": col.removeprefix("pred_"),
                           **regression_metrics(part.road_temp, part[col]),
                           "near_rows": int(near.sum()), "near_mae": regression_metrics(part.loc[near, "road_temp"], part.loc[near, col])["mae"]})
    table = pd.DataFrame(scores)
    aggregate = table.groupby("variant")[["mae", "rmse", "bias", "near_mae"]].mean().to_dict(orient="index")
    table.to_csv(out / "station_metrics.csv", index=False, encoding="utf-8-sig")
    result.to_parquet(out / "predictions.parquet", index=False, compression="zstd")
    summary = {"status": "paired_temperature_space_winter_forward", "rows": len(result), "stations": result.station.nunique(),
               "station_macro": aggregate, "config": config, "feature_sets": feature_sets, "signature": signature,
               "limitations": ["All candidates fixed before this experiment; no per-held-station model selection.",
                               "Near-freezing observed-temperature subset is diagnostic only, not an input or Ice metric.",
                               "Historical developmental data have been inspected; this is not a fresh independent holdout.",
                               "Radiation candidate uses delayed public products; retrospective only."]}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(aggregate), flush=True)


if __name__ == "__main__":
    main()
