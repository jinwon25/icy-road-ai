"""Replace nearest AWS inputs with the nearest available prior AWS among three."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive
from src.validation import PROTECTED_STATIONS, assert_training_stations
from src.weather_features import _load_aws, _numeric_range, haversine_km, prior_join

VARIABLES = ["air_temp", "humidity", "wind_speed", "rain_15m", "dewpoint"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--target", choices=("road_temp", "ice"), default="road_temp")
    args = parser.parse_args()
    private = ROOT / "outputs" / "private"
    if args.target == "ice":
        input_name = "smoke_ice_features" if args.smoke else "ice_features"
        output_name = "smoke_ice_fallback_features" if args.smoke else "ice_fallback_features"
    else:
        input_name = "smoke" if args.smoke else "weather_features"
        output_name = "smoke_aws_fallback_features" if args.smoke else "aws_fallback_features"
    in_dir = private / input_name
    features = pd.read_parquet(in_dir / "features.parquet")
    features["station"] = features.station.astype(str)
    assert_training_stations(features.station.unique())
    if set(features.station) & PROTECTED_STATIONS:
        raise AssertionError("Protected RWIS entered fallback features")
    if features.duplicated(["station", "time"]).any():
        raise ValueError("Duplicate target station/time")

    inventory = pd.read_csv(private / "full" / "station_inventory.csv",
                            dtype={"station_id": str})
    inventory = inventory.loc[inventory.kind.isin(["RWIS", "AWS"]),
                              ["kind", "station_id", "latitudes", "longitudes"]].copy()
    inventory["lat"] = pd.to_numeric(inventory.latitudes, errors="coerce")
    inventory["lon"] = pd.to_numeric(inventory.longitudes, errors="coerce")
    coords = inventory.set_index(["kind", "station_id"])[["lat", "lon"]]
    if coords.index.has_duplicates:
        raise ValueError("Duplicate station coordinate key")

    with zipfile.ZipFile(competition_archive(ROOT)) as archive:
        aws = _load_aws(archive, 2 if args.smoke else None)
    aws["station"] = aws.station.astype(str)
    for column, lower, upper in (("air_temp", -60, 70), ("humidity", 0, 100),
                                 ("wind_speed", 0, 75), ("rain_15m", 0, 500),
                                 ("dewpoint", -80, 60)):
        _numeric_range(aws, column, lower, upper)
    # A fallback station is selected only when it has a usable air temperature.
    aws = aws.loc[aws.air_temp.notna(), ["station", "source_time", *VARIABLES]]
    if aws.duplicated(["station", "source_time"]).any():
        raise ValueError("Duplicate valid AWS station/time")
    by_aws = {station: part.drop(columns="station") for station, part in aws.groupby("station")}

    parts = []
    for station, original in features.groupby("station", sort=True):
        target = original.sort_values("time").reset_index(drop=True).copy()
        lat, lon = coords.loc[("RWIS", station)]
        nearest = sorted((haversine_km(lat, lon, *coords.loc[("AWS", source_id)]), source_id)
                         for source_id in by_aws)[:3]
        if len(nearest) < 3:
            raise ValueError(f"Fewer than 3 AWS candidates for {station}")
        for variable in VARIABLES:
            target[f"aws_{variable}"] = np.nan
        target["aws_age_minutes"] = np.nan
        target["aws_distance_km"] = np.nan
        target["aws_source_time"] = pd.NaT
        target["aws_station"] = pd.NA
        target["aws_rank"] = pd.array([pd.NA] * len(target), dtype="Int64")
        for rank, (distance, source_id) in enumerate(nearest, start=1):
            joined = prior_join(target[["time"]], by_aws[source_id], f"candidate{rank}")
            pick = target.aws_rank.isna() & joined[f"candidate{rank}_air_temp"].notna()
            if not pick.any():
                continue
            for variable in VARIABLES:
                target.loc[pick, f"aws_{variable}"] = joined.loc[
                    pick, f"candidate{rank}_{variable}"].to_numpy()
            target.loc[pick, "aws_source_time"] = joined.loc[
                pick, f"candidate{rank}_source_time"].to_numpy()
            target.loc[pick, "aws_age_minutes"] = joined.loc[
                pick, f"candidate{rank}_age_minutes"].to_numpy()
            target.loc[pick, "aws_distance_km"] = distance
            target.loc[pick, "aws_station"] = source_id
            target.loc[pick, "aws_rank"] = rank
        parts.append(target)
    output = pd.concat(parts, ignore_index=True)
    available = int(output.aws_air_temp.notna().sum())
    if len(output) != len(features):
        raise AssertionError("Fallback changed the target row count")
    if args.target == "road_temp":
        expected = json.loads((private / ("smoke_aws_fallback" if args.smoke else "aws_fallback") /
                               "summary.json").read_text(encoding="utf-8"))["totals"]["top3_any_valid_times"]
        if available != expected:
            raise AssertionError(f"Fallback coverage mismatch: {available} vs {expected}")
    valid = output.aws_source_time.notna()
    if not (output.loc[valid, "aws_source_time"] < output.loc[valid, "time"]).all():
        raise AssertionError("Current or future AWS input")
    if not output.loc[valid, "aws_age_minutes"].between(0, 60, inclusive="right").all():
        raise AssertionError("AWS age exceeds 60 minutes")
    out = private / output_name
    out.mkdir(parents=True, exist_ok=True)
    output.to_parquet(out / "features.parquet", index=False, compression="zstd")
    summary = {"status": "development_prior_only_fallback_features",
               "target": args.target,
               "targets": len(output), "aws_temp_pairs": available,
               "aws_rank_counts": {str(rank): int(count) for rank, count in
                                   output.aws_rank.value_counts().items()},
               "source_rule": "nearest of three AWS with valid air temperature strictly prior within 60 minutes",
               "publication_latency": "unverified"}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(json.dumps({"output": str(out), **summary}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
