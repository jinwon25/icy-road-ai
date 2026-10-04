"""Check neighbor-RWIS benchmark by winter and route on fixed paired rows."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validation import PROTECTED_STATIONS, regression_metrics

PRIVATE = ROOT / "outputs" / "private"
PERIODS = {
    "winter_2024_25": (pd.Timestamp("2024-11-01"), pd.Timestamp("2025-03-01")),
    "winter_2025_26": (pd.Timestamp("2025-11-01"), pd.Timestamp("2026-03-01")),
}


def main() -> None:
    data = pd.read_parquet(PRIVATE / "neighbor_rwis" / "predictions.parquet")
    data["station"] = data.station.astype(str)
    if set(data.station) & PROTECTED_STATIONS:
        raise AssertionError("Protected RWIS entered neighbor diagnostic")
    data = data.loc[data.neighbor_road_temp.notna()].copy()
    age = (data.time - data.neighbor_source_time).dt.total_seconds() / 60
    if not age.between(0, 30, inclusive="right").all():
        raise AssertionError("Neighbor observation was not strictly prior within 30 min")
    inventory = pd.read_csv(PRIVATE / "full" / "station_inventory.csv", dtype=str,
                            encoding="utf-8-sig")
    routes = inventory.loc[inventory.kind.eq("RWIS") & inventory.protected.eq("False")
                           & inventory.station_id.ne("<missing>")].set_index("station_id").routes
    rows = []
    for period, (start, end) in PERIODS.items():
        part = data.loc[data.time.ge(start) & data.time.lt(end)]
        if part.empty:
            raise ValueError(f"Empty winter: {period}")
        for station, group in part.groupby("station", sort=True):
            record = {"period": period, "station": station, "route": routes[station],
                      "n": len(group)}
            for name, column in (("weather", "pred_weather_ridge"),
                                 ("neighbor", "neighbor_road_temp"),
                                 ("equal_blend", "pred_equal_blend")):
                metrics = regression_metrics(group.road_temp, group[column])
                record.update({f"{name}_{key}": metrics[key] for key in ("bias", "mae", "rmse")})
            rows.append(record)
    table = pd.DataFrame(rows)
    if len(table) != 28 or int(table.n.sum()) != len(data):
        raise AssertionError("Winter split does not cover 14 stations and all paired rows")
    winter = {}
    for period, part in table.groupby("period"):
        winter[period] = {"paired_rows": int(part.n.sum()), "stations": len(part),
                          "weather_macro_mae": float(part.weather_mae.mean()),
                          "neighbor_macro_mae": float(part.neighbor_mae.mean()),
                          "equal_blend_macro_mae": float(part.equal_blend_mae.mean()),
                          "stations_blend_better_than_weather": int(part.equal_blend_mae.lt(part.weather_mae).sum())}
    route = {str(name): {"stations": int(part.station.nunique()),
                         "weather_macro_mae": float(part.weather_mae.mean()),
                         "neighbor_macro_mae": float(part.neighbor_mae.mean()),
                         "equal_blend_macro_mae": float(part.equal_blend_mae.mean())}
             for name, part in table.groupby("route")}
    summary = {"status": "development_neighbor_rwis_winter_diagnostic",
               "paired_rows": len(data), "age_minutes_counts": {str(int(k)): int(v)
                                                              for k, v in age.value_counts().sort_index().items()},
               "winters": winter, "routes": route,
               "limitation": "Both winters share the same spatial LOSO weather-model fits; this is a stratified diagnostic, not winter-forward validation."}
    out = PRIVATE / "neighbor_rwis"
    table.to_csv(out / "winter_station_metrics.csv", index=False, encoding="utf-8-sig")
    (out / "diagnostic_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                                 encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
