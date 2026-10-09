"""Development-only RWIS analysis; the three official stations are never read into aggregates."""
from __future__ import annotations
import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive
from src.observation_io import daily_members, read_columns
from src.validation import PROTECTED_STATIONS, assert_training_stations, canonical_station_id, normalize_state

OUT = ROOT / "outputs" / "private" / "development"
FIELDS = ["timestamp", "station_id", "station_name", "route", "state_raw",
          "road_temp_raw", "humidity_raw", "rain_cum_raw", "air_temp_raw"]


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    totals = defaultdict(lambda: defaultdict(int))
    months = defaultdict(lambda: defaultdict(int))
    ice_times = defaultdict(list)
    differences = defaultdict(list)
    archive = competition_archive(ROOT)
    with zipfile.ZipFile(archive) as z:
        names = daily_members(z, "RWIS")
        for n in names:
            data = read_columns(z, n, ["관측시각 (KST)", "관측 지점번호", "관측 지점명", "고속도로", "노면상태",
                                       "노면온도 (광학)", "습도 (%)", "일 누적 강수량 (mm)", "기온 (C)"], FIELDS)
            data["station_id"] = data["station_id"].map(canonical_station_id)
            data = data.loc[~data.station_id.isin(PROTECTED_STATIONS) & data.station_id.ne("<missing>")].copy()
            assert_training_stations(data.station_id.unique())
            data["state"] = data.state_raw.map(normalize_state)
            data["timestamp"] = pd.to_datetime(data.timestamp, errors="coerce")
            for field in ("road_temp", "air_temp", "humidity", "rain_cum"):
                data[field] = pd.to_numeric(data[field + "_raw"], errors="coerce")
            valid_road = data.road_temp.between(-60, 70)
            valid_air = data.air_temp.between(-60, 70)
            valid_rh = data.humidity.between(0, 100)
            valid_rain = data.rain_cum.ge(0)
            data["ice"] = data.state.eq(1)
            for station, group in data.groupby("station_id", sort=False):
                row = totals[station]
                row["rows"] += len(group)
                row["valid_label"] += int(group.state.notna().sum())
                row["ice_slots"] += int(group.ice.sum())
                row["undefined_label"] += int(group.state.isna().sum())
                row["code_13"] += int(group.state_raw.isin(("13", "13.0")).sum())
                row["code_15"] += int(group.state_raw.isin(("15", "15.0")).sum())
                row["valid_road_temp"] += int(valid_road.loc[group.index].sum())
                row["valid_air_temp"] += int(valid_air.loc[group.index].sum())
                row["valid_humidity"] += int(valid_rh.loc[group.index].sum())
                row["valid_rain_cum"] += int(valid_rain.loc[group.index].sum())
                row["bad_road_temp"] += int((~valid_road.loc[group.index]).sum())
                row["bad_air_temp"] += int((~valid_air.loc[group.index]).sum())
                row["road_temp_neg999"] += int(group.road_temp.eq(-999).sum())
                row["air_temp_neg999"] += int(group.air_temp.eq(-999).sum())
                row["route"] = group.route.mode().iloc[0]
                row["name"] = group.station_name.mode().iloc[0]
                ice_times[station].extend(group.loc[group.ice, "timestamp"].dropna().tolist())
                pair = valid_road.loc[group.index] & valid_air.loc[group.index] & group.state.notna()
                diffs = (group.loc[pair, "road_temp"] - group.loc[pair, "air_temp"])
                differences["all"].extend(diffs.tolist())
                differences["ice"].extend(diffs[group.loc[pair, "ice"]].tolist())
                differences["non_ice"].extend(diffs[~group.loc[pair, "ice"]].tolist())
            for month, group in data.groupby(data.timestamp.dt.strftime("%Y-%m"), sort=False):
                row = months[month]
                row["rows"] += len(group)
                row["valid_label"] += int(group.state.notna().sum())
                row["ice_slots"] += int(group.ice.sum())
    stations = []
    all_event_lengths = []
    for station, row in sorted(totals.items()):
        times = sorted(ice_times[station])
        lengths = []
        for index, time in enumerate(times):
            if index == 0 or (time - times[index - 1]).total_seconds() != 600:
                lengths.append(1)
            else:
                lengths[-1] += 1
        all_event_lengths.extend(lengths)
        stations.append({"station_id": station, **row, "ice_events": len(lengths),
                         "ice_minutes": 10 * row["ice_slots"],
                         "max_event_minutes": 10 * max(lengths, default=0),
                         "single_slot_events": sum(length == 1 for length in lengths),
                         "ice_rate_valid": row["ice_slots"] / row["valid_label"] if row["valid_label"] else None})
    pd.DataFrame(stations).to_csv(OUT / "station_eda.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([{"month": m, **r} for m, r in sorted(months.items())]).to_csv(
        OUT / "monthly_eda.csv", index=False, encoding="utf-8-sig")
    diff_summary = {}
    for name, values in differences.items():
        a = np.asarray(values, dtype=float)
        diff_summary[name] = {"n": len(a), "median_c": float(np.median(a)) if len(a) else None,
                              "q10_c": float(np.quantile(a, 0.1)) if len(a) else None,
                              "q90_c": float(np.quantile(a, 0.9)) if len(a) else None}
    summary = {"stations": len(stations), "rows": sum(r["rows"] for r in stations),
               "valid_label": sum(r["valid_label"] for r in stations),
               "ice_slots": sum(r["ice_slots"] for r in stations),
               "ice_events": sum(r["ice_events"] for r in stations),
               "positive_stations": sum(r["ice_slots"] > 0 for r in stations),
               "single_slot_events": sum(length == 1 for length in all_event_lengths),
               "max_event_minutes": 10 * max(all_event_lengths, default=0),
               "median_event_minutes": float(10 * np.median(all_event_lengths)) if all_event_lengths else None,
               "temperature_difference": diff_summary}
    (OUT / "eda_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    run()
