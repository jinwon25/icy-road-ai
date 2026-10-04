"""Prior-only weather inputs for every development RWIS road-state time."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

from src.validation import (PROTECTED_STATIONS, assert_training_stations,
                            canonical_station_id, normalize_state)
from src.weather_features import (_load_aws, _load_daily, _nearest,
                                  _numeric_range, prior_join)


def build_ice_features(archive_path: Path, limit_days: int | None = None) -> pd.DataFrame:
    with zipfile.ZipFile(archive_path) as archive:
        rwis = _load_daily(archive, "RWIS", [0, 1, 3, 4, 5, 6],
                           ["time", "station", "route", "lat", "lon", "state_raw"],
                           limit_days)
        asos = _load_daily(archive, "ASOS", [1, 2, 4, 5, 6],
                           ["source_time", "station", "lat", "lon", "air_temp"],
                           limit_days)
        aws = _load_aws(archive, limit_days)
    rwis["station"] = rwis.station.map(canonical_station_id)
    rwis = rwis.loc[~rwis.station.isin(PROTECTED_STATIONS)
                    & rwis.station.ne("<missing>")].copy()
    assert_training_stations(rwis.station.unique())
    rwis["ice"] = rwis.state_raw.map(normalize_state)
    asos["station"] = asos.station.map(canonical_station_id)
    for frame, time_name in ((rwis, "time"), (asos, "source_time"), (aws, "source_time")):
        frame[time_name] = pd.to_datetime(frame[time_name], errors="coerce")
        for column in ("lat", "lon"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    rwis = rwis.loc[rwis.time.notna()].copy()
    if rwis.duplicated(["station", "time"]).any():
        raise ValueError("Duplicate development RWIS station/time")
    _numeric_range(asos, "air_temp", -60, 70)
    for column, lower, upper in (("air_temp", -60, 70), ("humidity", 0, 100),
                                 ("wind_speed", 0, 75), ("rain_15m", 0, 500),
                                 ("dewpoint", -80, 60)):
        _numeric_range(aws, column, lower, upper)
    rwis_coords = rwis.groupby("station")[["lat", "lon"]].first().dropna()
    asos_coords = asos.groupby("station")[["lat", "lon"]].first().dropna()
    aws_coords = aws.groupby("station")[["lat", "lon"]].first().dropna()
    if len(rwis_coords) != rwis.station.nunique():
        raise ValueError("Development RWIS coordinate missing")
    frames = []
    for station, coords in rwis_coords.iterrows():
        aws_station, aws_distance = _nearest(coords.lat, coords.lon, aws_coords)
        asos_station, asos_distance = _nearest(coords.lat, coords.lon, asos_coords)
        target = rwis.loc[rwis.station.eq(station),
                          ["station", "route", "time", "ice", "state_raw"]]
        weather = aws.loc[aws.station.eq(aws_station),
                          ["source_time", "air_temp", "humidity", "wind_speed",
                           "rain_15m", "dewpoint"]]
        joined = prior_join(target, weather, "aws")
        synoptic = asos.loc[asos.station.eq(asos_station),
                            ["source_time", "air_temp"]]
        joined = prior_join(joined, synoptic, "asos")
        joined["aws_station"] = aws_station
        joined["asos_station"] = asos_station
        joined["aws_distance_km"] = aws_distance
        joined["asos_distance_km"] = asos_distance
        frames.append(joined)
    return pd.concat(frames, ignore_index=True)
