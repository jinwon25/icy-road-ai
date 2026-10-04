"""Paired LOSO test: prior weather versus prior weather plus facility proximity."""
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.baseline_weather_ridge import FEATURES
from src.validation import PROTECTED_STATIONS, assert_training_stations, regression_metrics

PRIVATE = ROOT / "outputs" / "private"
STATIC = ["log_bridge_distance_m", "log_tunnel_distance_m"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facility-type", choices=("nearest", "route"), default="nearest")
    args = parser.parse_args()
    static_folder = "station_facility_route" if args.facility_type == "route" else "station_facility"
    data = pd.read_parquet(PRIVATE / "aws_fallback_features" / "features.parquet")
    static = pd.read_csv(PRIVATE / "spatial" / static_folder / "features.csv",
                         dtype={"station": str}, encoding="utf-8-sig")
    baseline = pd.read_parquet(PRIVATE / "aws_fallback_ridge" / "predictions.parquet")
    for frame in (data, static, baseline):
        frame["station"] = frame.station.astype(str)
        assert_training_stations(frame.station.unique())
        if set(frame.station) & PROTECTED_STATIONS:
            raise AssertionError("Protected RWIS entered facility ablation")
    if static.station.duplicated().any():
        raise ValueError("Duplicate static station")
    data = data.merge(static, on="station", how="left", validate="many_to_one")
    if data[["bridge_distance_m", "tunnel_distance_m"]].isna().any().any():
        raise ValueError("Missing development facility distances")
    for kind in ("bridge", "tunnel"):
        data[f"log_{kind}_distance_m"] = np.log1p(data[f"{kind}_distance_m"])
    time = pd.to_datetime(data.time)
    minute = time.dt.hour * 60 + time.dt.minute
    day = time.dt.dayofyear + minute / 1440
    data["hour_sin"] = np.sin(2 * np.pi * minute / 1440)
    data["hour_cos"] = np.cos(2 * np.pi * minute / 1440)
    data["season_sin"] = np.sin(2 * np.pi * day / 365.25)
    data["season_cos"] = np.cos(2 * np.pi * day / 365.25)
    data = data.loc[data.asos_air_temp.notna()].copy()
    data = data.merge(baseline[["station", "time", "road_temp", "pred_weather_ridge"]],
                      on=["station", "time"], how="outer", validate="one_to_one",
                      indicator=True, suffixes=("", "_baseline"))
    if not data._merge.eq("both").all() or len(data) != len(baseline):
        raise AssertionError("Weather and static variants have different evaluation rows")
    if not data.road_temp.equals(data.road_temp_baseline):
        raise AssertionError("Weather and static variants have different outcomes")
    records = []
    predictions = []
    for held in sorted(data.station.unique()):
        train = data.loc[data.station.ne(held)]
        valid = data.loc[data.station.eq(held)].copy()
        model = make_pipeline(SimpleImputer(strategy="median", add_indicator=True,
                                            keep_empty_features=True),
                              StandardScaler(), Ridge(alpha=100.0))
        model.fit(train[FEATURES + STATIC], train.road_temp)
        valid["pred_weather_facility"] = model.predict(valid[FEATURES + STATIC])
        weather = regression_metrics(valid.road_temp, valid.pred_weather_ridge)
        combined = regression_metrics(valid.road_temp, valid.pred_weather_facility)
        near = valid.road_temp.between(-2, 2)
        weather_near = regression_metrics(valid.loc[near, "road_temp"],
                                          valid.loc[near, "pred_weather_ridge"])
        combined_near = regression_metrics(valid.loc[near, "road_temp"],
                                           valid.loc[near, "pred_weather_facility"])
        records.append({"station": held, "n": len(valid), "near_freezing_n": int(near.sum()),
                        "bridge_distance_m": float(valid.bridge_distance_m.iloc[0]),
                        "tunnel_distance_m": float(valid.tunnel_distance_m.iloc[0]),
                        "weather_bias": weather["bias"], "facility_bias": combined["bias"],
                        "weather_mae": weather["mae"], "facility_mae": combined["mae"],
                        "weather_rmse": weather["rmse"], "facility_rmse": combined["rmse"],
                        "weather_near_mae": weather_near["mae"],
                        "facility_near_mae": combined_near["mae"]})
        predictions.append(valid[["station", "time", "road_temp", "pred_weather_ridge",
                                  "pred_weather_facility"]])
        print(f"{held}: {weather['mae']:.3f} -> {combined['mae']:.3f} C", flush=True)
    table = pd.DataFrame(records)
    pred = pd.concat(predictions, ignore_index=True)
    summary = {"status": "development_only_paired_loso_facility_ablation",
               "validation": "14 held-out RWIS stations; both winters; identical 483095 rows",
               "baseline": "prior ASOS/AWS fallback Ridge alpha=100",
               "addition": "log1p projected distance in m to nearest supplied bridge/tunnel polygons",
               "facility_type": args.facility_type,
               "bias_definition": "prediction minus observation",
               "stations": len(table), "paired_rows": len(pred),
               "weather_macro_mae": float(table.weather_mae.mean()),
               "facility_macro_mae": float(table.facility_mae.mean()),
               "weather_macro_rmse": float(table.weather_rmse.mean()),
               "facility_macro_rmse": float(table.facility_rmse.mean()),
               "weather_macro_near_mae": float(table.weather_near_mae.mean()),
               "facility_macro_near_mae": float(table.facility_near_mae.mean()),
               "stations_facility_mae_better": int(table.facility_mae.lt(table.weather_mae).sum()),
               "stations_facility_near_mae_better": int(table.facility_near_mae.lt(table.weather_near_mae).sum()),
               "station_delta_mae": dict(zip(table.station, (table.facility_mae - table.weather_mae).round(4))),
               "limitation": "Facility data vintage is unverified; only 14 station-level spatial units; exploratory, not final model selection.",
               "python": platform.python_version(), "sklearn": sklearn.__version__}
    out = PRIVATE / ("route_facility_weather_comparison" if args.facility_type == "route"
                     else "facility_weather_comparison")
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "station_metrics.csv", index=False, encoding="utf-8-sig")
    pred.to_parquet(out / "predictions.parquet", index=False, compression="zstd")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
