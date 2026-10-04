"""Audit strictly prior three-hour AWS context for development Ice labels.

The 15-minute rain field is overlapping, so wet-observation counts and maximum
are reported; values are never summed into an hourly rain total.
"""
from __future__ import annotations

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
from src.weather_features import _load_aws, _numeric_range

PRIVATE = ROOT / "outputs" / "private"
HISTORY = ["air_min_3h", "humidity_max_3h", "dewpoint_gap_min_3h",
           "rain15_max_3h", "wet_observations_3h", "air_observations_3h"]


def source_history(aws: pd.DataFrame) -> pd.DataFrame:
    """Each output uses only the AWS observation at/before its source timestamp."""
    output = []
    for station, group in aws.groupby("station", sort=False):
        group = group.sort_values("source_time").copy()
        if group.source_time.duplicated().any():
            raise ValueError(f"AWS duplicate station/time: {station}")
        group["dewpoint_gap"] = group.air_temp - group.dewpoint
        group["wet_flag"] = group.rain_15m.gt(0).where(group.rain_15m.notna()).astype(float)
        index = group.set_index("source_time")
        window = index.rolling("3h", closed="both", min_periods=1)
        group["air_min_3h"] = window.air_temp.min().to_numpy()
        group["humidity_max_3h"] = window.humidity.max().to_numpy()
        group["dewpoint_gap_min_3h"] = window.dewpoint_gap.min().to_numpy()
        group["rain15_max_3h"] = window.rain_15m.max().to_numpy()
        group["wet_observations_3h"] = window.wet_flag.sum().to_numpy()
        group["air_observations_3h"] = window.air_temp.count().to_numpy()
        output.append(group[["station", "source_time", *HISTORY]])
    return pd.concat(output, ignore_index=True)


def summary_rates(data: pd.DataFrame) -> dict:
    defined = data.loc[data.ice.notna() & data.air_min_3h.notna()].copy()
    if defined.empty:
        return {"rows": 0}
    cool = defined.loc[defined.aws_air_temp.between(-5, 3)]
    return {
        "rows": len(defined), "ice_slots": int(defined.ice.sum()),
        "cool_rows": len(cool), "cool_ice_slots": int(cool.ice.sum()),
        "wet3h_rows": int(defined.wet_observations_3h.gt(0).sum()),
        "wet3h_ice_slots": int(defined.loc[defined.wet_observations_3h.gt(0), "ice"].sum()),
        "cool_wet3h_rows": int(cool.wet_observations_3h.gt(0).sum()),
        "cool_wet3h_ice_slots": int(cool.loc[cool.wet_observations_3h.gt(0), "ice"].sum()),
        "cool_dry3h_rows": int(cool.wet_observations_3h.eq(0).sum()),
        "cool_dry3h_ice_slots": int(cool.loc[cool.wet_observations_3h.eq(0), "ice"].sum()),
    }


def main() -> None:
    data = pd.read_parquet(PRIVATE / "ice_fallback_features" / "features.parquet")
    data["station"] = data.station.astype(str)
    assert_training_stations(data.station.unique())
    if set(data.station) & PROTECTED_STATIONS:
        raise AssertionError("Protected RWIS entered history audit")
    archive_path = competition_archive(ROOT)
    with zipfile.ZipFile(archive_path) as archive:
        aws = _load_aws(archive, limit_days=None)
    for col, low, high in (("air_temp", -60, 70), ("humidity", 0, 100),
                           ("rain_15m", 0, 500), ("dewpoint", -80, 60)):
        _numeric_range(aws, col, low, high)
    aws = aws.loc[aws.station.notna() & aws.source_time.notna()].copy()
    history = source_history(aws)
    data["aws_station"] = data.aws_station.astype("string")
    history["station"] = history.station.astype("string")
    merged = data.merge(history, how="left", left_on=["aws_station", "aws_source_time"],
                        right_on=["station", "source_time"], validate="many_to_one",
                        suffixes=("", "_source"))
    if len(merged) != len(data):
        raise AssertionError("History join changed target row count")
    valid = merged.aws_source_time.notna()
    if not (merged.loc[valid, "aws_source_time"] < merged.loc[valid, "time"]).all():
        raise AssertionError("Source weather not strictly earlier than RWIS target")
    if (merged.loc[valid, "station_source"].isna()).any():
        raise AssertionError("Selected AWS source time missing from history")
    audit = {"status": "development_prior_aws_3h_history_audit",
             "target_slots": len(merged), "valid_labels": int(merged.ice.notna().sum()),
             "ice_slots": int(merged.ice.eq(1).sum()),
             "positive_history_available": int(merged.loc[merged.ice.eq(1), "air_min_3h"].notna().sum()),
             "all_history_available": int(merged.air_min_3h.notna().sum()),
             "exposure": summary_rates(merged),
             "rain_semantics": "15-minute precipitation windows overlap; positive-observation counts are not rainfall amount",
             "source_semantics": "AWS source timestamps strictly precede target RWIS time; 3h rolling window ends at source time",
             "limitation": "Associations are descriptive, temporally autocorrelated and confounded by station/season; not a causal or final Ice score."}
    out = PRIVATE / "ice_weather_history"
    out.mkdir(parents=True, exist_ok=True)
    columns = ["station", "route", "time", "ice", "state_raw", "aws_station",
               "aws_source_time", "aws_air_temp", *HISTORY]
    merged[columns].to_parquet(out / "features.parquet", index=False, compression="zstd")
    (out / "summary.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
