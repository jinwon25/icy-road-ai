"""Time and station boundaries for development-only neighbor validation."""
from __future__ import annotations

import pandas as pd

from src.validation import assert_training_stations


def winter_station_split(data, held, train_period, valid_period):
    """Hold out the target station for both winters; fit only the first winter."""
    assert_training_stations(data.station.unique())
    time = pd.to_datetime(data.time)
    train = data.loc[data.station.ne(held) & time.between(
        pd.Timestamp(train_period[0]), pd.Timestamp(train_period[1]) + pd.Timedelta(hours=23, minutes=50))].copy()
    valid = data.loc[data.station.eq(held) & time.between(
        pd.Timestamp(valid_period[0]), pd.Timestamp(valid_period[1]) + pd.Timedelta(hours=23, minutes=50))].copy()
    if train.empty or valid.empty or train.time.max() >= valid.time.min():
        raise ValueError("Empty or overlapping winter split")
    return train, valid


def delayed_neighbor_join(target, source, delay_minutes, max_age_minutes=60):
    """Latest measurement available by t-delay, strictly before t, age <= cap.

    A fixed publication delay is a sensitivity assumption, not verified metadata.
    Exact availability-time matches are permitted for positive delays.
    """
    if delay_minutes < 0 or max_age_minutes <= 0:
        raise ValueError("Invalid publication delay or age cap")
    right = source[["time", "road_temp"]].dropna().rename(
        columns={"time": "neighbor_source_time", "road_temp": "neighbor_road_temp"})
    if right.neighbor_source_time.duplicated().any():
        raise ValueError("Duplicate source timestamps")
    right["available_time"] = right.neighbor_source_time + pd.Timedelta(minutes=delay_minutes)
    joined = pd.merge_asof(target.sort_values("time"), right.sort_values("available_time"),
                           left_on="time", right_on="available_time", direction="backward",
                           allow_exact_matches=delay_minutes > 0)
    age = (joined.time - joined.neighbor_source_time).dt.total_seconds() / 60
    invalid = ~age.between(0, max_age_minutes, inclusive="right")
    joined.loc[invalid, "neighbor_road_temp"] = float("nan")
    joined.loc[invalid, ["neighbor_source_time", "available_time"]] = pd.NaT
    joined["neighbor_age_minutes"] = age.where(~invalid)
    return joined
