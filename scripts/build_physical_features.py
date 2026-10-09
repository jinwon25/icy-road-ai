"""과거 ASOS 복사·운량·적설과 AWS 냉각·수분 이력을 결합한다."""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive, sha256_file
from src.observation_io import daily_members, read_columns
from src.validation import assert_training_stations, canonical_station_id
from src.weather_features import _numeric_range
from scripts.baseline_ice_logistic import add_time_features, FEATURES
from scripts.audit_ice_weather_history import HISTORY

ASOS_FIELDS = {"강수량(mm)": ("asos_rain_mm", 0, 500), "전운량(10분위)": ("asos_cloud_tenths", 0, 10),
               "일사(MJ/m2)": ("asos_solar_mj_m2", 0, 10), "적설(cm)": ("asos_snow_cm", 0, 500),
               "지면온도(°C)": ("asos_ground_temp", -60, 70), "습도(%)": ("asos_humidity", 0, 100)}


def main():
    private = ROOT / "outputs/private"
    base_path = private / "ice_fallback_features/features.parquet"
    data = add_time_features(pd.read_parquet(base_path))
    assert_training_stations(data.station.unique())
    history = pd.read_parquet(private / "ice_weather_history/features.parquet")
    data = data.merge(history[["station", "time", *HISTORY]], on=["station", "time"], how="left", validate="one_to_one")
    archive_path = competition_archive(ROOT)
    with zipfile.ZipFile(archive_path) as archive:
        frames = [read_columns(archive, name, ["시간", "지점", *ASOS_FIELDS],
                               ["source_time", "asos_station", *[v[0] for v in ASOS_FIELDS.values()]])
                  for name in daily_members(archive, "ASOS")]
    asos = pd.concat(frames, ignore_index=True)
    asos["source_time"] = pd.to_datetime(asos.source_time, errors="raise")
    asos["asos_station"] = asos.asos_station.map(canonical_station_id)
    for name, low, high in ASOS_FIELDS.values():
        _numeric_range(asos, name, low, high)
    if asos.duplicated(["asos_station", "source_time"]).any():
        raise ValueError("Duplicate ASOS source")
    data = data.merge(asos, how="left", left_on=["asos_station", "asos_source_time"],
                      right_on=["asos_station", "source_time"], validate="many_to_one")
    good = data.source_time.notna()
    if not (data.loc[good, "source_time"] < data.loc[good, "time"]).all():
        raise AssertionError("ASOS source is not strictly prior")
    metadata = pd.read_csv(private / "sensor_availability/metadata.csv", dtype={"station": str})
    metadata = metadata.loc[metadata.kind.eq("RWIS"), ["station", "elevation_m"]]
    data = data.merge(metadata, on="station", how="left", validate="many_to_one")
    data["air_dewpoint_gap"] = data.aws_air_temp - data.aws_dewpoint
    data["air_asos_gap"] = data.aws_air_temp - data.asos_air_temp
    data["ground_air_gap"] = data.asos_ground_temp - data.aws_air_temp
    physical = [*HISTORY, *[v[0] for v in ASOS_FIELDS.values()], "elevation_m",
                "air_dewpoint_gap", "air_asos_gap", "ground_air_gap"]
    reference = pd.read_parquet(base_path)
    pd.testing.assert_frame_equal(data[["station", "time", "ice"]], reference[["station", "time", "ice"]])
    out = private / "physical_features"
    out.mkdir(parents=True, exist_ok=True)
    data.to_parquet(out / "features.parquet", index=False, compression="zstd")
    summary = {"status": "development_physical_weather_inputs", "archive_sha256": sha256_file(archive_path),
               "base_feature_sha256": sha256_file(base_path), "rows": len(data),
               "base_features": FEATURES, "additional_features": physical,
               "nonmissing": {name: int(data[name].notna().sum()) for name in physical},
               "semantics": ["ASOS radiation retains MJ/m2; it is not silently treated as W/m2.",
                             "ASOS ground temperature is not RWIS road temperature.",
                             "AWS overlapping 15-minute rainfall is never summed as rainfall volume.",
                             "Absent precipitation/snow/radiation values remain missing, not zero.",
                             "Target height is supplied static elevation, not a lapse-rate correction.",
                             "Neighbor thermal inputs are built separately with fold-wide exclusion."]}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
