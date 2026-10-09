"""NOAA 태양 위치 근사식과 Copernicus DSM의 지형 차폐 후보 특성."""
from __future__ import annotations

import numpy as np
import pandas as pd
from pyproj import Geod


def solar_position(times, lat, lon):
    """KST 시각을 입력받는다. 대기 굴절을 보정하지 않은 고도·북쪽 기준 방위각."""
    t = pd.DatetimeIndex(times)
    if t.tz is not None:
        t = t.tz_convert("Asia/Seoul").tz_localize(None)
    hour = t.hour.to_numpy() + t.minute.to_numpy() / 60 + t.second.to_numpy() / 3600
    gamma = 2 * np.pi / np.where(t.is_leap_year, 366, 365) * (t.dayofyear.to_numpy() - 1 + (hour - 12) / 24)
    eq = 229.18 * (.000075 + .001868 * np.cos(gamma) - .032077 * np.sin(gamma)
                    - .014615 * np.cos(2 * gamma) - .040849 * np.sin(2 * gamma))
    dec = (.006918 - .399912 * np.cos(gamma) + .070257 * np.sin(gamma)
           - .006758 * np.cos(2 * gamma) + .000907 * np.sin(2 * gamma)
           - .002697 * np.cos(3 * gamma) + .00148 * np.sin(3 * gamma))
    ha = np.deg2rad((hour * 60 + eq + 4 * np.asarray(lon) - 60 * 9) / 4 - 180)
    phi = np.deg2rad(lat)
    altitude = np.arcsin(np.clip(np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.cos(ha), -1, 1))
    azimuth = np.arctan2(np.sin(ha), np.cos(ha) * np.sin(phi) - np.tan(dec) * np.cos(phi)) + np.pi
    return np.rad2deg(altitude), np.rad2deg(azimuth) % 360


def horizon_angles(center_m, elevations_m, distances_m):
    """거리별 DSM 높이로 방위별 지평선 각도를 구한다. 결측을 평지로 채우지 않는다."""
    z, distances = np.asarray(elevations_m, float), np.asarray(distances_m, float)
    if not np.isfinite(center_m) or np.any(distances <= 0):
        raise ValueError("Finite center height and positive distances required")
    good = np.isfinite(z)
    angle = np.where(good, np.degrees(np.arctan2(z - center_m, distances)), -np.inf)
    result = np.maximum(0, angle.max(axis=-1))
    # 일부 누락된 방향도 알 수 없는 장애물이 있을 수 있으므로 보수적으로 미산출한다.
    return np.where(good.all(axis=-1), result, np.nan)


class CopernicusSampler:
    def __init__(self, paths):
        import rasterio
        self.tiles = []
        for path in paths:
            with rasterio.open(path) as ds:
                if ds.crs.to_epsg() != 4326 or ds.scales != (1.,) or ds.offsets != (0.,):
                    raise ValueError("Unexpected public GLO-30 grid")
                grid = ds.read(1, masked=True).filled(np.nan)
                grid[(grid < -500) | (grid > 9000)] = np.nan
                self.tiles.append((ds.transform, ds.bounds, grid))
        if not self.tiles:
            raise ValueError("No Copernicus tiles")
        self.geod = Geod(ellps="WGS84")

    def sample(self, lon, lat):
        lon, lat = np.broadcast_arrays(np.asarray(lon, float), np.asarray(lat, float))
        result = np.full(lon.shape, np.nan)
        for transform, bounds, grid in self.tiles:
            mask = (lon >= bounds.left) & (lon < bounds.right) & (lat > bounds.bottom) & (lat <= bounds.top)
            if mask.any():
                cols = np.floor((lon[mask] - transform.c) / transform.a).astype(int)
                rows = np.floor((lat[mask] - transform.f) / transform.e).astype(int)
                result[mask] = grid[rows, cols]
        return result

    def features(self, lon, lat):
        center = float(self.sample(lon, lat))
        if not np.isfinite(center):
            raise ValueError("Target outside DSM coverage")
        xx, yy = np.meshgrid(np.arange(-500, 501, 50), np.arange(-500, 501, 50))
        distance = np.hypot(xx, yy)
        mask = distance <= 500
        azimuth = np.degrees(np.arctan2(xx[mask], yy[mask]))
        x, y, _ = self.geod.fwd(np.full(mask.sum(), lon), np.full(mask.sum(), lat), azimuth, distance[mask])
        nearby = self.sample(x, y)
        valid = nearby[np.isfinite(nearby)]
        bearings = np.arange(0., 360., 22.5)
        distances = np.arange(60., 3001., 60.)
        b, d = np.meshgrid(bearings, distances, indexing="ij")
        x, y, _ = self.geod.fwd(np.full(b.size, lon), np.full(b.size, lat), b.ravel(), d.ravel())
        elevations = self.sample(x, y).reshape(b.shape)
        horizon = horizon_angles(center, elevations, distances)
        result = {"dsm_elevation_m": center, "dsm_relative_500m": center - float(np.median(valid)),
                  "dsm_percentile_500m": float(np.mean(valid <= center)),
                  "dsm_valid_fraction_500m": float(len(valid) / len(nearby)),
                  "horizon_max_deg": float(np.max(horizon)),
                  "sky_view_proxy": float(np.mean(np.cos(np.deg2rad(horizon)) ** 2))}
        result.update({f"horizon_{i:02d}_deg": float(v) for i, v in enumerate(horizon)})
        return result


def join_power_history(target, radiation):
    """사후 전용: 시간 구간이 완전히 끝난 복사량만 결합한다. 공개 지연은 별도 제약."""
    if radiation.duplicated(["grid_id", "source_interval_end"]).any():
        raise ValueError("Duplicate radiation hour")
    left = target.copy()
    left["_original_order"] = np.arange(len(left))
    result = pd.merge_asof(left.sort_values("time"), radiation.sort_values("source_interval_end"),
                           left_on="time", right_on="source_interval_end", by="grid_id",
                           direction="backward", tolerance=pd.Timedelta("60min"), allow_exact_matches=True)
    good = result.source_interval_end.notna()
    if not (result.loc[good, "source_interval_end"] <= result.loc[good, "time"]).all():
        raise AssertionError("Unfinished radiation interval")
    return result.sort_values("_original_order").drop(columns="_original_order").reset_index(drop=True)
