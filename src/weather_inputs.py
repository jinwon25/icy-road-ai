"""Source-preserving filters for daily weather input files."""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.validation import canonical_station_id


def filter_aws_nominal_day(frame: pd.DataFrame, nominal_day: date) -> tuple[pd.DataFrame, dict[str, int]]:
    """Keep AWS rows on their source-file KST date; do not impute readings.

    The source ZIP stores the next day's 00:00 row in both adjacent files.
    Boundary equality was checked separately in ``audit_aws_boundaries.py``.
    Original columns and string values remain in the returned copy.
    """
    if frame.shape[1] != 21:
        raise ValueError(f"Expected 21 AWS columns, got {frame.shape[1]}")
    time = pd.to_datetime(frame.iloc[:, 0], errors="coerce", format="mixed")
    station = frame.iloc[:, 1].map(canonical_station_id)
    missing_station = station.eq("<missing>")
    same_day = time.dt.date.eq(nominal_day)
    valid = ~missing_station & same_day & time.notna()
    cleaned = frame.loc[valid].copy()
    cleaned.insert(0, "source_time_kst", time.loc[valid].dt.tz_localize("Asia/Seoul"))
    cleaned.insert(1, "station_id", station.loc[valid])
    duplicated = cleaned.duplicated(["station_id", "source_time_kst"], keep=False)
    duplicate_count = int(duplicated.sum())
    if duplicate_count:
        raise ValueError(f"Duplicate AWS station/time rows within nominal date: {duplicate_count}")
    counts = {
        "input_rows": len(frame),
        "missing_station_rows": int(missing_station.sum()),
        "invalid_timestamp_rows": int(time.isna().sum()),
        "valid_station_invalid_timestamp": int((~missing_station & time.isna()).sum()),
        "valid_station_outside_nominal_day": int((~missing_station & time.notna() & ~same_day).sum()),
        "retained_rows": len(cleaned),
        "duplicate_station_time_rows": duplicate_count,
    }
    if counts["input_rows"] != (counts["missing_station_rows"]
                                + counts["valid_station_invalid_timestamp"]
                                + counts["valid_station_outside_nominal_day"]
                                + counts["retained_rows"]):
        raise AssertionError("AWS row categories do not partition the source file")
    return cleaned, counts
