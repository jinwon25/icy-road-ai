"""Limit facility proximity to polygons intersecting each RWIS highway route.

Route membership is an explicit geometric approximation: a facility polygon
must intersect a 50 m buffer around a supplied highway centerline. The source
vintage is unverified, so this is a development ablation, not a final map.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_static_station_features import LAYERS, PRIVATE, SPATIAL, _extract_layer, _facilities, _distance
from src.validation import PROTECTED_STATIONS


def main() -> None:
    inventory = pd.read_csv(PRIVATE / "full" / "station_inventory.csv", dtype=str,
                            encoding="utf-8-sig")
    stations = inventory.loc[inventory.kind.eq("RWIS") & inventory.protected.eq("False")
                             & inventory.station_id.ne("<missing>")].copy()
    if len(stations) != 14 or set(stations.station_id) & PROTECTED_STATIONS:
        raise AssertionError("Protected or missing development station")
    stations["lat"] = pd.to_numeric(stations.latitudes, errors="raise")
    stations["lon"] = pd.to_numeric(stations.longitudes, errors="raise")
    road = gpd.read_file(SPATIAL / "jb_road_center_line.shp", columns=["NAME"])
    if str(road.crs) != "EPSG:5179":
        raise ValueError(f"Unexpected road CRS: {road.crs}")
    points = gpd.GeoDataFrame(stations, geometry=gpd.points_from_xy(stations.lon, stations.lat),
                              crs="EPSG:4326").to_crs(road.crs)
    road_buffer = gpd.GeoDataFrame(road[["NAME"]].copy(), geometry=road.geometry.buffer(50),
                                   crs=road.crs)
    with zipfile.ZipFile(SPATIAL / "other_spatial.zip") as archive:
        paths = {kind: _extract_layer(archive, stem) for kind, stem in LAYERS.items()}
    routed = {}
    layer_summary = {}
    for kind, path in paths.items():
        frame, metadata = _facilities(path, road)
        joined = gpd.sjoin(frame, road_buffer, how="inner", predicate="intersects")
        joined = joined.reset_index(names="facility_index").drop_duplicates(["facility_index", "NAME"])
        if joined.empty:
            raise ValueError(f"No highway-aligned {kind} polygons")
        routed[kind] = {name: part for name, part in joined.groupby("NAME")}
        layer_summary[kind] = {**metadata, "route_aligned_unique_polygons": int(joined.facility_index.nunique()),
                               "route_counts": {str(name): len(part) for name, part in routed[kind].items()}}
    records = []
    for row in points.itertuples():
        point = row.geometry
        nearest_indices = road.sindex.nearest(point, return_all=True)[1]
        distances = road.geometry.iloc[nearest_indices].distance(point)
        road_row = road.iloc[int(nearest_indices[distances.argmin()])]
        if float(distances.min()) > 50:
            raise ValueError(f"RWIS station farther than 50 m from highway: {row.station_id}")
        name = road_row.NAME
        record = {"station": row.station_id, "route_name": name,
                  "distance_to_route_m": float(distances.min())}
        for kind in LAYERS:
            if name not in routed[kind]:
                raise ValueError(f"No route-aligned {kind} for route {name}")
            record[f"{kind}_distance_m"] = _distance(point, routed[kind][name])
        records.append(record)
    table = pd.DataFrame(records).sort_values("station").reset_index(drop=True)
    summary = {"status": "development_route_aligned_facility_proximity",
               "station_count": len(table), "road_crs": str(road.crs),
               "corridor_buffer_m": 50, "facilities": layer_summary,
               "distance_summary_m": {kind: {"median": float(table[f"{kind}_distance_m"].median()),
                                               "max": float(table[f"{kind}_distance_m"].max()),
                                               "within_100m": int(table[f"{kind}_distance_m"].le(100).sum())}
                                      for kind in LAYERS},
               "limitation": "Geometric route association and source vintage remain unverified; exploratory only."}
    out = SPATIAL / "station_facility_route"
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "features.csv", index=False, encoding="utf-8-sig")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
