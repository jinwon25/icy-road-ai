"""공개 DSM 지형·태양 위치와 사후 NASA 복사량을 분리해 개발 입력으로 저장한다."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.solar_terrain import CopernicusSampler, solar_position, join_power_history
from src.data_source import sha256_file
from src.validation import assert_training_stations

TERRAIN = ["dsm_elevation_m", "dsm_relative_500m", "dsm_percentile_500m", "horizon_max_deg", "sky_view_proxy"]
SOLAR = ["sun_altitude_deg", "sun_visible_proxy", "clear_sky_horizontal_proxy"]
RADIATION = ["power_shortwave_wh_m2", "power_longwave_wh_m2"]


def main():
    private = ROOT / "outputs/private"
    out = private / "solar_terrain_features"
    out.mkdir(parents=True, exist_ok=True)
    tile_paths = sorted((private / "external/copernicus_dem").glob("*.tif"))
    dem = CopernicusSampler(tile_paths)
    metadata = pd.read_csv(private / "sensor_availability/metadata.csv", dtype={"station": str})
    metadata = metadata.loc[metadata.kind.eq("RWIS"), ["station", "lat", "lon"]]
    assert_training_stations(metadata.station)
    station_rows = [{"station": r.station, "lat": r.lat, "lon": r.lon, **dem.features(r.lon, r.lat)} for r in metadata.itertuples()]
    station = pd.DataFrame(station_rows)
    segments = gpd.read_file(private / "spatial/segment_scaffold/segments.gpkg")
    points = gpd.GeoSeries(segments.geometry.interpolate(.5, normalized=True), crs=segments.crs).to_crs(4326)
    segment_rows = [{"seg_id": ident, "lon": p.x, "lat": p.y, **dem.features(p.x, p.y)} for ident, p in zip(segments.seg_id, points)]
    station.to_csv(out / "station_terrain.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(segment_rows).to_csv(out / "segment_terrain.csv", index=False, encoding="utf-8-sig")
    data = pd.read_parquet(private / "physical_features/features.parquet")
    data["station"] = data.station.astype(str)
    reference = data[["station", "time", "ice"]].copy()
    # 기존 좌표 열과 구별하여 정적 메타데이터를 명시적으로 사용한다.
    geo = station.rename(columns={"lat": "terrain_lat", "lon": "terrain_lon"})
    data = data.merge(geo, on="station", how="left", validate="many_to_one")
    altitude, azimuth = solar_position(data.time, data.terrain_lat, data.terrain_lon)
    horizon = data[[f"horizon_{i:02d}_deg" for i in range(16)]].to_numpy()
    bearing_index = azimuth / 22.5
    lower = np.floor(bearing_index).astype(int) % 16
    fraction = bearing_index % 1
    i = np.arange(len(data))
    obstruction = horizon[i, lower] * (1 - fraction) + horizon[i, (lower + 1) % 16] * fraction
    data["sun_altitude_deg"] = altitude
    data["sun_visible_proxy"] = np.where(np.isfinite(obstruction), (altitude > obstruction).astype(float), np.nan)
    data["clear_sky_horizontal_proxy"] = np.maximum(0, np.sin(np.deg2rad(altitude))) * data.sun_visible_proxy
    data["grid_id"] = [f"N{np.floor(lat)+.5:.1f}_E{np.floor(lon)+.5:.1f}" for lat, lon in zip(data.terrain_lat, data.terrain_lon)]
    power_path = private / "external/nasa_power/hourly.parquet"
    power = pd.read_parquet(power_path)[["grid_id", "source_hour_kst", "source_interval_end", *RADIATION]]
    data = join_power_history(data, power)
    pd.testing.assert_frame_equal(data[["station", "time", "ice"]], reference)
    data.to_parquet(out / "features.parquet", index=False, compression="zstd")
    summary = {"status": "development_candidates_not_validated", "rows": len(data), "stations": len(station), "segments": len(segments),
               "terrain_solar_features": TERRAIN + SOLAR, "retrospective_radiation_features": RADIATION,
               "nonmissing": {c: int(data[c].notna().sum()) for c in TERRAIN + SOLAR + RADIATION},
               "inputs": {"physical_features": sha256_file(private / "physical_features/features.parquet"), "power": sha256_file(power_path),
                          "tiles": {p.name: sha256_file(p) for p in tile_paths}},
               "vertical_reference": "EGM2008 EPSG:3855, metres; Copernicus Product Handbook v5.0 pp10,13",
               "method": "DSM nearest pixel; 500m neighbourhood sampled at 50m; 16 horizon bearings every22.5degrees,60m steps to3km; NOAA solar equation KST UTC+9",
               "limitations": ["DSM includes canopy/buildings; road deck elevation, grade and engineering shadow are not established.",
                               "Horizon truncates at 3km and 16 directions; interpolated terrain shadow is a proxy without local validation.",
                               "Approximate sky-view is mean cosine-squared horizon angle; no complete RoadSurf energy/storage balance.",
                               "Native provided DEM has unverified normalization; it is not used as metre terrain height.",
                               "NASA radiation has multi-day publication latency: retrospective estimation only, not real-time forecasting.",
                               "The prior completed hour join prevents interval overlap but does not remove publication latency.",
                               "Solar geometry and static DSM features do not themselves require future weather observations.",
                               "Scores or risk levels are not assigned to the 467 geometry fragments by this script."],
               "attribution_files": ["external/copernicus_dem/manifest.json", "external/nasa_power/manifest.json"]}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ["status", "rows", "stations", "segments", "nonmissing"]}), flush=True)


if __name__ == "__main__":
    main()
