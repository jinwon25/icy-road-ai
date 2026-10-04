"""Summarize label overlap and source availability for development Ice failures."""

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
    ice = pd.read_parquet(private / "ice_features" / "features.parquet",
                          columns=["station", "time", "ice", "aws_air_temp",
                                   "aws_humidity", "aws_rain_15m"])
    road = pd.read_parquet(private / "weather_features" / "features.parquet",
                           columns=["station", "time", "road_temp"])
    fallback = pd.read_parquet(private / "ice_fallback_features" / "features.parquet",
                               columns=["station", "time", "aws_air_temp"])
    for frame in (ice, road, fallback):
        frame["station"] = frame.station.astype(str)
        if set(frame.station) & PROTECTED_STATIONS:
            raise AssertionError("Protected RWIS entered Ice diagnostic")
    merged = ice.merge(road, on=["station", "time"], how="left",
                       validate="one_to_one").merge(
                           fallback, on=["station", "time"], how="left",
                           validate="one_to_one", suffixes=("_nearest", "_fallback"))
    positive = merged.loc[merged.ice.eq(1)]
    negative = merged.loc[merged.ice.eq(0)]
    summary = {
        "status": "development_ice_input_diagnostic_only",
        "target_slots": len(merged), "valid_labels": int(merged.ice.notna().sum()),
        "ice_slots": len(positive),
        "ice_with_road_temp": int(positive.road_temp.notna().sum()),
        "ice_road_temp_median_c": float(positive.road_temp.median()),
        "ice_road_temp_above_2c": int(positive.road_temp.gt(2).sum()),
        "nonice_road_temp_at_or_below_0c": int(negative.road_temp.le(0).sum()),
        "ice_nearest_aws_temp_available": int(positive.aws_air_temp_nearest.notna().sum()),
        "ice_fallback_aws_temp_available": int(positive.aws_air_temp_fallback.notna().sum()),
        "ice_nearest_aws_rain_15m_available": int(positive.aws_rain_15m.notna().sum()),
        "ice_nearest_aws_rain_15m_positive": int(positive.aws_rain_15m.gt(0).sum()),
        "ice_nearest_aws_humidity_at_least_90": int(positive.aws_humidity.ge(90).sum()),
        "limitations": "Road temperature is diagnostic truth, never an input to these direct classifiers; weather observations are strictly prior with actual publication latency unverified."
    }
    out = private / "ice_diagnostic"
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
