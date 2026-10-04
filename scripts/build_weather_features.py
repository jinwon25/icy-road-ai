"""Build private, prior-only weather features for development RWIS road temperature."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive
from src.validation import PROTECTED_STATIONS
from src.weather_features import build_features


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-days", type=int, default=None)
    args = parser.parse_args()
    archive = competition_archive(ROOT)
    features, mapping = build_features(archive, args.limit_days)
    if set(features.station) & PROTECTED_STATIONS:
        raise AssertionError("Protected RWIS entered development features")
    for prefix in ("aws", "asos"):
        source = features[f"{prefix}_source_time"]
        valid = source.notna()
        if not (source[valid] < features.loc[valid, "time"]).all():
            raise AssertionError(f"{prefix} includes current or future observation")
    rows = []
    for station, part in features.groupby("station"):
        m = mapping.loc[mapping.station.eq(station)].iloc[0]
        rows.append({"station": station, "targets": len(part),
                     "aws_temp_pairs": int(part.aws_air_temp.notna().sum()),
                     "asos_temp_pairs": int(part.asos_air_temp.notna().sum()),
                     "both_temp_pairs": int((part.aws_air_temp.notna() & part.asos_air_temp.notna()).sum()),
                     "aws_station": m.aws_station, "aws_distance_km": m.aws_distance_km,
                     "asos_station": m.asos_station, "asos_distance_km": m.asos_distance_km})
    station_table = pd.DataFrame(rows)
    report = {
        "status": "development_features_only",
        "input_assumptions": {
            "rwis_aws_timezone": "KST from source headers",
            "asos_timezone": "KST provisional; source column lacks timezone",
            "availability": "source timestamp strictly earlier than target, at most 60 minutes old; publication latency unverified",
            "precipitation": "AWS trailing 15-minute amount, not daily cumulative"
        },
        "days_per_winter": args.limit_days,
        "stations": len(station_table),
        "targets": len(features),
        "aws_temp_pairs": int(features.aws_air_temp.notna().sum()),
        "asos_temp_pairs": int(features.asos_air_temp.notna().sum()),
        "both_temp_pairs": int((features.aws_air_temp.notna() & features.asos_air_temp.notna()).sum()),
        "aws_distance_km_range": [float(station_table.aws_distance_km.min()),
                                   float(station_table.aws_distance_km.max())],
        "asos_distance_km_range": [float(station_table.asos_distance_km.min()),
                                    float(station_table.asos_distance_km.max())],
    }
    out = ROOT / "outputs" / "private" / ("smoke" if args.limit_days else "weather_features")
    out.mkdir(parents=True, exist_ok=True)
    features.to_parquet(out / "features.parquet", index=False, compression="zstd")
    station_table.to_csv(out / "station_coverage.csv", index=False, encoding="utf-8-sig")
    (out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(out), "targets": report["targets"],
                      "aws_temp_pairs": report["aws_temp_pairs"],
                      "asos_temp_pairs": report["asos_temp_pairs"],
                      "both_temp_pairs": report["both_temp_pairs"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
