"""Fixed Ridge weather-only baseline under leave-one-RWIS-station-out validation."""

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
from src.validation import PROTECTED_STATIONS, assert_training_stations, regression_metrics

FEATURES = ["asos_air_temp", "aws_air_temp", "aws_humidity", "aws_wind_speed",
            "aws_rain_15m", "aws_dewpoint", "aws_age_minutes", "asos_age_minutes",
            "aws_distance_km", "asos_distance_km", "hour_sin", "hour_cos",
            "season_sin", "season_cos"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Use the two-day feature sample")
    parser.add_argument("--variant", choices=("nearest", "fallback"), default="nearest")
    args = parser.parse_args()
    if args.variant == "nearest":
        input_name = "smoke" if args.smoke else "weather_features"
        output_name = "smoke_weather_ridge" if args.smoke else "weather_ridge"
    else:
        input_name = "smoke_aws_fallback_features" if args.smoke else "aws_fallback_features"
        output_name = "smoke_aws_fallback_ridge" if args.smoke else "aws_fallback_ridge"
    input_dir = ROOT / "outputs" / "private" / input_name
    data = pd.read_parquet(input_dir / "features.parquet")
    data["station"] = data.station.astype(str)
    assert_training_stations(data.station.unique())
    if set(data.station) & PROTECTED_STATIONS:
        raise AssertionError("Protected RWIS entered weather baseline")
    time = pd.to_datetime(data.time)
    minute = time.dt.hour * 60 + time.dt.minute
    day = time.dt.dayofyear + minute / 1440
    data["hour_sin"] = np.sin(2 * np.pi * minute / 1440)
    data["hour_cos"] = np.cos(2 * np.pi * minute / 1440)
    data["season_sin"] = np.sin(2 * np.pi * day / 365.25)
    data["season_cos"] = np.cos(2 * np.pi * day / 365.25)
    # A paired comparison avoids changing the denominator between weather and ASOS baselines.
    data = data.loc[data.asos_air_temp.notna()].copy()
    ids = sorted(data.station.unique())
    output = []
    scores = []
    for held in ids:
        train = data.loc[data.station.ne(held)]
        valid = data.loc[data.station.eq(held)].copy()
        if train.station.eq(held).any():
            raise AssertionError("Held-out station entered Ridge fitting")
        offset = float((train.road_temp - train.asos_air_temp).median())
        model = make_pipeline(
            SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
            StandardScaler(), Ridge(alpha=100.0),
        )
        model.fit(train[FEATURES], train.road_temp)
        valid["pred_asos_adjusted"] = valid.asos_air_temp + offset
        valid["pred_weather_ridge"] = model.predict(valid[FEATURES])
        base = regression_metrics(valid.road_temp, valid.pred_asos_adjusted)
        weather = regression_metrics(valid.road_temp, valid.pred_weather_ridge)
        near = valid.road_temp.between(-2, 2)
        base_near = regression_metrics(valid.loc[near, "road_temp"],
                                       valid.loc[near, "pred_asos_adjusted"])
        weather_near = regression_metrics(valid.loc[near, "road_temp"],
                                          valid.loc[near, "pred_weather_ridge"])
        scores.append({"station": held, "n": len(valid),
                       "aws_available": int(valid.aws_air_temp.notna().sum()),
                       "asos_adjusted_bias": base["bias"], "asos_adjusted_mae": base["mae"],
                       "asos_adjusted_rmse": base["rmse"],
                       "weather_ridge_bias": weather["bias"], "weather_ridge_mae": weather["mae"],
                       "weather_ridge_rmse": weather["rmse"],
                       "near_freezing_n": int(near.sum()),
                       "asos_adjusted_near_mae": base_near["mae"],
                       "weather_ridge_near_mae": weather_near["mae"]})
        output.append(valid[["station", "time", "road_temp", "pred_asos_adjusted",
                             "pred_weather_ridge", "aws_source_time", "asos_source_time"]])
    score_table = pd.DataFrame(scores)
    predictions = pd.concat(output, ignore_index=True)
    summary = {
        "status": "development_only_fixed_weather_ridge",
        "aws_variant": args.variant,
        "validation": "leave one RWIS station out; both winters; no station ID feature",
        "paired_denominator": "all development targets with prior ASOS air temperature",
        "bias_definition": "prediction minus observation",
        "features": FEATURES,
        "imputation": "median and missing indicators fit inside each training fold",
        "ridge_alpha": 100.0,
        "stations": len(score_table), "paired_rows": len(predictions),
        "near_freezing_rows": int(score_table.near_freezing_n.sum()),
        "asos_adjusted_station_macro_mae": float(score_table.asos_adjusted_mae.mean()),
        "weather_ridge_station_macro_mae": float(score_table.weather_ridge_mae.mean()),
        "asos_adjusted_station_macro_rmse": float(score_table.asos_adjusted_rmse.mean()),
        "weather_ridge_station_macro_rmse": float(score_table.weather_ridge_rmse.mean()),
        "asos_adjusted_station_macro_bias": float(score_table.asos_adjusted_bias.mean()),
        "weather_ridge_station_macro_bias": float(score_table.weather_ridge_bias.mean()),
        "stations_weather_worse": int((score_table.weather_ridge_mae
                                        > score_table.asos_adjusted_mae).sum()),
        "python": platform.python_version(), "sklearn": sklearn.__version__,
    }
    out = ROOT / "outputs" / "private" / output_name
    out.mkdir(parents=True, exist_ok=True)
    score_table.to_csv(out / "station_metrics.csv", index=False, encoding="utf-8-sig")
    predictions.to_parquet(out / "predictions.parquet", index=False, compression="zstd")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("stations", "paired_rows", "asos_adjusted_station_macro_mae",
                       "weather_ridge_station_macro_mae", "stations_weather_worse")}), flush=True)


if __name__ == "__main__":
    main()
