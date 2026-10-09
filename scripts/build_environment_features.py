"""개발 관측소·최대 1km 도형에 지형·수계·시설 특징을 같은 방식으로 생성한다."""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.terrain_features import DemSampler, curvature_proxy
from src.validation import assert_training_stations
from src.data_source import sha256_file
from scripts.build_static_station_features import _extract_layer, _facilities, _distance


def main():
    private = ROOT / "outputs/private"
    spatial = private / "spatial"
    roads = gpd.read_file(spatial / "jb_road_center_line.shp")
    segments = gpd.read_file(spatial / "segment_scaffold/segments.gpkg")
    if roads.crs.to_epsg() != 5179 or segments.crs.to_epsg() != 5179:
        raise ValueError("Metric road CRS required")
    inventory = pd.read_csv(private / "sensor_availability/metadata.csv", dtype={"station": str})
    inventory = inventory.loc[inventory.kind.eq("RWIS")].copy()
    assert_training_stations(inventory.station.unique())
    stations = gpd.GeoDataFrame(inventory, geometry=gpd.points_from_xy(inventory.lon, inventory.lat), crs=4326).to_crs(5179)
    layers = {}
    layer_info = {}
    with zipfile.ZipFile(spatial / "other_spatial.zip") as archive:
        for name, stem in [("bridge", "N3A_A0070000"), ("tunnel", "N3A_A0110020"), ("river", "TN_RIVER_BNDRY")]:
            path = _extract_layer(archive, stem)
            layers[name], layer_info[name] = _facilities(path, roads)
    dem = DemSampler(spatial / "dem.tif")
    out = spatial / "environment_features"
    out.mkdir(parents=True, exist_ok=True)
    segment_rows = []
    for row in segments.itertuples():
        point = row.geometry.interpolate(.5, normalized=True)
        result = {"seg_id": row.seg_id, "route_name": row.route_nm,
                  **dem.at_projected_point(point.x, point.y), **curvature_proxy(row.geometry)}
        sensitivity = curvature_proxy(row.geometry, spacing_m=25.)
        result["curvature_p90_25m_inv_m"] = sensitivity["curvature_p90_inv_m"]
        for name, layer in layers.items():
            result[f"{name}_distance_m"] = _distance(point, layer)
        segment_rows.append(result)
    segment_table = pd.DataFrame(segment_rows)
    station_rows = []
    for row in stations.itertuples():
        point = row.geometry
        indices = segments.sindex.nearest(point, return_all=True)[1]
        distances = segments.geometry.iloc[indices].distance(point)
        nearest = segments.iloc[int(indices[distances.argmin()])]
        curve = segment_table.set_index("seg_id").loc[nearest.seg_id]
        result = {"station": row.station, "route": row.route, "supplied_elevation_m": row.elevation_m,
                  "segment_id": nearest.seg_id, "distance_to_centerline_m": float(distances.min()),
                  **dem.at_projected_point(point.x, point.y),
                  "curvature_p90_inv_m": curve.curvature_p90_inv_m,
                  "curvature_p90_25m_inv_m": curve.curvature_p90_25m_inv_m}
        for name, layer in layers.items():
            result[f"{name}_distance_m"] = _distance(point, layer)
        station_rows.append(result)
    station_table = pd.DataFrame(station_rows)
    station_table.to_csv(out / "station_features.csv", index=False, encoding="utf-8-sig")
    segment_table.to_csv(out / "segment_features.csv", index=False, encoding="utf-8-sig")
    summary = {"status": "static_environment_candidates_not_risk_scores", "stations": len(station_table),
               "segments": len(segment_table), "layers": layer_info,
               "dem_crs_wkt": dem.crs.to_wkt(), "dem_horizontal_transform": dem.transformer.description,
               "dem_vertical_unit_code": dem.vertical_unit, "dem_sha256": sha256_file(spatial / "dem.tif"),
               "station_dem_available": int(station_table.dem_value.notna().sum()),
               "segment_dem_available": int(segment_table.dem_value.notna().sum()),
               "limitations": ["DEM height retained in native values; no unverified metre slope or horizon-angle calculation.",
                               "500m terrain percentile is invariant to positive vertical unit scaling.",
                               "Curvature is a 25m/50m geometric proxy, not official engineering radius.",
                               "Facility distance is horizontal polygon proximity, not verified carriageway membership.",
                               "River proximity alone does not establish higher humidity or causal icing risk.",
                               "Source vintage, direction and official chainage remain unverified.",
                               "Segment attributes use midpoint location; they do not represent worst-case values along the entire segment."]}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ["status", "stations", "segments", "station_dem_available", "segment_dem_available", "dem_vertical_unit_code"]}), flush=True)


if __name__ == "__main__":
    main()
