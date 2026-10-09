"""공식 2024 표준노드링크와 제공 도로 구간의 비공개 공간 감사.

최종 구간·공식 이정·위험 점수를 확정하지 않는다. 방향별 링크는 실제
차로 중심선과 이격된 교통정보 표현일 수 있으므로 원본 선형을 보존한다.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely.geometry import Point
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file
from src.frozen_assessment import verify_freeze

ARCHIVE_SHA = "35efe0871e23dd2967af554d227afd448268d04e20d19933819288dd879b05de"
ROUTES = {
    "서해안고속국도": ("15", "서해안고속도로"),
    "호남고속국도": ("25", "호남고속도로"),
    "통영-대전고속국도": ("35", "통영대전고속도로"),
}
SAMPLE_SPACING_M = 25.0
NODE_TOLERANCE_M = 30.0
ORIENTATION_MARGIN_M = 1.0
CORRIDOR_M = 2000.0


def main():
    frozen = verify_freeze(ROOT)
    private = ROOT / "outputs/private"
    archive = private / "external/official_nodelink_20240325/NODELINKDATA.zip"
    if sha256_file(archive) != ARCHIVE_SHA:
        raise ValueError("Official archive digest changed")
    scaffold = private / "spatial/segment_scaffold/segments.gpkg"
    segments = gpd.read_file(scaffold)
    if segments.crs.to_epsg() != 5179 or set(segments.route_nm) != set(ROUTES):
        raise ValueError("Unexpected provided geometry scope or metric CRS")
    base = f"/vsizip/{archive.resolve().as_posix()}"
    national = pyogrio.read_dataframe(
        base + "/MOCT_LINK.shp",
        where="ROAD_RANK='101' AND ROAD_NO IN ('15','25','35')", encoding="CP949")
    if national.crs is None:
        raise ValueError("Official source lacks CRS")
    original_wkt = national.crs.to_wkt()
    # Preserve the supplied WKT; assigning EPSG:5179 would displace this release.
    national = national.to_crs(5179)
    scope = pd.Series(False, index=national.index)
    for provided_name, (number, official_name) in ROUTES.items():
        scope |= national.ROAD_NO.eq(number) & national.ROAD_NAME.eq(official_name)
    links = national.loc[scope].copy().reset_index(drop=True)
    if links.LINK_ID.duplicated().any() or links.geometry.is_empty.any() or not links.is_valid.all():
        raise ValueError("Invalid or duplicate official links")
    if not links.ROAD_USE.isin(["0", "1"]).all() or not links.CONNECT.isin(["0", "1"]).all():
        raise ValueError("Unknown official use or ramp code")
    links["provided_route"] = links.ROAD_NAME.map({v[1]: k for k, v in ROUTES.items()})
    links["active_non_ramp"] = links.ROAD_USE.eq("0") & links.CONNECT.eq("0")
    links["geometric_length_m"] = links.length
    nodes = pyogrio.read_dataframe(base + "/MOCT_NODE.shp", encoding="CP949").to_crs(5179)
    if nodes.NODE_ID.duplicated().any():
        raise ValueError("Duplicate official nodes")
    node_map = nodes.set_index("NODE_ID").geometry.to_dict()
    orientation = []
    for row in links.itertuples():
        a, b = Point(row.geometry.coords[0]), Point(row.geometry.coords[-1])
        f, t = node_map.get(row.F_NODE), node_map.get(row.T_NODE)
        record = {"LINK_ID": row.LINK_ID, "orientation_check": "missing_node"}
        if f is not None and t is not None:
            forward = [a.distance(f), b.distance(t)]
            reverse = [a.distance(t), b.distance(f)]
            status = "ambiguous_or_outside_tolerance"
            if sum(forward) + ORIENTATION_MARGIN_M < sum(reverse) and max(forward) <= NODE_TOLERANCE_M:
                status = "geometry_order_matches_flow_nodes"
            elif sum(reverse) + ORIENTATION_MARGIN_M < sum(forward) and max(reverse) <= NODE_TOLERANCE_M:
                status = "geometry_order_reversed_from_flow_nodes"
            record.update(orientation_check=status, start_to_f_m=forward[0], end_to_t_m=forward[1],
                          start_to_t_m=reverse[0], end_to_f_m=reverse[1])
        orientation.append(record)
    links = links.merge(pd.DataFrame(orientation), on="LINK_ID", validate="one_to_one")
    samples, segment_records, route_records, corridor_parts = [], [], [], []
    for route_name in ROUTES:
        provided = segments.loc[segments.route_nm.eq(route_name)]
        pool = links.loc[links.provided_route.eq(route_name) & links.ROAD_USE.eq("0")].reset_index(drop=True)
        mainline = pool.loc[pool.active_non_ramp].reset_index(drop=True)
        if pool.empty or mainline.empty:
            raise ValueError("No official comparison candidates")
        tree, main_tree = STRtree(pool.geometry.to_numpy()), STRtree(mainline.geometry.to_numpy())
        corridor = provided.geometry.union_all().buffer(CORRIDOR_M)
        # Review corridor only: neither an administrative clip nor final road extent.
        nearby = pool.loc[pool.geometry.intersects(corridor)].copy()
        corridor_parts.append(nearby)
        before = len(samples)
        for row in provided.itertuples():
            count = max(1, int(np.ceil(row.geometry.length / SAMPLE_SPACING_M)))
            offsets = np.linspace(0, row.geometry.length, count + 1)
            points = np.array([row.geometry.interpolate(float(x)) for x in offsets], dtype=object)
            indices = np.asarray(tree.nearest(points), dtype=int)
            main_indices = np.asarray(main_tree.nearest(points), dtype=int)
            distances, main_distances, ramp_flags = [], [], []
            for offset, point, ix, mix in zip(offsets, points, indices, main_indices):
                candidate, main = pool.iloc[ix], mainline.iloc[mix]
                distance, main_distance = point.distance(candidate.geometry), point.distance(main.geometry)
                distances.append(distance); main_distances.append(main_distance)
                ramp_flags.append(candidate.CONNECT == "1")
                samples.append({"seg_id": row.seg_id, "route": route_name, "offset_m": float(offset),
                                "sample_weight_m": float(row.geometry.length / len(points)),
                                "nearest_active_link": candidate.LINK_ID, "distance_m": float(distance),
                                "nearest_connect": candidate.CONNECT, "nearest_road_type": candidate.ROAD_TYPE,
                                "nearest_orientation_check": candidate.orientation_check,
                                "nearest_active_non_ramp_link": main.LINK_ID,
                                "non_ramp_distance_m": float(main_distance),
                                "nearest_link_tie_assessed": False})
            segment_records.append({"seg_id": row.seg_id, "route": route_name,
                                    "length_m": row.geometry.length, "samples": len(points),
                                    "max_active_link_distance_m": float(max(distances)),
                                    "median_active_link_distance_m": float(np.median(distances)),
                                    "max_non_ramp_distance_m": float(max(main_distances)),
                                    "nearest_ramp_sample_fraction": float(np.mean(ramp_flags)),
                                    "all_samples_within_30m_non_ramp": bool(max(main_distances) <= 30),
                                    "all_samples_within_100m_non_ramp": bool(max(main_distances) <= 100),
                                    "flow_direction_assigned_to_original_segment": False})
        part = pd.DataFrame(samples[before:])
        weights = part.sample_weight_m.to_numpy()
        route_records.append({"route": route_name, "provided_segments": len(provided),
                              "provided_length_m": float(provided.length.sum()),
                              "official_named_route_national_links": int(links.provided_route.eq(route_name).sum()),
                              "official_review_corridor_active_links": len(nearby),
                              "official_corridor_non_ramp_links": int(nearby.active_non_ramp.sum()),
                              "official_corridor_ramp_links": int(nearby.CONNECT.eq("1").sum()),
                              "sample_count": len(part),
                              "active_distance_median_m": float(part.distance_m.median()),
                              "active_distance_p95_m": float(part.distance_m.quantile(.95)),
                              "active_distance_max_m": float(part.distance_m.max()),
                              "approx_length_fraction_within_30m_active": float(np.average(part.distance_m.le(30), weights=weights)),
                              "approx_length_fraction_within_30m_non_ramp": float(np.average(part.non_ramp_distance_m.le(30), weights=weights)),
                              "approx_length_fraction_within_100m_non_ramp": float(np.average(part.non_ramp_distance_m.le(100), weights=weights)),
                              "approx_length_fraction_nearest_ramp": float(np.average(part.nearest_connect.eq("1"), weights=weights))})
    output = private / "spatial/official_nodelink_review_v1"
    if output.exists():
        raise FileExistsError("Review output exists; preserve existing evidence")
    output.mkdir(parents=True)
    pd.DataFrame(samples).to_csv(output / "provided_segment_samples.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(segment_records).to_csv(output / "provided_segment_comparison.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(route_records).to_csv(output / "route_comparison.csv", index=False, encoding="utf-8-sig")
    links.drop(columns="geometry").to_csv(output / "official_named_route_inventory.csv", index=False, encoding="utf-8-sig")
    corridor_links = gpd.GeoDataFrame(pd.concat(corridor_parts, ignore_index=True), crs=5179)
    corridor_links.to_file(output / "official_corridor_links.gpkg", layer="official_links", driver="GPKG")
    reread = gpd.read_file(output / "official_corridor_links.gpkg")
    if not reread.LINK_ID.equals(corridor_links.LINK_ID) or reread.crs.to_epsg() != 5179:
        raise AssertionError("Official geometry export roundtrip failed")
    if any(not a.equals_exact(b, 1e-8) for a, b in zip(reread.geometry, corridor_links.geometry)):
        raise AssertionError("Geometry changed during export")
    summary = {"status": "official_historical_geometry_review_not_final_segments",
               "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
               "source_publication_date": "2024-03-25", "archive_sha256": ARCHIVE_SHA,
               "source_crs_wkt": original_wkt, "analysis_crs": "EPSG:5179",
               "source_encoding_explicit": "CP949", "national_number_candidates": len(national),
               "national_named_route_links": len(links), "named_routes": ROUTES,
               "orientation_checks": links.orientation_check.value_counts().to_dict(),
               "analyst_qa_choices": {"sample_spacing_m": SAMPLE_SPACING_M,
                                      "node_tolerance_m": NODE_TOLERANCE_M,
                                      "orientation_margin_m": ORIENTATION_MARGIN_M,
                                      "review_corridor_m": CORRIDOR_M, "comparison_distances_m": [30, 100]},
               "routes": route_records, "geometry_roundtrip_verified": True,
               "protected_outcomes_used": False, "frozen_files_unchanged": len(frozen["files"]),
               "official_chainage_verified": False, "final_submission_use_rights_confirmed": False,
               "source_sha256": {"archive": ARCHIVE_SHA, "provided_scaffold": sha256_file(scaffold),
                                 "review_script": sha256_file(Path(__file__))},
               "output_sha256": {p.name: sha256_file(p) for p in output.iterdir() if p.is_file()},
               "limitations": [
                   "Review corridor is not an official administrative boundary or final scope.",
                   "Direction-separated ITS lines may be offset from physical carriageway centerlines.",
                   "Nearest links alone do not identify original fragment membership or direction; equal-distance ties are not resolved.",
                   "Length fractions approximate spaced samples; they are not exact line coverage fractions.",
                   "F_NODE/T_NODE direction is checked against source nodes, not destination labels or official kilometer posts.",
                   "Historical publication precedes first winter but does not prove every later road change is represented.",
                   "Website copyright policy is preserved; competition use and redistribution rights are not confirmed.",
                   "Provided geometry, 467 existing segments, frozen models, and submission draft are unchanged."]}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
