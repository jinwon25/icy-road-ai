"""Check development RWIS positions against the supplied highway centerlines."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validation import PROTECTED_STATIONS

ROUTE_NAMES = {"서해안": "서해안고속국도", "호남선": "호남고속국도",
               "통영-대전중부선": "통영-대전고속국도"}


def main() -> None:
    inventory = pd.read_csv(ROOT / "outputs" / "private" / "full" / "station_inventory.csv",
                            dtype=str, encoding="utf-8-sig")
    stations = inventory.loc[inventory.kind.eq("RWIS") & inventory.protected.eq("False")
                             & inventory.station_id.ne("<missing>")].copy()
    if set(stations.station_id) & PROTECTED_STATIONS:
        raise AssertionError("Protected RWIS entered spatial development audit")
    stations["lat"] = pd.to_numeric(stations.latitudes, errors="raise")
    stations["lon"] = pd.to_numeric(stations.longitudes, errors="raise")
    road = gpd.read_file(ROOT / "outputs" / "private" / "spatial" / "jb_road_center_line.shp")
    if road.crs is None or not road.crs.is_projected:
        raise ValueError("Road centerline needs an explicit projected CRS")
    geometries = {name: part.geometry.union_all() for name, part in road.groupby("NAME")}
    if set(ROUTE_NAMES.values()) != set(geometries):
        raise ValueError("Unexpected highway names in the centerline")
    points = gpd.GeoDataFrame(stations, geometry=gpd.points_from_xy(stations.lon, stations.lat),
                              crs="EPSG:4326").to_crs(road.crs)
    rows = []
    for item in points.itertuples():
        expected = ROUTE_NAMES.get(item.routes.strip())
        if expected is None:
            raise ValueError(f"Unmapped RWIS route: {item.routes}")
        distances = {name: float(item.geometry.distance(geometry))
                     for name, geometry in geometries.items()}
        nearest = min(distances, key=distances.get)
        rows.append({"station": item.station_id, "route": item.routes,
                     "expected_road_name": expected, "nearest_road_name": nearest,
                     "distance_to_expected_m": distances[expected],
                     "distance_to_nearest_m": distances[nearest],
                     "nearest_matches_route": nearest == expected})
    table = pd.DataFrame(rows)
    summary = {"status": "static_development_station_check",
               "stations": len(table), "road_crs": str(road.crs),
               "distance_to_expected_m_median": float(table.distance_to_expected_m.median()),
               "distance_to_expected_m_max": float(table.distance_to_expected_m.max()),
               "stations_over_500m": int(table.distance_to_expected_m.gt(500).sum()),
               "nearest_route_mismatch": int((~table.nearest_matches_route).sum()),
               "purpose": "position QA only; no protected RWIS or hazard score"}
    out = ROOT / "outputs" / "private" / "spatial"
    table.to_csv(out / "station_road_alignment.csv", index=False, encoding="utf-8-sig")
    (out / "station_road_alignment_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
