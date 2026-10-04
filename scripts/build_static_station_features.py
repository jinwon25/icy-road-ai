"""Extract development-station facility proximity from supplied, projected polygons.

The private extracted shapefiles and feature table are deliberately git-ignored.
No RWIS outcome or protected-station location is read by this script.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validation import PROTECTED_STATIONS

PRIVATE = ROOT / "outputs" / "private"
SPATIAL = PRIVATE / "spatial"
LAYERS = {"bridge": "N3A_A0070000", "tunnel": "N3A_A0110020"}


def _extract_layer(archive: zipfile.ZipFile, stem: str) -> Path:
    folder = SPATIAL / "facilities" / stem
    folder.mkdir(parents=True, exist_ok=True)
    for entry in archive.infolist():
        if Path(entry.filename).stem != stem or Path(entry.filename).suffix.lower() not in {
            ".shp", ".shx", ".dbf", ".prj", ".cpg"
        }:
            continue
        target = folder / Path(entry.filename).name
        if not target.exists() or target.stat().st_size != entry.file_size:
            with archive.open(entry) as source, target.open("wb") as dest:
                while chunk := source.read(1024 * 1024):
                    dest.write(chunk)
    path = folder / f"{stem}.shp"
    if not path.exists():
        raise FileNotFoundError(f"Required facility layer missing: {stem}")
    return path


def _facilities(path: Path, road: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict]:
    info = pyogrio.read_info(path)
    crs = info["crs"]
    if not crs:
        raise ValueError(f"CRS missing: {path}")
    # Read only the highway neighborhood. The source files cover all Korea.
    native_bbox = gpd.GeoSeries([box(*road.total_bounds).buffer(5000)], crs=road.crs).to_crs(crs).total_bounds
    frame = gpd.read_file(path, bbox=tuple(native_bbox), columns=[]).to_crs(road.crs)
    frame = frame.loc[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
    if frame.empty:
        raise ValueError(f"No nearby facility geometry: {path}")
    return frame, {"source_records": int(info["features"]), "nearby_records": len(frame),
                   "source_crs": str(crs), "geometry_types": frame.geom_type.value_counts().to_dict()}


def _distance(point, frame: gpd.GeoDataFrame) -> float:
    indices = frame.sindex.nearest(point, return_all=True)[1]
    return float(frame.geometry.iloc[indices].distance(point).min())


def build() -> tuple[pd.DataFrame, dict]:
    inventory = pd.read_csv(PRIVATE / "full" / "station_inventory.csv", dtype=str,
                            encoding="utf-8-sig")
    stations = inventory.loc[inventory.kind.eq("RWIS") & inventory.protected.eq("False")
                             & inventory.station_id.ne("<missing>")].copy()
    if set(stations.station_id) & PROTECTED_STATIONS or len(stations) != 14:
        raise AssertionError("Development station list is incomplete or includes protected IDs")
    stations["lat"] = pd.to_numeric(stations.latitudes, errors="raise")
    stations["lon"] = pd.to_numeric(stations.longitudes, errors="raise")
    road = gpd.read_file(SPATIAL / "jb_road_center_line.shp", columns=[])
    if road.crs is None or not road.crs.is_projected:
        raise ValueError("Highway centerline has no projected CRS")
    points = gpd.GeoDataFrame(stations, geometry=gpd.points_from_xy(stations.lon, stations.lat),
                              crs="EPSG:4326").to_crs(road.crs)
    with zipfile.ZipFile(SPATIAL / "other_spatial.zip") as archive:
        paths = {kind: _extract_layer(archive, stem) for kind, stem in LAYERS.items()}
    facilities = {}
    metadata = {}
    for kind, path in paths.items():
        facilities[kind], metadata[kind] = _facilities(path, road)
    rows = []
    for row in points.itertuples():
        point = row.geometry
        item = {"station": row.station_id}
        for kind, frame in facilities.items():
            item[f"{kind}_distance_m"] = _distance(point, frame)
        rows.append(item)
    table = pd.DataFrame(rows).sort_values("station").reset_index(drop=True)
    summary = {"status": "development_static_facility_proximity",
               "crs": str(road.crs), "station_count": len(table), "facilities": metadata,
               "feature_meanings": {"bridge_distance_m": "distance to nearest bridge polygon",
                                    "tunnel_distance_m": "distance to nearest tunnel polygon"},
               "distance_summary_m": {kind: {"min": float(table[f"{kind}_distance_m"].min()),
                                               "median": float(table[f"{kind}_distance_m"].median()),
                                               "max": float(table[f"{kind}_distance_m"].max()),
                                               "within_100m": int(table[f"{kind}_distance_m"].le(100).sum())}
                                      for kind in LAYERS},
               "caveat": "Facility source vintage for both observation winters is not documented; exploratory ablation only."}
    return table, summary


def main() -> None:
    table, summary = build()
    out = SPATIAL / "station_facility"
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "features.csv", index=False, encoding="utf-8-sig")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
