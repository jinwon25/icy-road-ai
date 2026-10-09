"""Build prior-only ASOS/AWS inputs for development RWIS stations."""

from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.validation import PROTECTED_STATIONS, assert_training_stations, canonical_station_id
from src.weather_inputs import filter_aws_nominal_day
from src.observation_io import daily_members, read_columns, numeric_observations


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a, b, c, d = np.radians([lat1, lon1, lat2, lon2])
    h = np.sin((c - a) / 2) ** 2 + np.cos(a) * np.cos(c) * np.sin((d - b) / 2) ** 2
    return float(6371.0088 * 2 * np.arcsin(np.sqrt(h)))


def prior_join(target: pd.DataFrame, source: pd.DataFrame, prefix: str,
               tolerance_minutes: int = 60) -> pd.DataFrame:
    """Join the latest strictly earlier observation, with an explicit age limit."""
    left = target.sort_values("time").copy()
    right = source.sort_values("source_time").copy()
    right = right.rename(columns={column: f"{prefix}_{column}" for column in right
                                  if column != "source_time"})
    right = right.rename(columns={"source_time": f"{prefix}_source_time"})
    joined = pd.merge_asof(
        left, right, left_on="time", right_on=f"{prefix}_source_time",
        direction="backward", allow_exact_matches=False,
        tolerance=pd.Timedelta(minutes=tolerance_minutes),
    )
    source_time = joined[f"{prefix}_source_time"]
    joined[f"{prefix}_age_minutes"] = (joined["time"] - source_time).dt.total_seconds() / 60
    valid = source_time.notna()
    if valid.any():
        assert (source_time[valid] < joined.loc[valid, "time"]).all()
        assert joined.loc[valid, f"{prefix}_age_minutes"].between(
            0, tolerance_minutes, inclusive="right").all()
    return joined


def _load_daily(archive: zipfile.ZipFile, kind: str, columns: list[str],
                new_names: list[str], limit_days: int | None) -> pd.DataFrame:
    names = daily_members(archive, kind)
    if limit_days:
        names = names[:limit_days]
    frames = []
    for name in names:
        frame = read_columns(archive, name, columns, new_names)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _load_aws(archive: zipfile.ZipFile, limit_days: int | None) -> pd.DataFrame:
    names = daily_members(archive, "AWS")
    if limit_days:
        names = names[:limit_days]
    frames = []
    for name in names:
        match = re.search(r"AWS_daily_(\d{8})", name, re.IGNORECASE)
        if not match:
            raise ValueError(f"Missing AWS date token: {name}")
        day = datetime.strptime(match.group(1), "%Y%m%d").date()
        with archive.open(name) as stream:
            raw = pd.read_csv(stream, dtype=str, encoding="utf-8-sig", keep_default_na=False)
        clean, _ = filter_aws_nominal_day(raw, day)
        names_by_position = list(raw.columns)
        chosen = clean[["source_time_kst", "station_id", *[names_by_position[i] for i in
                                                               (3, 4, 10, 11, 13, 17, 20)]]].copy()
        chosen.columns = ["source_time", "station", "lat", "lon", "wind_speed",
                          "air_temp", "rain_15m", "humidity", "dewpoint"]
        chosen["source_time"] = chosen["source_time"].dt.tz_localize(None)
        frames.append(chosen)
    return pd.concat(frames, ignore_index=True)


def _numeric_range(frame: pd.DataFrame, column: str, lower: float, upper: float) -> None:
    number = numeric_observations(frame[column])
    frame[column] = number.where(number.between(lower, upper))


def _nearest(target_lat: float, target_lon: float, coordinates: pd.DataFrame) -> tuple[str, float]:
    candidates = ((haversine_km(target_lat, target_lon, row.lat, row.lon), station)
                  for station, row in coordinates.iterrows())
    distance, station = min(candidates)
    return str(station), float(distance)


def build_features(archive_path: Path, limit_days: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    with zipfile.ZipFile(archive_path) as archive:
        rwis = _load_daily(archive, "RWIS", ["관측시각 (KST)", "관측 지점번호", "고속도로", "관측소 위도", "관측소 경도", "노면온도 (광학)"],
                           ["time", "station", "route", "lat", "lon", "road_temp"], limit_days)
        asos = _load_daily(archive, "ASOS", ["시간", "지점", "위도", "경도", "기온(°C)"],
                           ["source_time", "station", "lat", "lon", "air_temp"], limit_days)
        aws = _load_aws(archive, limit_days)
    rwis["station"] = rwis.station.map(canonical_station_id)
    rwis = rwis.loc[~rwis.station.isin(PROTECTED_STATIONS) & rwis.station.ne("<missing>")].copy()
    assert_training_stations(rwis.station.unique())
    asos["station"] = asos.station.map(canonical_station_id)
    for frame, time_name in ((rwis, "time"), (asos, "source_time"), (aws, "source_time")):
        frame[time_name] = pd.to_datetime(frame[time_name], errors="coerce")
        for column in ("lat", "lon"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    _numeric_range(rwis, "road_temp", -60, 70)
    rwis = rwis.loc[rwis.road_temp.notna() & rwis.time.notna()].copy()
    _numeric_range(asos, "air_temp", -60, 70)
    for column, lower, upper in (("air_temp", -60, 70), ("humidity", 0, 100),
                                 ("wind_speed", 0, 75), ("rain_15m", 0, 500),
                                 ("dewpoint", -80, 60)):
        _numeric_range(aws, column, lower, upper)
    rwis_coords = rwis.groupby("station")[["lat", "lon"]].first().dropna()
    asos_coords = asos.groupby("station")[["lat", "lon"]].first().dropna()
    aws_coords = aws.groupby("station")[["lat", "lon"]].first().dropna()
    if len(rwis_coords) != rwis.station.nunique():
        raise ValueError("A development RWIS station has no coordinates")
    frames = []
    mapping = []
    for station, coords in rwis_coords.iterrows():
        aws_station, aws_distance = _nearest(coords.lat, coords.lon, aws_coords)
        asos_station, asos_distance = _nearest(coords.lat, coords.lon, asos_coords)
        target = rwis.loc[rwis.station.eq(station), ["station", "route", "time", "road_temp"]]
        weather = aws.loc[aws.station.eq(aws_station),
                          ["source_time", "air_temp", "humidity", "wind_speed", "rain_15m", "dewpoint"]]
        weather = prior_join(target, weather, "aws")
        synoptic = asos.loc[asos.station.eq(asos_station), ["source_time", "air_temp"]]
        weather = prior_join(weather, synoptic, "asos")
        weather["aws_station"] = aws_station
        weather["asos_station"] = asos_station
        weather["aws_distance_km"] = aws_distance
        weather["asos_distance_km"] = asos_distance
        frames.append(weather)
        mapping.append({"station": station, "aws_station": aws_station,
                        "aws_distance_km": aws_distance, "asos_station": asos_station,
                        "asos_distance_km": asos_distance})
    features = pd.concat(frames, ignore_index=True)
    return features, pd.DataFrame(mapping)
