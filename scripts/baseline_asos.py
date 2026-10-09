"""Leakage-safe preliminary road-temperature baseline from past ASOS readings."""
from __future__ import annotations
import argparse
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive
from src.observation_io import daily_members, read_columns
from src.validation import (PROTECTED_STATIONS, assert_training_stations,
                            canonical_station_id, regression_metrics)


def haversine_km(lat1, lon1, lat2, lon2):
    a, b, c, d = map(np.radians, (lat1, lon1, lat2, lon2))
    hav = np.sin((c - a) / 2) ** 2 + np.cos(a) * np.cos(c) * np.sin((d - b) / 2) ** 2
    return float(6371.0088 * 2 * np.arcsin(np.sqrt(hav)))


def read_data(zip_path, kind, columns, names, limit_days):
    frames = []
    with zipfile.ZipFile(zip_path) as archive:
        files = daily_members(archive, kind)
        if limit_days:
            files = files[:limit_days]
        for name in files:
            frame = read_columns(archive, name, columns, names)
            if kind == "RWIS":
                frame["station"] = frame.station.map(canonical_station_id)
                frame = frame.loc[~frame.station.isin(PROTECTED_STATIONS)
                                  & frame.station.ne("<missing>")].copy()
            frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-days", type=int)
    args = parser.parse_args()
    archive = competition_archive(ROOT)
    asos = read_data(archive, "ASOS", ["시간", "지점", "지점명", "위도", "경도", "기온(°C)"],
                     ["time", "station", "name", "lat", "lon", "air_temp"], args.limit_days)
    rwis = read_data(archive, "RWIS", ["관측시각 (KST)", "관측 지점번호", "관측 지점명", "고속도로", "관측소 위도", "관측소 경도", "노면온도 (광학)"],
                     ["time", "station", "name", "route", "lat", "lon", "road_temp"], args.limit_days)
    rwis["station"] = rwis.station.map(canonical_station_id)
    rwis = rwis.loc[~rwis.station.isin(PROTECTED_STATIONS) & rwis.station.ne("<missing>")].copy()
    assert_training_stations(rwis.station.unique())
    asos["station"] = asos.station.map(canonical_station_id)
    for frame in (asos, rwis):
        frame["time"] = pd.to_datetime(frame.time, errors="coerce")
        frame["lat"] = pd.to_numeric(frame.lat, errors="coerce")
        frame["lon"] = pd.to_numeric(frame.lon, errors="coerce")
    asos["air_temp"] = pd.to_numeric(asos.air_temp, errors="coerce")
    rwis["road_temp"] = pd.to_numeric(rwis.road_temp, errors="coerce")
    asos = asos.loc[asos.air_temp.between(-60, 70) & asos.time.notna()].copy()
    rwis = rwis.loc[rwis.road_temp.between(-60, 70) & rwis.time.notna()].copy()
    acoords = asos.groupby("station")[["lat", "lon"]].first()
    rcoords = rwis.groupby("station")[["lat", "lon"]].first()
    prediction_frames = []
    mapping = []
    for station, (lat, lon) in rcoords.iterrows():
        candidates = sorted([(haversine_km(lat, lon, row.lat, row.lon), sid)
                             for sid, row in acoords.iterrows()])
        distance, nearest = candidates[0]
        left = rwis.loc[rwis.station.eq(station), ["station", "time", "road_temp"]].sort_values("time")
        right = asos.loc[asos.station.eq(nearest), ["time", "air_temp"]].sort_values("time").rename(columns={"time": "source_time"})
        joined = pd.merge_asof(left, right, left_on="time", right_on="source_time",
                               direction="backward", allow_exact_matches=False,
                               tolerance=pd.Timedelta(hours=1))
        joined["distance_km"] = distance
        joined["asos_station"] = nearest
        joined["age_minutes"] = (joined.time - joined.source_time).dt.total_seconds() / 60
        prediction_frames.append(joined)
        mapping.append({"rwis_station": station, "asos_station": nearest, "distance_km": distance})
    predictions = pd.concat(prediction_frames, ignore_index=True)
    if predictions.source_time.notna().any():
        assert (predictions.loc[predictions.source_time.notna(), "source_time"]
                < predictions.loc[predictions.source_time.notna(), "time"]).all()
        assert predictions.age_minutes.dropna().between(0, 60, inclusive="right").all()
    rows = []
    for station in sorted(predictions.station.unique()):
        heldout = predictions.loc[predictions.station.eq(station)]
        training = predictions.loc[~predictions.station.eq(station)].dropna(subset=["air_temp"])
        offset = float((training.road_temp - training.air_temp).median())
        direct = regression_metrics(heldout.road_temp, heldout.air_temp)
        adjusted = regression_metrics(heldout.road_temp, heldout.air_temp + offset)
        rows.append({"station": station, "n_total": len(heldout), "offset_from_training_c": offset,
                     "nearest_asos": heldout.asos_station.iloc[0],
                     "distance_km": heldout.distance_km.iloc[0],
                     "direct_n": direct["n"], "direct_bias": direct["bias"],
                     "direct_mae": direct["mae"], "direct_rmse": direct["rmse"],
                     "adjusted_n": adjusted["n"], "adjusted_bias": adjusted["bias"],
                     "adjusted_mae": adjusted["mae"], "adjusted_rmse": adjusted["rmse"]})
    offsets = {row["station"]: row["offset_from_training_c"] for row in rows}
    predictions["pred_direct"] = predictions.air_temp
    predictions["pred_adjusted_oof"] = predictions.air_temp + predictions.station.map(offsets)
    report = {"status": "preliminary_development_only",
              "description": "nearest ASOS air temperature strictly before target time, <=60 min old",
              "target": "RWIS optical road temperature, unit assumed C pending confirmation",
              "stations": len(rows),
              "direct_station_macro_bias": float(np.mean([r["direct_bias"] for r in rows if r["direct_bias"] is not None])),
              "adjusted_station_macro_bias": float(np.mean([r["adjusted_bias"] for r in rows if r["adjusted_bias"] is not None])),
              "offset_worsened_stations": int(sum(r["adjusted_mae"] > r["direct_mae"] for r in rows)),
              "nearest_distance_km_range": [float(min(r["distance_km"] for r in rows)),
                                            float(max(r["distance_km"] for r in rows))],
              "direct_station_macro_mae": float(np.mean([r["direct_mae"] for r in rows if r["direct_mae"] is not None])),
              "adjusted_station_macro_mae": float(np.mean([r["adjusted_mae"] for r in rows if r["adjusted_mae"] is not None])),
              "direct_station_macro_rmse": float(np.mean([r["direct_rmse"] for r in rows if r["direct_rmse"] is not None])),
              "adjusted_station_macro_rmse": float(np.mean([r["adjusted_rmse"] for r in rows if r["adjusted_rmse"] is not None])),
              "total_valid_pairs": int(sum(r["direct_n"] for r in rows)),
              "total_targets": int(sum(r["n_total"] for r in rows))}
    report["coverage"] = report["total_valid_pairs"] / report["total_targets"]
    out = ROOT / "outputs" / "private" / ("smoke" if args.limit_days else "baseline")
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out / "station_metrics.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(mapping).to_csv(out / "nearest_asos.csv", index=False, encoding="utf-8-sig")
    predictions.to_csv(out / "predictions.csv", index=False, encoding="utf-8-sig")
    (out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
