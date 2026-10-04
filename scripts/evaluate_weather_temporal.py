"""Supplementary winter-to-winter transfer check, separate from spatial LOSO."""

from __future__ import annotations

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
from src.validation import PROTECTED_STATIONS, assert_training_stations, regression_metrics


def main() -> None:
    data = pd.read_parquet(ROOT / "outputs" / "private" / "weather_features" / "features.parquet")
    data["station"] = data.station.astype(str)
    assert_training_stations(data.station.unique())
    if set(data.station) & PROTECTED_STATIONS:
        raise AssertionError("Protected RWIS entered temporal validation")
    time = pd.to_datetime(data.time)
    minute = time.dt.hour * 60 + time.dt.minute
    day = time.dt.dayofyear + minute / 1440
    data["hour_sin"] = np.sin(2 * np.pi * minute / 1440)
    data["hour_cos"] = np.cos(2 * np.pi * minute / 1440)
    data["season_sin"] = np.sin(2 * np.pi * day / 365.25)
    data["season_cos"] = np.cos(2 * np.pi * day / 365.25)
    data = data.loc[data.asos_air_temp.notna()].copy()
    split = json.loads((ROOT / "outputs" / "private" / "validation" / "splits.json").read_text(encoding="utf-8"))["supplementary_temporal_split"]
    train_period = split["train"]
    validation_period = split["validation"]
    train = data.loc[data.time.between(train_period[0], train_period[1] + " 23:50:00")]
    valid = data.loc[data.time.between(validation_period[0], validation_period[1] + " 23:50:00")].copy()
    if train.empty or valid.empty or not (train.time.max() < valid.time.min()):
        raise AssertionError("Winter transfer periods are invalid")
    offset = float((train.road_temp - train.asos_air_temp).median())
    model = make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
        StandardScaler(), Ridge(alpha=100.0),
    )
    model.fit(train[FEATURES], train.road_temp)
    valid["pred_asos_adjusted"] = valid.asos_air_temp + offset
    valid["pred_weather_ridge"] = model.predict(valid[FEATURES])
    rows = []
    for station, part in valid.groupby("station"):
        base = regression_metrics(part.road_temp, part.pred_asos_adjusted)
        weather = regression_metrics(part.road_temp, part.pred_weather_ridge)
        rows.append({"station": station, "n": len(part),
                     "asos_adjusted_mae": base["mae"], "asos_adjusted_rmse": base["rmse"],
                     "weather_ridge_mae": weather["mae"], "weather_ridge_rmse": weather["rmse"]})
    station_table = pd.DataFrame(rows)
    report = {"status": "supplementary_temporal_transfer_only_not_spatial_holdout",
              "train_period": train_period,
              "validation_period": validation_period,
              "same_station_ids_in_train_and_validation": True,
              "train_rows": len(train), "validation_rows": len(valid),
              "stations": len(station_table),
              "asos_adjusted_station_macro_mae": float(station_table.asos_adjusted_mae.mean()),
              "weather_ridge_station_macro_mae": float(station_table.weather_ridge_mae.mean()),
              "stations_weather_worse": int((station_table.weather_ridge_mae
                                             > station_table.asos_adjusted_mae).sum()),
              "limitations": "same RWIS sites are in both winters; does not test unknown-road spatial transfer"}
    out = ROOT / "outputs" / "private" / "weather_temporal"
    out.mkdir(parents=True, exist_ok=True)
    station_table.to_csv(out / "station_metrics.csv", index=False, encoding="utf-8-sig")
    valid[["station", "time", "road_temp", "pred_asos_adjusted", "pred_weather_ridge"]].to_parquet(
        out / "predictions.parquet", index=False, compression="zstd")
    (out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
