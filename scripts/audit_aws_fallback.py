"""Audit prior-only AWS fallback availability on development RWIS times.

This is a feature feasibility audit, not a fitted model or an Ice score.
No protected RWIS observations or road-temperature labels are read.
"""

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
from src.weather_features import _load_aws, haversine_km, prior_join


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="Use the existing two-day feature smoke sample")
    args = parser.parse_args()
    source_dir = ROOT / "outputs" / "private" / ("smoke" if args.smoke else "weather_features")
    features = pd.read_parquet(source_dir / "features.parquet",
                               columns=["station", "time", "aws_air_temp"])
    features["station"] = features.station.astype(str)
    assert_training_stations(features.station.unique())
    if set(features.station) & PROTECTED_STATIONS:
        raise AssertionError("Protected RWIS entered AWS fallback audit")
    if features.duplicated(["station", "time"]).any():
        raise ValueError("Duplicated development RWIS target time")

    inventory = pd.read_csv(ROOT / "outputs" / "private" / "full" / "station_inventory.csv",
                            dtype={"station_id": str})
    inventory = inventory.loc[inventory.kind.isin(["RWIS", "AWS"]),
                              ["kind", "station_id", "latitudes", "longitudes"]].copy()
    inventory["lat"] = pd.to_numeric(inventory.latitudes, errors="coerce")
    inventory["lon"] = pd.to_numeric(inventory.longitudes, errors="coerce")
    if inventory.duplicated(["kind", "station_id"]).any():
        raise ValueError("Station inventory contains duplicate IDs")
    coords = inventory.set_index(["kind", "station_id"])[["lat", "lon"]]

    archive = competition_archive(ROOT)
    with zipfile.ZipFile(archive) as zipped:
        aws = _load_aws(zipped, 2 if args.smoke else None)
    aws["station"] = aws.station.astype(str)
    aws["air_temp"] = pd.to_numeric(aws.air_temp, errors="coerce")
    aws = aws.loc[aws.air_temp.between(-60, 70), ["station", "source_time", "air_temp"]]
    if aws.duplicated(["station", "source_time"]).any():
        raise ValueError("Duplicate AWS source station/time after nominal-day filtering")
    by_aws = {station: part[["source_time", "air_temp"]]
              for station, part in aws.groupby("station")}

    rows = []
    selections = []
    for station, part in features.groupby("station", sort=True):
        lat, lon = coords.loc[("RWIS", station)]
        candidates = []
        for aws_station, source in by_aws.items():
            if ("AWS", aws_station) not in coords.index:
                continue
            aws_lat, aws_lon = coords.loc[("AWS", aws_station)]
            candidates.append((haversine_km(lat, lon, aws_lat, aws_lon), aws_station))
        nearest = sorted(candidates)[:3]
        if len(nearest) < 3:
            raise ValueError(f"Fewer than 3 AWS stations for {station}")
        target = part[["time"]].sort_values("time").reset_index(drop=True)
        original = part.sort_values("time").aws_air_temp.notna().reset_index(drop=True)
        candidates_valid = []
        for rank, (distance, aws_station) in enumerate(nearest, start=1):
            # A valid prior reading may be older than a later missing AWS row.
            joined = prior_join(target, by_aws[aws_station], f"aws{rank}")
            valid = joined[f"aws{rank}_air_temp"].notna().to_numpy()
            age = joined[f"aws{rank}_age_minutes"].to_numpy()
            candidates_valid.append(valid)
            rows.append({"rwis_station": station, "aws_rank": rank,
                         "aws_station": aws_station, "distance_km": distance,
                         "target_times": len(target), "valid_prior_times": int(valid.sum()),
                         "median_age_minutes_when_valid": float(np.median(age[valid]))
                         if valid.any() else None})
        nearest_valid, second_valid, third_valid = candidates_valid
        any_three = nearest_valid | second_valid | third_valid
        fallback_only = ~nearest_valid & (second_valid | third_valid)
        selections.append({"rwis_station": station, "target_times": len(target),
                           "existing_nearest_aws_times": int(original.sum()),
                           "top1_last_valid_times": int(nearest_valid.sum()),
                           "top3_any_valid_times": int(any_three.sum()),
                           "top1_history_rescue_times": int((~original & nearest_valid).sum()),
                           "other_aws_rescue_times": int(fallback_only.sum()),
                           "still_missing_times": int((~any_three).sum())})
        if (original & ~nearest_valid).any():
            raise AssertionError("Valid existing nearest AWS missing from last-valid audit")

    station_table = pd.DataFrame(selections)
    rank_table = pd.DataFrame(rows)
    totals = station_table.drop(columns="rwis_station").sum().astype(int).to_dict()
    summary = {"status": "development_feature_availability_only",
               "scope": "14 development RWIS target times; no road-temperature labels used",
               "timing": "strictly prior valid AWS air temperature, maximum age 60 minutes; actual publication latency unverified",
               "station_count": len(station_table), "totals": totals,
               "station_12209": station_table.loc[
                   station_table.rwis_station.eq("12209")].iloc[0].to_dict()}
    out = ROOT / "outputs" / "private" / ("smoke_aws_fallback" if args.smoke else "aws_fallback")
    out.mkdir(parents=True, exist_ok=True)
    station_table.to_csv(out / "station_coverage.csv", index=False, encoding="utf-8-sig")
    rank_table.to_csv(out / "nearest_aws.csv", index=False, encoding="utf-8-sig")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(out), **summary}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
