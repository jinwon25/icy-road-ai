"""수정본 목표안개 시정 입력과 동일 노선·과거 관측 가용성 감사."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive, sha256_file
from src.fog_features import load_fog, attach_fog, FOG_FEATURES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delay-minutes", type=int, default=0)
    parser.add_argument("--max-age-minutes", type=int, default=30)
    args = parser.parse_args()
    private = ROOT / "outputs/private"
    archive = competition_archive(ROOT)
    base = private / "ice_fallback_features/features.parquet"
    target = pd.read_parquet(base)
    inventory = pd.read_csv(private / "full/station_inventory.csv", dtype=str)
    metadata = inventory.loc[inventory.kind.eq("RWIS"),
                             ["station_id", "routes", "latitudes", "longitudes"]].rename(
        columns={"station_id": "station", "routes": "route", "latitudes": "lat", "longitudes": "lon"})
    metadata[["lat", "lon"]] = metadata[["lat", "lon"]].astype(float)
    fog = load_fog(archive)
    result = attach_fog(target, metadata, fog, args.max_age_minutes, args.delay_minutes)
    if len(result) != len(target):
        raise AssertionError("Target denominator changed")
    for field in target:
        pd.testing.assert_series_equal(result[field], target[field].reset_index(drop=True), check_dtype=False)
    rows = []
    for station, part in result.groupby("station"):
        rows.append({"station": station, "route": part.route.iloc[0].strip(), "rows": len(part),
                     "available_rows": int(part.fog_visibility_m.notna().sum()),
                     "ice_slots": int(part.ice.eq(1).sum()),
                     "ice_with_fog": int((part.ice.eq(1) & part.fog_visibility_m.notna()).sum()),
                     "source_station": part.fog_station.iloc[0],
                     "distance_km": part.fog_distance_km.iloc[0]})
    summary = {"status": "development_only_optional_fog_inputs", "archive_sha256": sha256_file(archive),
               "base_feature_sha256": sha256_file(base), "rows": len(result),
               "source_stations": sorted(fog.station.unique()), "model_features": FOG_FEATURES,
               "available_rows": int(result.fog_visibility_m.notna().sum()),
               "ice_with_fog": int((result.ice.eq(1) & result.fog_visibility_m.notna()).sum()),
               "delay_assumption_minutes": args.delay_minutes, "maximum_age_minutes": args.max_age_minutes,
               "limitations": ["Visibility in metres is not relative humidity or road temperature.",
                               "Nearest same-route fog observation; no cross-route fallback.",
                               "Honam has no fog station. All base rows and labels are preserved.",
                               "Observation timestamp does not establish actual publication latency.",
                               "Distance is retained; this does not establish local fog at the target."]}
    out = private / f"ice_fog_features_delay{args.delay_minutes}"
    out.mkdir(parents=True, exist_ok=True)
    result.to_parquet(out / "features.parquet", index=False, compression="zstd")
    pd.DataFrame(rows).to_csv(out / "station_coverage.csv", index=False, encoding="utf-8-sig")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
