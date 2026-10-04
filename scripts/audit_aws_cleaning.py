"""Run the nominal-day AWS input filter and record row accounting."""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive
from src.weather_inputs import filter_aws_nominal_day


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-files", type=int, default=None)
    args = parser.parse_args()
    total = Counter()
    archive_path = competition_archive(ROOT)
    with zipfile.ZipFile(archive_path) as archive:
        names = sorted(n for n in archive.namelist() if "AWS_daily_" in n)
        if args.limit_files:
            names = names[:args.limit_files]
        for name in names:
            match = re.search(r"AWS_daily_(\d{8})", name)
            if not match:
                raise ValueError(f"Missing AWS date token: {name}")
            nominal_day = datetime.strptime(match.group(1), "%Y%m%d").date()
            with archive.open(name) as stream:
                frame = pd.read_csv(stream, dtype=str, encoding="utf-8-sig", keep_default_na=False)
            _, counts = filter_aws_nominal_day(frame, nominal_day)
            total.update(counts)
            total["files"] += 1
    report = {"source": "AWS daily files in supplied ZIP", "timezone": "KST (source header)",
              "counts": dict(total),
              "rule": "keep valid-station rows whose timestamp date equals the source filename date; no value imputation"}
    out = ROOT / "outputs" / "private" / ("smoke" if args.limit_files else "full")
    out.mkdir(parents=True, exist_ok=True)
    (out / "aws_cleaning_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
