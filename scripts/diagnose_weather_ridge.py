"""Summarize OOF failures by winter and AWS availability without refitting."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validation import PROTECTED_STATIONS


def main() -> None:
    private = ROOT / "outputs" / "private"
    prediction = pd.read_parquet(private / "weather_ridge" / "predictions.parquet")
    features = pd.read_parquet(private / "weather_features" / "features.parquet",
                               columns=["station", "time", "aws_air_temp"])
    joined = prediction.merge(features, on=["station", "time"], validate="one_to_one")
    if set(joined.station.astype(str)) & PROTECTED_STATIONS:
        raise AssertionError("Protected RWIS entered diagnostic table")
    joined["winter_start_year"] = joined.time.dt.year.where(
        joined.time.dt.month.ge(11), joined.time.dt.year - 1)
    joined["aws_available"] = joined.aws_air_temp.notna()
    joined["baseline_abs_error"] = (joined.pred_asos_adjusted - joined.road_temp).abs()
    joined["weather_abs_error"] = (joined.pred_weather_ridge - joined.road_temp).abs()
    joined["near_freezing"] = joined.road_temp.between(-2, 2)
    records = []
    for (station, winter, available), part in joined.groupby(
            ["station", "winter_start_year", "aws_available"], sort=True):
        near = part.loc[part.near_freezing]
        records.append({"station": str(station), "winter_start_year": int(winter),
                        "aws_available": bool(available), "n": len(part),
                        "baseline_mae": float(part.baseline_abs_error.mean()),
                        "weather_mae": float(part.weather_abs_error.mean()),
                        "near_freezing_n": len(near),
                        "baseline_near_mae": float(near.baseline_abs_error.mean()) if len(near) else None,
                        "weather_near_mae": float(near.weather_abs_error.mean()) if len(near) else None})
    table = pd.DataFrame(records)
    station_scores = pd.read_csv(private / "weather_ridge" / "station_metrics.csv",
                                 dtype={"station": str})
    summary = {"status": "development_oof_diagnostic_only",
               "groups": len(table), "rows": len(joined),
               "weather_worse_stations": station_scores.loc[
                   station_scores.weather_ridge_mae.gt(station_scores.asos_adjusted_mae),
                   "station"].tolist(),
               "near_freezing_worse_stations": station_scores.loc[
                   station_scores.weather_ridge_near_mae.gt(station_scores.asos_adjusted_near_mae),
                   "station"].tolist(),
               "strata": "station × winter start year × nearest AWS air-temperature availability"}
    out = private / "weather_ridge"
    table.to_csv(out / "winter_availability_diagnostic.csv", index=False, encoding="utf-8-sig")
    (out / "diagnostic_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
