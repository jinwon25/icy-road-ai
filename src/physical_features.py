"""도로 냉각·수분 입력. 대상 지점과 모든 검증 지점을 주변 참조에서 제외한다."""
from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from src.observation_io import daily_members, read_columns
from src.validation import PROTECTED_STATIONS, canonical_station_id, assert_training_stations
from src.weather_features import _numeric_range, prior_join, haversine_km

CONTEXT_FEATURES = ["near_road_temp", "near_temp_min60", "near_temp_trend60",
                    "near_distance_km", "near_age_minutes", "moisture_humidity",
                    "moisture_rain10", "moisture_distance_km", "moisture_age_minutes",
                    "surface_dewpoint_gap", "surface_air_gap"]


def load_thermal_sources(path: Path) -> pd.DataFrame:
    columns = ["관측시각 (KST)", "관측 지점번호", "고속도로", "노면온도 (광학)",
               "습도 (%)", "일 누적 강수량 (mm)"]
    names = ["time", "station", "route", "road_temp", "humidity", "rain_cum"]
    chunks = []
    with zipfile.ZipFile(path) as archive:
        for member in daily_members(archive, "RWIS"):
            part = read_columns(archive, member, columns, names)
            part["station"] = part.station.map(canonical_station_id)
            part = part.loc[~part.station.isin(PROTECTED_STATIONS) & part.station.ne("<missing>")]
            chunks.append(part)
    frame = pd.concat(chunks, ignore_index=True)
    assert_training_stations(frame.station.unique())
    frame["time"] = pd.to_datetime(frame.time, errors="raise")
    frame["route"] = frame.route.str.strip()
    for column, low, high in [("road_temp", -60, 70), ("humidity", 0, 100), ("rain_cum", 0, 2000)]:
        _numeric_range(frame, column, low, high)
    return source_history(frame)


def source_history(source: pd.DataFrame) -> pd.DataFrame:
    assert_training_stations(source.station.unique())
    parts = []
    for _, part in source.groupby("station"):
        part = part.sort_values("time").copy()
        if part.time.duplicated().any():
            raise ValueError("Duplicate thermal source timestamp")
        indexed = part.set_index("time")
        part["temp_min60"] = indexed.road_temp.rolling("60min", closed="both", min_periods=1).min().to_numpy()
        previous = (part.time - pd.Timedelta(hours=1)).map(indexed.road_temp)
        part["temp_trend60"] = part.road_temp.to_numpy() - previous.to_numpy()
        contiguous = part.time.diff().eq(pd.Timedelta(minutes=10))
        same_day = part.time.dt.normalize().eq(part.time.shift().dt.normalize())
        delta = part.rain_cum.diff()
        part["rain10"] = delta.where(contiguous & same_day & delta.ge(0))
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


class ThermalContext:
    def __init__(self, targets: pd.DataFrame, source: pd.DataFrame, metadata: pd.DataFrame):
        assert_training_stations(targets.station.unique())
        assert_training_stations(source.station.unique())
        self.targets = targets[["station", "time"]].copy().reset_index(drop=True)
        self.targets["time"] = pd.to_datetime(self.targets.time).astype("datetime64[ns]")
        if self.targets.duplicated().any():
            raise ValueError("Duplicate target")
        self.source = source.copy()
        self.source["time"] = pd.to_datetime(self.source.time).astype("datetime64[ns]")
        self.metadata = metadata.set_index("station").copy()
        self.metadata["route"] = self.metadata.route.str.strip()
        assert_training_stations(self.metadata.index)
        counts = source.groupby("station").humidity.count()
        self.metadata["has_moisture"] = self.metadata.index.map(counts).fillna(0) > 0
        self.cache = {}

    def reference(self, target, forbidden, moisture=False):
        forbidden = set(forbidden) | {target} | PROTECTED_STATIONS
        point = self.metadata.loc[target]
        pool = self.metadata.loc[self.metadata.route.eq(point.route) & ~self.metadata.index.isin(forbidden)]
        if moisture:
            pool = pool.loc[pool.has_moisture]
        if pool.empty:
            return None, np.nan
        distances = {sid: haversine_km(point.lat, point.lon, row.lat, row.lon)
                     for sid, row in pool.iterrows()}
        sid = min(distances, key=lambda key: (distances[key], key))
        return sid, distances[sid]

    def pair(self, station, reference):
        if station == reference:
            raise ValueError("Self reference forbidden")
        key = (station, reference)
        if key not in self.cache:
            target = self.targets.loc[self.targets.station.eq(station)].copy()
            source = self.source.loc[self.source.station.eq(reference),
                                     ["time", "road_temp", "temp_min60", "temp_trend60", "humidity", "rain10"]]
            joined = prior_join(target, source.rename(columns={"time": "source_time"}), "ctx", 30)
            self.cache[key] = joined.set_index("time")
        return self.cache[key]

    def features(self, frame: pd.DataFrame, forbidden: set[str]):
        """같은 분할 전체에서 금지된 참조를 차단하고 학습 타깃도 자기 이력을 못 쓴다."""
        assert_training_stations(frame.station.unique())
        rows, manifest = [], []
        for station, part in frame.groupby("station", sort=False):
            result = pd.DataFrame(index=part.index)
            for moisture, prefix, mapping in [
                (False, "near", {"road_temp": "road_temp", "temp_min60": "temp_min60", "temp_trend60": "temp_trend60"}),
                (True, "moisture", {"humidity": "humidity", "rain10": "rain10"})]:
                sid, distance = self.reference(station, forbidden, moisture)
                if sid in set(forbidden) | {station}:
                    raise AssertionError("Excluded source selected")
                result[f"{prefix}_distance_km"] = distance
                if sid is None:
                    for destination in mapping.values():
                        result[f"{prefix}_{destination}"] = np.nan
                    result[f"{prefix}_age_minutes"] = np.nan
                else:
                    source = self.pair(station, sid)
                    for original, destination in mapping.items():
                        result[f"{prefix}_{destination}"] = part.time.map(source[f"ctx_{original}"])
                    result[f"{prefix}_age_minutes"] = part.time.map(source.ctx_age_minutes)
                manifest.append({"target": station, "kind": prefix, "source": sid,
                                 "distance_km": distance, "forbidden": sorted(forbidden)})
            result["surface_dewpoint_gap"] = result.near_road_temp - part.aws_dewpoint
            result["surface_air_gap"] = result.near_road_temp - part.aws_air_temp
            rows.append(result)
        result = pd.concat(rows).reindex(frame.index)
        return result[CONTEXT_FEATURES], manifest
