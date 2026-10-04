"""Prior-only nearest same-route RWIS road-temperature interpolation baseline.

This is a nonparametric benchmark. Each target station is absent from its own
reference set, and the three official protected RWIS are absent entirely.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validation import PROTECTED_STATIONS, assert_training_stations, regression_metrics
from src.weather_features import haversine_km, prior_join

PRIVATE = ROOT / "outputs" / "private"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="Evaluate first two target stations")
    args = parser.parse_args()
    data = pd.read_parquet(PRIVATE / "aws_fallback_features" / "features.parquet",
                           columns=["station", "route", "time", "road_temp", "asos_air_temp"])
    data["station"] = data.station.astype(str)
    assert_training_stations(data.station.unique())
    if set(data.station) & PROTECTED_STATIONS or data.duplicated(["station", "time"]).any():
        raise AssertionError("Protected or duplicate RWIS source/target")
    baseline = pd.read_parquet(PRIVATE / "aws_fallback_ridge" / "predictions.parquet",
                               columns=["station", "time", "road_temp", "pred_weather_ridge"])
    baseline["station"] = baseline.station.astype(str)
    assert_training_stations(baseline.station.unique())
    metadata = pd.read_csv(PRIVATE / "full" / "station_inventory.csv", dtype=str,
                           encoding="utf-8-sig")
    stations = metadata.loc[metadata.kind.eq("RWIS") & metadata.protected.eq("False")
                            & metadata.station_id.isin(data.station.unique())].copy()
    if len(stations) != data.station.nunique() or set(stations.station_id) & PROTECTED_STATIONS:
        raise AssertionError("Development station metadata mismatch")
    stations["lat"] = pd.to_numeric(stations.latitudes, errors="raise")
    stations["lon"] = pd.to_numeric(stations.longitudes, errors="raise")
    stations = stations.set_index("station_id")
    ids = sorted(data.station.unique())
    if args.smoke:
        ids = ids[:2]
    outputs = []
    table = []
    for target_id in ids:
        target_meta = stations.loc[target_id]
        candidates = stations.loc[stations.routes.eq(target_meta.routes)
                                  & stations.index.to_series().ne(target_id)]
        if candidates.empty:
            raise ValueError(f"No same-route development RWIS source for {target_id}")
        distances = {candidate_id: haversine_km(target_meta.lat, target_meta.lon,
                                                 candidate.lat, candidate.lon)
                     for candidate_id, candidate in candidates.iterrows()}
        source_id = min(distances, key=distances.get)
        source = data.loc[data.station.eq(source_id), ["time", "road_temp"]].copy()
        source = source.rename(columns={"time": "source_time"})
        target = data.loc[data.station.eq(target_id) & data.asos_air_temp.notna(),
                          ["station", "time", "road_temp"]].copy()
        joined = prior_join(target, source, "neighbor", tolerance_minutes=30)
        joined["source_station"] = source_id
        joined["source_distance_km"] = distances[source_id]
        joined = joined.merge(baseline[["station", "time", "road_temp", "pred_weather_ridge"]],
                              on=["station", "time"], how="left", validate="one_to_one",
                              suffixes=("", "_baseline"))
        if joined.pred_weather_ridge.isna().any() or not joined.road_temp.equals(joined.road_temp_baseline):
            raise AssertionError("Weather Ridge comparison is not paired")
        joined["pred_equal_blend"] = (joined.neighbor_road_temp + joined.pred_weather_ridge) / 2
        paired = joined.loc[joined.neighbor_road_temp.notna()]
        source_score = regression_metrics(paired.road_temp, paired.neighbor_road_temp)
        weather_score = regression_metrics(paired.road_temp, paired.pred_weather_ridge)
        blend_score = regression_metrics(paired.road_temp, paired.pred_equal_blend)
        near = paired.road_temp.between(-2, 2)
        source_near = regression_metrics(paired.loc[near, "road_temp"],
                                         paired.loc[near, "neighbor_road_temp"])
        weather_near = regression_metrics(paired.loc[near, "road_temp"],
                                          paired.loc[near, "pred_weather_ridge"])
        blend_near = regression_metrics(paired.loc[near, "road_temp"],
                                        paired.loc[near, "pred_equal_blend"])
        table.append({"station": target_id, "source_station": source_id,
                      "source_distance_km": distances[source_id], "target_rows": len(joined),
                      "paired_rows": len(paired), "near_freezing_rows": int(near.sum()),
                      "neighbor_bias": source_score["bias"], "neighbor_mae": source_score["mae"],
                      "neighbor_rmse": source_score["rmse"], "weather_bias": weather_score["bias"],
                      "weather_mae": weather_score["mae"], "weather_rmse": weather_score["rmse"],
                      "blend_bias": blend_score["bias"], "blend_mae": blend_score["mae"],
                      "blend_rmse": blend_score["rmse"],
                      "neighbor_near_mae": source_near["mae"],
                      "weather_near_mae": weather_near["mae"],
                      "blend_near_mae": blend_near["mae"]})
        outputs.append(joined[["station", "time", "road_temp", "source_station",
                               "neighbor_source_time", "source_distance_km",
                               "neighbor_road_temp", "pred_weather_ridge", "pred_equal_blend"]])
        print(f"{target_id} <- {source_id} ({distances[source_id]:.1f} km): "
              f"neighbor MAE {source_score['mae']:.3f}, weather MAE {weather_score['mae']:.3f}",
              flush=True)
    metrics = pd.DataFrame(table)
    predictions = pd.concat(outputs, ignore_index=True)
    summary = {"status": "development_prior_same_route_rwis_benchmark",
               "smoke": args.smoke, "target_stations": len(metrics),
               "target_rows": len(predictions), "paired_rows": int(metrics.paired_rows.sum()),
               "source_age_limit_minutes": 30,
               "source_definition": "nearest other development RWIS on same route; road temperature strictly earlier than target",
               "comparison": "paired subset of existing outer-LOSO prior AWS/ASOS Ridge predictions",
               "bias_definition": "prediction minus observation",
               "neighbor_macro_mae": float(metrics.neighbor_mae.mean()),
               "equal_blend_macro_mae": float(metrics.blend_mae.mean()),
               "weather_macro_mae_on_paired": float(metrics.weather_mae.mean()),
               "neighbor_macro_rmse": float(metrics.neighbor_rmse.mean()),
               "equal_blend_macro_rmse": float(metrics.blend_rmse.mean()),
               "weather_macro_rmse_on_paired": float(metrics.weather_rmse.mean()),
               "neighbor_macro_near_mae": float(metrics.neighbor_near_mae.mean()),
               "equal_blend_macro_near_mae": float(metrics.blend_near_mae.mean()),
               "weather_macro_near_mae_on_paired": float(metrics.weather_near_mae.mean()),
               "stations_neighbor_better": int(metrics.neighbor_mae.lt(metrics.weather_mae).sum()),
               "stations_blend_better_than_neighbor": int(metrics.blend_mae.lt(metrics.neighbor_mae).sum()),
               "stations_blend_better_than_weather": int(metrics.blend_mae.lt(metrics.weather_mae).sum()),
               "source_distance_max_km": float(metrics.source_distance_km.max()),
               "note": "Operational same-route RWIS availability and latency are unverified; nonparametric reference benchmark, not a fitted spatial model."}
    out = PRIVATE / ("smoke_neighbor_rwis" if args.smoke else "neighbor_rwis")
    out.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(out / "station_metrics.csv", index=False, encoding="utf-8-sig")
    predictions.to_parquet(out / "predictions.parquet", index=False, compression="zstd")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
