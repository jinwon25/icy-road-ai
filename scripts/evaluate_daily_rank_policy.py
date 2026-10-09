"""고정 열·수분 모델의 사후 일별 경보 개수 정책을 내부 점수에서만 선택한다."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.daily_rank_policy import capped_daily_scores
from src.ice_daily_selection import choose_daily_threshold
from src.validation import binary_metrics, daily_scores, macro_scores, assert_training_stations
from src.data_source import sha256_file
from scripts.evaluate_physical_ice import threshold_grid


def main():
    private = ROOT / "outputs/private"
    config_path = ROOT / "config/daily_rank_experiment.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    source = private / config["source"]
    out = private / "daily_rank_policy"
    out.mkdir(parents=True, exist_ok=True)
    outer = pd.read_parquet(source / "predictions.parquet")
    assert_training_stations(outer.station.unique())
    name = config["candidate"]
    rows, frames = [], []
    for station, part in outer.groupby("station"):
        inner = pd.read_parquet(source / station / "inner_oof.parquet")
        if station in set(inner.station):
            raise AssertionError("Outer station in policy selection")
        scores = inner[f"score_{name}"].to_numpy()
        grid = threshold_grid(scores)
        choices = []
        for cap in config["caps"]:
            reduced = capped_daily_scores(inner, scores, cap)
            threshold, value, trace = choose_daily_threshold(inner, reduced, grid)
            alarms = int((reduced >= threshold).sum())
            choices.append({"station": station, "cap": cap, "threshold": threshold, "inner_daily_f1": value, "inner_alarm_slots": alarms})
        selected = sorted(choices, key=lambda r: (-r["inner_daily_f1"], r["inner_alarm_slots"], r["cap"]))[0]
        result = part[["station", "time", "ice", f"pred_daily_{name}"]].copy()
        reduced = capped_daily_scores(part, part[f"score_{name}"], selected["cap"])
        result["pred_daily_cap"] = (reduced >= selected["threshold"]).astype(int)
        result["selected_cap"] = selected["cap"]
        rows.extend([{**r, "selected": r is selected} for r in choices])
        frames.append(result)
        print(station, json.dumps(selected), flush=True)
    result = pd.concat(frames, ignore_index=True)
    metrics, all_days = {}, []
    for variant, col in [("thermal_daily", f"pred_daily_{name}"), ("retrospective_daily_cap", "pred_daily_cap")]:
        valid = result.loc[result.ice.notna()]
        records = [(r.station, r.time, int(r.ice) if pd.notna(r.ice) else None, int(getattr(r, col))) for r in result.itertuples()]
        daily = daily_scores(records, minimum_coverage=1.)
        days = pd.DataFrame(daily)
        accepted = days.loc[days.accepted]
        fixed = accepted.loc[(accepted.tp + accepted.fn).gt(0)]
        metrics[variant] = {"slot_micro": binary_metrics(valid.ice.astype(int), valid[col]), "daily_station_macro": macro_scores(daily),
                            "fixed_ice_day_f1": float(fixed.groupby("station").f1.mean().mean()),
                            "false_alarm_nonice_days": int(accepted.loc[(accepted.tp + accepted.fn).eq(0), "fp"].gt(0).sum())}
        days["variant"] = variant
        all_days.append(days)
    result.to_parquet(out / "predictions.parquet", index=False, compression="zstd")
    pd.DataFrame(rows).to_csv(out / "selection.csv", index=False, encoding="utf-8-sig")
    pd.concat(all_days).to_csv(out / "daily_metrics.csv", index=False, encoding="utf-8-sig")
    summary = {"status": "retrospective_policy_development_only", "rows": len(result), "metrics": metrics, "config": config,
               "source_signature": json.loads((source / "input_signature.json").read_text(encoding="utf-8")),
               "policy_code_sha256": sha256_file(ROOT / "src/daily_rank_policy.py"), "config_sha256": sha256_file(config_path)}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics), flush=True)


if __name__ == "__main__":
    main()
