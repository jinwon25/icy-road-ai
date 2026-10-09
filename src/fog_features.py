"""목표안개 관측소의 시정을 같은 노선의 개발 타깃에 과거 시각으로 결합한다."""
from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from src.observation_io import daily_members, read_columns, numeric_observations
from src.validation import canonical_station_id, assert_training_stations
from src.weather_features import haversine_km

FOG_FEATURES = ["fog_log_visibility_m", "fog_age_minutes", "fog_distance_km"]


def load_fog(archive_path: Path) -> pd.DataFrame:
    columns = ["관측시각 (KST)", "관측 지점번호", "고속도로", "관측소 위도",
               "관측소 경도", "관측소 고도 (m)", "시정 (m)"]
    names = ["source_time", "station", "route", "lat", "lon", "elevation_m", "visibility_m"]
    with zipfile.ZipFile(archive_path) as archive:
        parts = [read_columns(archive, name, columns, names)
                 for name in daily_members(archive, "FOG")]
    result = pd.concat(parts, ignore_index=True)
    result["station"] = result.station.map(canonical_station_id)
    assert_training_stations(result.station.unique())
    if result.station.eq("<missing>").any():
        raise ValueError("Fog station ID missing")
    result["route"] = result.route.str.strip()
    result["source_time"] = pd.to_datetime(result.source_time, errors="raise")
    for field in ["lat", "lon", "elevation_m", "visibility_m"]:
        result[field] = numeric_observations(result[field])
    if not result.lat.between(-90, 90).all() or not result.lon.between(-180, 180).all():
        raise ValueError("Missing or invalid fog coordinates")
    result["visibility_m"] = result.visibility_m.where(result.visibility_m.ge(0))
    if result.duplicated(["station", "source_time"]).any():
        raise ValueError("Duplicate fog station/time")
    for _, part in result.groupby("station"):
        if part[["route", "lat", "lon", "elevation_m"]].nunique(dropna=False).ne(1).any():
            raise ValueError("Fog metadata changes across observations")
    return result


def attach_fog(target: pd.DataFrame, metadata: pd.DataFrame, fog: pd.DataFrame,
               max_age_minutes: int = 30, delay_minutes: int = 0) -> pd.DataFrame:
    """지연은 가정이다. 동시각·미래·타 노선 입력은 금지하고 미관측 행도 보존한다."""
    if max_age_minutes <= 0 or delay_minutes < 0 or delay_minutes > max_age_minutes:
        raise ValueError("Require 0 <= delay <= positive maximum age")
    target = target.copy()
    target["station"] = target.station.map(canonical_station_id)
    target["time"] = pd.to_datetime(target.time, errors="raise")
    assert_training_stations(target.station.unique())
    assert_training_stations(fog.station.unique())
    if target.duplicated(["station", "time"]).any():
        raise ValueError("Duplicate target station/time")
    if set(target.station) & set(fog.station):
        raise ValueError("Fog source cannot also be a target")
    if metadata.station.duplicated().any():
        raise ValueError("Duplicate target metadata")
    meta = metadata.set_index("station")
    sources = fog.groupby("station")[["route", "lat", "lon"]].first()
    frames = []
    target["_fog_order"] = np.arange(len(target))
    for station, part in target.groupby("station", sort=False):
        point = meta.loc[station]
        route = str(point.route).strip()
        if not part.route.str.strip().eq(route).all():
            raise ValueError("Cached route and station metadata disagree")
        candidates = sources.loc[sources.route.str.strip().eq(route)]
        part = part.copy()
        if candidates.empty:
            part["fog_station"] = None
            part["fog_source_time"] = pd.NaT
            for field in ["fog_visibility_m", "fog_distance_km", "fog_age_minutes"]:
                part[field] = np.nan
        else:
            distances = {sid: haversine_km(point.lat, point.lon, row.lat, row.lon)
                         for sid, row in candidates.iterrows()}
            selected = min(distances, key=lambda sid: (distances[sid], sid))
            right = fog.loc[fog.station.eq(selected) & fog.visibility_m.notna(),
                            ["source_time", "visibility_m"]].rename(
                                columns={"source_time": "fog_source_time",
                                         "visibility_m": "fog_visibility_m"})
            right["_available_time"] = right.fog_source_time + pd.Timedelta(minutes=delay_minutes)
            part = pd.merge_asof(part.sort_values("time"), right.sort_values("_available_time"),
                                 left_on="time", right_on="_available_time", direction="backward",
                                 allow_exact_matches=delay_minutes > 0,
                                 tolerance=pd.Timedelta(minutes=max_age_minutes - delay_minutes))
            part = part.drop(columns="_available_time")
            part["fog_station"] = selected
            part["fog_distance_km"] = distances[selected]
            part["fog_age_minutes"] = (part.time - part.fog_source_time).dt.total_seconds() / 60
        frames.append(part)
    result = pd.concat(frames, ignore_index=True).sort_values("_fog_order").drop(columns="_fog_order").reset_index(drop=True)
    available = result.fog_source_time.notna()
    if not result.loc[available, "fog_age_minutes"].between(0, max_age_minutes, inclusive="right").all():
        raise AssertionError("Nonprior or stale fog source")
    if not result.loc[available, "fog_age_minutes"].ge(delay_minutes).all():
        raise AssertionError("Publication-delay assumption violated")
    result["fog_log_visibility_m"] = np.log1p(result.fog_visibility_m)
    return result
