"""공식 CCTV 이정과 ROADPLUS 좌표로 연구 참조를 교차 점검한다."""
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file

ROUTES = {"서해안선": "서해안고속국도", "호남선": "호남고속국도",
          "통영대전선": "통영-대전고속국도"}


def main():
    private = ROOT / "outputs/private"
    source = private / "external/official_cctv_anchors"
    cctv = pd.read_csv(source / "kec_cctv_20260423.csv", encoding="cp949")
    raw = json.loads((source / "roadplus_EX_CCTV.geojson").read_text(encoding="utf-8"))
    points = pd.DataFrame([{"name": f["properties"]["cctvname"],
                            "cctv_id": f["properties"]["cctvid"],
                            "lon": f["geometry"]["coordinates"][0],
                            "lat": f["geometry"]["coordinates"][1]}
                           for f in raw["features"]])
    # 이름만으로 다른 도로의 같은 명칭을 고를 수 없다. 양쪽에서 유일한 명칭만 허용한다.
    catalog_counts = cctv.groupby("CCTV명").size()
    point_counts = points.groupby("name").size()
    selected = cctv.loc[cctv["노선명"].isin(ROUTES)].copy()
    selected["catalog_name_count"] = selected["CCTV명"].map(catalog_counts)
    selected["coordinate_name_count"] = selected["CCTV명"].map(point_counts).fillna(0).astype(int)
    selected["join_status"] = np.select(
        [selected.coordinate_name_count.eq(0), selected.catalog_name_count.ne(1),
         selected.coordinate_name_count.ne(1)],
        ["no_exact_name_match", "ambiguous_catalog_name", "ambiguous_coordinate_name"],
        default="unique_exact_name_candidate")
    joined = selected.loc[selected.join_status.eq("unique_exact_name_candidate")].merge(
        points.loc[points.name.map(point_counts).eq(1)],
        left_on="CCTV명", right_on="name", validate="one_to_one")
    edges = gpd.read_file(private / "spatial/chainage_reference/research_reference.gpkg")
    anchors = gpd.GeoDataFrame(joined, geometry=[Point(x, y) for x, y in zip(joined.lon, joined.lat)],
                               crs=4326).to_crs(edges.crs)
    records = []
    for label, route in ROUTES.items():
        pool = edges.loc[edges.route.eq(route)].reset_index(drop=True)
        tree = STRtree(pool.geometry.to_numpy())
        for _, row in anchors.loc[anchors["노선명"].eq(label)].iterrows():
            index = int(tree.nearest(row.geometry))
            edge = pool.iloc[index]
            km = edge.km0_candidate + edge.geometry.project(row.geometry, normalized=True) * (
                edge.km1_candidate - edge.km0_candidate)
            distance = row.geometry.distance(edge.geometry)
            error = (km - float(row["이정"])) * 1000
            # 이는 분석자 QA 기준이다. 공식 허용오차 또는 역사적 선형 검증으로 해석하지 않는다.
            records.append({"route": route, "catalog_route_number": int(row["노선번호"]),
                            "cctv_name": row["CCTV명"], "cctv_id": row.cctv_id,
                            "official_chainage_km": float(row["이정"]), "official_camera_direction": row["방향"],
                            "longitude": row.lon, "latitude": row.lat,
                            "reference_chainage_km_candidate": float(km),
                            "reference_distance_m": float(distance), "chainage_error_m": float(error),
                            "passes_anchor_qa": bool(distance <= 100 and abs(error) <= 100),
                            "segment_direction_verified": False})
    out = private / "spatial/official_chainage_anchors"
    out.mkdir(parents=True, exist_ok=True)
    selected.drop(columns="geometry", errors="ignore").to_csv(out / "catalog_join_review.csv", index=False, encoding="utf-8-sig")
    result = pd.DataFrame(records)
    result.to_csv(out / "anchor_comparison.csv", index=False, encoding="utf-8-sig")
    segments = pd.read_csv(private / "spatial/chainage_reference/segment_chainage_candidates.csv")
    scoped = []
    for route, part in result.groupby("route"):
        bounds = segments.loc[segments.route.eq(route)]
        pool = part.loc[part.official_chainage_km.between(bounds.km_min_candidate.min(), bounds.km_max_candidate.max())]
        close = pool.loc[pool.reference_distance_m.le(100)]
        scoped.append({"route": route, "anchors_in_candidate_span": len(pool),
                       "anchors_within_100m": len(close), "passes": int(pool.passes_anchor_qa.sum()),
                       "median_abs_error_m_for_close_anchors": float(close.chainage_error_m.abs().median()),
                       "max_abs_error_m_for_close_anchors": float(close.chainage_error_m.abs().max())})
    summary = {
        "status": "official_point_cross_check_not_full_segment_alignment",
        "catalog_rows_in_scope": len(selected), "unique_exact_name_candidates": len(result),
        "join_status_counts": selected.join_status.value_counts().to_dict(),
        "passes_anchor_qa": int(result.passes_anchor_qa.sum()),
        "within_provided_segment_candidate_span": scoped,
        "per_route": {route: {
            "anchors": len(part), "passes": int(part.passes_anchor_qa.sum()),
            "median_abs_chainage_error_m": float(part.chainage_error_m.abs().median()),
            "p95_abs_chainage_error_m": float(part.chainage_error_m.abs().quantile(.95)),
            "max_abs_chainage_error_m": float(part.chainage_error_m.abs().max()),
            "median_reference_distance_m": float(part.reference_distance_m.median())
        } for route, part in result.groupby("route")},
        "thresholds_analyst_choice": {"max_distance_m": 100, "max_abs_chainage_error_m": 100},
        "source_sha256": {p.name: sha256_file(p) for p in source.glob("*") if p.is_file()},
        "limitations": [
            "Exact unique names are candidate joins; no shared official CCTV identifier in the CSV.",
            "2026 CCTV inventory and current map do not establish 2024/2025 historical alignment.",
            "Camera viewing direction is not proof of segment carriageway direction.",
            "Passing isolated anchors does not validate every research reference edge or 467 road fragments.",
            "ROADPLUS map redistribution licence remains unconfirmed; source and outputs remain private.",
            "Catalog route numbers are preserved as published, including inconsistent Honam numbering.",
        ],
        "official_full_geometry_verified": False,
        "protected_outcomes_used": False,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
