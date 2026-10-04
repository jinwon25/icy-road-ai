"""Build private 10-minute Ice targets with prior-only ASOS/AWS inputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive
from src.ice_features import build_ice_features
from src.validation import PROTECTED_STATIONS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit-days", type=int, default=None)
    args = parser.parse_args()
    archive = competition_archive(ROOT)
    data = build_ice_features(archive, args.limit_days)
    if set(data.station.astype(str)) & PROTECTED_STATIONS:
        raise AssertionError("Protected RWIS entered Ice features")
    for prefix in ("aws", "asos"):
        valid = data[f"{prefix}_source_time"].notna()
        if not (data.loc[valid, f"{prefix}_source_time"]
                < data.loc[valid, "time"]).all():
            raise AssertionError(f"Current or future {prefix} source")
    summary = {"status": "development_ice_features_only",
               "limit_days_per_winter": args.limit_days,
               "stations": int(data.station.nunique()), "target_slots": len(data),
               "valid_labels": int(data.ice.notna().sum()),
               "ice_slots": int(data.ice.eq(1).sum()),
               "undefined_labels": int(data.ice.isna().sum()),
               "prior_aws_temp_slots": int(data.aws_air_temp.notna().sum()),
               "prior_asos_temp_slots": int(data.asos_air_temp.notna().sum())}
    if args.limit_days is None:
        expected = json.loads((ROOT / "outputs" / "private" / "development" /
                               "eda_summary.json").read_text(encoding="utf-8"))
        if (summary["target_slots"] != expected["rows"]
                or summary["valid_labels"] != expected["valid_label"]
                or summary["ice_slots"] != expected["ice_slots"]):
            raise AssertionError("Ice targets differ from audited development EDA")
    out = ROOT / "outputs" / "private" / ("smoke_ice_features" if args.limit_days else "ice_features")
    out.mkdir(parents=True, exist_ok=True)
    data.to_parquet(out / "features.parquet", index=False, compression="zstd")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(json.dumps({"output": str(out), **summary}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
