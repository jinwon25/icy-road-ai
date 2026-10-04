"""Make paired development-only LOSO comparison of nearest and fallback AWS."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validation import PROTECTED_STATIONS, regression_metrics


def main() -> None:
    private = ROOT / "outputs" / "private"
    nearest = pd.read_parquet(private / "weather_ridge" / "predictions.parquet")
    fallback = pd.read_parquet(private / "aws_fallback_ridge" / "predictions.parquet")
    nearest["station"] = nearest.station.astype(str)
    fallback["station"] = fallback.station.astype(str)
    if set(nearest.station) & PROTECTED_STATIONS or set(fallback.station) & PROTECTED_STATIONS:
        raise AssertionError("Protected RWIS entered model comparison")
    joined = nearest.merge(fallback, on=["station", "time"], how="outer",
                           validate="one_to_one", indicator=True,
                           suffixes=("_nearest", "_fallback"))
    if not joined._merge.eq("both").all() or len(joined) != len(nearest) or len(joined) != len(fallback):
        raise AssertionError("Weather variants use different evaluation times")
    if not joined.road_temp_nearest.equals(joined.road_temp_fallback):
        raise AssertionError("Variants have different road-temperature truth")
    if not joined.pred_asos_adjusted_nearest.equals(joined.pred_asos_adjusted_fallback):
        raise AssertionError("Variants have different ASOS baseline predictions")
    records = []
    for station, part in joined.groupby("station", sort=True):
        near = part.road_temp_nearest.between(-2, 2)
        first = regression_metrics(part.road_temp_nearest, part.pred_weather_ridge_nearest)
        second = regression_metrics(part.road_temp_nearest, part.pred_weather_ridge_fallback)
        first_near = regression_metrics(part.loc[near, "road_temp_nearest"],
                                        part.loc[near, "pred_weather_ridge_nearest"])
        second_near = regression_metrics(part.loc[near, "road_temp_nearest"],
                                         part.loc[near, "pred_weather_ridge_fallback"])
        base = regression_metrics(part.road_temp_nearest, part.pred_asos_adjusted_nearest)
        records.append({"station": station, "n": len(part), "near_freezing_n": int(near.sum()),
                        "asos_adjusted_mae": base["mae"],
                        "nearest_bias": first["bias"], "fallback_bias": second["bias"],
                        "nearest_mae": first["mae"], "fallback_mae": second["mae"],
                        "nearest_rmse": first["rmse"], "fallback_rmse": second["rmse"],
                        "nearest_near_mae": first_near["mae"],
                        "fallback_near_mae": second_near["mae"]})
    table = pd.DataFrame(records)
    overall = table.loc[table.station.eq("12209")].iloc[0].to_dict()
    summary = {"status": "development_only_paired_loso_input_ablation",
               "pairing": "same 14 held-out development stations and exact station/time rows; fixed Ridge alpha=100",
               "bias_definition": "prediction minus observation",
               "stations": len(table), "paired_rows": len(joined),
               "nearest_macro_mae": float(table.nearest_mae.mean()),
               "fallback_macro_mae": float(table.fallback_mae.mean()),
               "nearest_macro_rmse": float(table.nearest_rmse.mean()),
               "fallback_macro_rmse": float(table.fallback_rmse.mean()),
               "stations_fallback_mae_better": int(table.fallback_mae.lt(table.nearest_mae).sum()),
               "stations_fallback_near_mae_worse": table.loc[
                   table.fallback_near_mae.gt(table.nearest_near_mae), "station"].tolist(),
               "station_12209": overall}
    out = private / "weather_fallback_comparison"
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "station_metrics.csv", index=False, encoding="utf-8-sig")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
