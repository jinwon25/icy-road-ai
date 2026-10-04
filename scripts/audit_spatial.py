"""Inspect spatial metadata; write only git-ignored private summaries."""
from __future__ import annotations

import json
import shutil
import struct
import zipfile
from collections import Counter
from pathlib import Path

import geopandas as gpd
from pyproj import CRS

from audit_data import decoded_name
from src.data_source import competition_archive

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "private" / "spatial"


def copy_entry(archive, info, target):
    if not target.exists() or target.stat().st_size != info.file_size:
        with archive.open(info) as source, target.open("wb") as dest:
            shutil.copyfileobj(source, dest, length=1024 * 1024)


def tiff_metadata(path):
    wanted = {256, 257, 258, 259, 339, 33550, 33922, 34264, 34735, 34736, 34737, 42113}
    sizes = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 11: 4, 12: 8}
    formats = {1: "B", 3: "H", 4: "I", 11: "f", 12: "d"}
    with path.open("rb") as stream:
        endian = "<" if stream.read(2) == b"II" else ">"
        if struct.unpack(endian + "H", stream.read(2))[0] != 42:
            raise ValueError("Not a classic TIFF")
        stream.seek(struct.unpack(endian + "I", stream.read(4))[0])
        count = struct.unpack(endian + "H", stream.read(2))[0]
        tags = {}
        for _ in range(count):
            entry = stream.read(12)
            tag, kind, length, offset = struct.unpack(endian + "HHII", entry)
            if tag not in wanted or kind not in sizes or length > 10000:
                continue
            total = sizes[kind] * length
            if total <= 4:
                raw = entry[8:8 + total]
            else:
                pos = stream.tell()
                stream.seek(offset)
                raw = stream.read(total)
                stream.seek(pos)
            if kind == 2:
                value = raw.rstrip(b"\x00").decode("ascii", errors="replace")
            elif kind in formats:
                value = struct.unpack(endian + str(length) + formats[kind], raw)
                value = value[0] if length == 1 else list(value)
            else:
                value = raw.hex()
            tags[str(tag)] = value
    width, height = tags["256"], tags["257"]
    scale, tie = tags.get("33550"), tags.get("33922")
    bounds = None
    if scale and tie and len(scale) >= 2 and len(tie) >= 6:
        x0 = tie[3] - tie[0] * scale[0]
        y0 = tie[4] + tie[1] * scale[1]
        bounds = [x0, y0 - height * scale[1], x0 + width * scale[0], y0]
    geokeys = {}
    directory = tags.get("34735")
    if directory:
        for index in range(directory[3]):
            key, source, length, value = directory[4 + 4 * index:8 + 4 * index]
            if source == 0:
                geokeys[str(key)] = value
    return {"width": width, "height": height, "bounds": bounds,
            "pixel_scale": scale, "nodata": tags.get("42113"),
            "bits_per_sample": tags.get("258"), "sample_format": tags.get("339"),
            "geokeys": geokeys, "vertical_unit_code": geokeys.get("4099"),
            "tags": tags}


def nested_layer_metadata(archive):
    layers = {}
    for info in archive.infolist():
        name = decoded_name(info)
        suffix = Path(name).suffix.lower()
        if suffix not in (".shp", ".dbf", ".prj"):
            continue
        stem = str(Path(name).with_suffix(""))
        layer = layers.setdefault(stem, {})
        with archive.open(info) as stream:
            if suffix == ".shp":
                header = stream.read(100)
                layer["geometry_type_code"] = struct.unpack("<i", header[32:36])[0]
                layer["bounds_native"] = list(struct.unpack("<4d", header[36:68]))
            elif suffix == ".dbf":
                header = stream.read(32)
                layer["records"] = struct.unpack("<I", header[4:8])[0]
            else:
                wkt = stream.read().decode("ascii", errors="replace")
                try:
                    layer["crs"] = str(CRS.from_wkt(wkt))
                except Exception:
                    layer["crs_wkt"] = wkt[:300]
    return layers


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    archive_path = competition_archive(ROOT)
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            if "jb_road_center_line." in info.filename and info.filename.endswith((".shp", ".shx", ".dbf", ".prj", ".cpg")):
                copy_entry(archive, info, OUT / Path(info.filename).name)
        copy_entry(archive, next(i for i in archive.infolist() if i.filename.endswith(".tif")), OUT / "dem.tif")
        copy_entry(archive, next(i for i in archive.infolist() if i.filename.endswith(".zip")), OUT / "other_spatial.zip")
    road = gpd.read_file(OUT / "jb_road_center_line.shp")
    road_info = {"features": len(road), "crs": str(road.crs),
                 "bounds_native": list(map(float, road.total_bounds)),
                 "geometry_types": dict(Counter(road.geom_type.astype(str))),
                 "invalid_geometries": int((~road.geometry.is_valid).sum()),
                 "empty_geometries": int(road.geometry.is_empty.sum()),
                 "columns": road.columns.tolist(),
                 "route_counts": road.NAME.value_counts(dropna=False).to_dict(),
                 "route_length_km": (road.assign(length_km=road.length / 1000)
                                      .groupby("NAME").length_km.sum().to_dict()),
                 "road_numbers": road.RDNU.value_counts(dropna=False).to_dict()}
    with zipfile.ZipFile(OUT / "other_spatial.zip") as inner:
        manifest = [{"name": decoded_name(i), "bytes": i.file_size,
                     "compressed_bytes": i.compress_size} for i in inner.infolist()]
        nested = {"entries": len(manifest),
                  "total_uncompressed_bytes": sum(x["bytes"] for x in manifest),
                  "extensions": dict(Counter(Path(x["name"]).suffix.lower() for x in manifest)),
                  "layers": nested_layer_metadata(inner)}
    report = {"road_centerline": road_info, "dem": tiff_metadata(OUT / "dem.tif"),
              "nested_archive": nested}
    (OUT / "spatial_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "nested_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"road_features": len(road), "dem_size": [report["dem"]["width"], report["dem"]["height"]],
                      "nested_entries": len(manifest)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
