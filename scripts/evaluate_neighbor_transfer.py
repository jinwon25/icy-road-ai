"""Fixed weather/RWIS blend: unseen station AND next-winter validation.

No tuning: Ridge alpha=100, 1:1 blending; delay scenarios are sensitivity checks.
Only development caches are read. Missing neighbors fall back to weather Ridge.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.baseline_weather_ridge import FEATURES
from src.neighbor_validation import delayed_neighbor_join, winter_station_split
from src.validation import assert_training_stations, regression_metrics
from src.weather_features import haversine_km

PRIVATE = ROOT / "outputs" / "private"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    feature_path = PRIVATE / "aws_fallback_features/features.parquet"
    data = pd.read_parquet(feature_path)
    data["station"] = data.station.astype(str)
    assert_training_stations(data.station.unique())
    if data.duplicated(["station", "time"]).any():
        raise ValueError("Duplicate development targets")
    time = pd.to_datetime(data.time)
    minute = time.dt.hour * 60 + time.dt.minute
    day = time.dt.dayofyear + minute / 1440
    for name, value, period in (("hour", minute, 1440), ("season", day, 365.25)):
        data[name + "_sin"] = np.sin(2 * np.pi * value / period)
        data[name + "_cos"] = np.cos(2 * np.pi * value / period)
    eligible = data.loc[data.asos_air_temp.notna()].copy()
    periods = json.loads((ROOT / "config/evaluation.json").read_text(encoding="utf-8"))["evaluation_periods"]
    meta = pd.read_csv(PRIVATE / "full/station_inventory.csv", dtype=str)
    meta = meta.loc[meta.kind.eq("RWIS") & meta.protected.eq("False")
                    & meta.station_id.isin(data.station.unique())].set_index("station_id")
    assert_training_stations(meta.index)
    if len(meta) != data.station.nunique():
        raise ValueError("Development metadata mismatch")
    ids = sorted(data.station.unique())[:2] if args.smoke else sorted(data.station.unique())
    scores, predictions, manifests = [], [], []
    for held in ids:
        train, valid = winter_station_split(eligible, held, periods[0], periods[1])
        model = make_pipeline(SimpleImputer(strategy="median", add_indicator=True,
                                            keep_empty_features=True),
                              StandardScaler(), Ridge(alpha=100.0))
        model.fit(train[FEATURES], train.road_temp)
        valid["pred_weather"] = model.predict(valid[FEATURES])
        target_meta = meta.loc[held]
        candidates = meta.loc[meta.routes.eq(target_meta.routes) & meta.index.to_series().ne(held)]
        distances = {sid: haversine_km(float(target_meta.latitudes), float(target_meta.longitudes),
                                      float(row.latitudes), float(row.longitudes))
                     for sid, row in candidates.iterrows()}
        if not distances:
            raise ValueError(f"No same-route reference: {held}")
        source_id = min(distances, key=lambda sid: (distances[sid], sid))
        source = data.loc[data.station.eq(source_id), ["time", "road_temp"]]
        manifests.append({"held_station": held, "train_stations": sorted(train.station.unique()),
                          "train_start": str(train.time.min()), "train_end": str(train.time.max()),
                          "train_rows": len(train), "valid_start": str(valid.time.min()),
                          "valid_end": str(valid.time.max()), "reference_station": source_id})
        for delay in (0, 10, 30, 60):
            joined = delayed_neighbor_join(valid[["station", "time", "road_temp", "pred_weather"]],
                                            source, delay, max_age_minutes=60)
            joined["pred_blend"] = ((joined.pred_weather + joined.neighbor_road_temp) / 2).fillna(joined.pred_weather)
            joined["source_station"] = source_id
            joined["delay_minutes"] = delay
            near = joined.road_temp.between(-2, 2)
            row = {"station": held, "delay_minutes": delay, "source_station": source_id,
                   "source_distance_km": distances[source_id], "rows": len(joined),
                   "neighbor_available_rows": int(joined.neighbor_road_temp.notna().sum()),
                   "near_rows": int(near.sum())}
            for name in ("weather", "blend"):
                metric = regression_metrics(joined.road_temp, joined["pred_" + name])
                row.update({name + "_" + k: v for k, v in metric.items() if k != "n"})
                row[name + "_near_mae"] = regression_metrics(joined.loc[near, "road_temp"],
                                                              joined.loc[near, "pred_" + name])["mae"]
            scores.append(row)
            predictions.append(joined)
        print(f"Completed held station {held}, reference {source_id}", flush=True)
    metrics = pd.DataFrame(scores)
    scenarios = []
    for delay, part in metrics.groupby("delay_minutes"):
        scenarios.append({"delay_minutes": int(delay), "stations": len(part),
                          "rows": int(part.rows.sum()),
                          "neighbor_available_rows": int(part.neighbor_available_rows.sum()),
                          "stations_blend_better": int(part.blend_mae.lt(part.weather_mae).sum()),
                          **{col + "_macro": float(part[col].mean()) for col in
                             ("weather_mae", "blend_mae", "weather_rmse", "blend_rmse",
                              "weather_bias", "blend_bias", "weather_near_mae", "blend_near_mae")}})
    source_config = json.loads((ROOT / "config/data_source.json").read_text(encoding="utf-8"))
    summary = {"status": "development_only_spatiotemporal_transfer",
               "data_release": source_config["release"], "archive_sha256": source_config["sha256"],
               "smoke": args.smoke, "train_period": periods[0], "validation_period": periods[1],
               "validation": "first-winter other stations train; second-winter held station test",
               "reference_policy": "nearest other development station same route, prior observations available by scenario delay",
               "source_max_age_minutes": 60, "ridge_alpha": 100.0, "weather_weight": 0.5,
               "missing_neighbor_policy": "weather_only; identical target denominator across all scenarios",
               "source_features_sha256": hashlib.sha256(feature_path.read_bytes()).hexdigest(),
               "scenarios": scenarios,
               "limitations": ["Publication delays are assumed, not verified.",
                               "Existing weather-input delays unchanged; only RWIS latency varied.",
                               "Compare only within a single audited release and matching target rows.",
                               "Does not establish Ice classification or risk-map quality."]}
    out = PRIVATE / ("smoke_neighbor_transfer" if args.smoke else "neighbor_transfer")
    out.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(out / "station_metrics.csv", index=False, encoding="utf-8-sig")
    pd.concat(predictions, ignore_index=True).to_parquet(out / "predictions.parquet", index=False, compression="zstd")
    (out / "fold_manifest.json").write_text(json.dumps(manifests, indent=2), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
