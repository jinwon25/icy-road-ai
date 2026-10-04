"""Compare duplicate AWS midnight rows without changing the source archive."""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive
from src.validation import canonical_station_id


def canonical_value(value: str) -> tuple[str, object]:
    value = value.strip()
    try:
        number = Decimal(value)
    except InvalidOperation:
        return ("text", value)
    if number.is_finite():
        return ("number", number.normalize())
    return ("text", value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-files", type=int, default=None)
    args = parser.parse_args()
    archive_path = competition_archive(ROOT)
    counts = Counter()
    changed_columns = Counter()
    unmatched_dates = Counter()
    previous: dict[str, tuple[str, ...]] = {}
    columns: list[str] = []
    with zipfile.ZipFile(archive_path) as archive:
        names = sorted(n for n in archive.namelist() if "AWS_daily_" in n)
        if args.limit_files:
            names = names[:args.limit_files]
        for name in names:
            match = re.search(r"AWS_daily_(\d{8})", name)
            if not match:
                raise ValueError(f"Missing date token: {name}")
            day = datetime.strptime(match.group(1), "%Y%m%d")
            today = day.strftime("%Y-%m-%d 00:00:00")
            tomorrow = (day + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
            with archive.open(name) as stream:
                frame = pd.read_csv(stream, dtype=str, encoding="utf-8-sig", keep_default_na=False)
            columns = list(frame.columns)
            if len(columns) != 21:
                raise ValueError(f"Unexpected AWS column count in {name}: {len(columns)}")
            boundaries = frame.loc[frame.iloc[:, 0].isin((today, tomorrow))]
            current: dict[str, tuple[str, ...]] = {}
            following: dict[str, tuple[str, ...]] = {}
            for values in boundaries.itertuples(index=False, name=None):
                station = canonical_station_id(values[1])
                if station == "<missing>":
                    continue
                destination = current if values[0] == today else following
                if station in destination:
                    counts["within_file_duplicate_boundary_key"] += 1
                destination[station] = tuple(values)
            for station, before in previous.items():
                after = current.get(station)
                if after is None or before[0] != after[0]:
                    counts["unmatched_previous_midnight"] += 1
                    unmatched_dates[before[0][:10]] += 1
                    continue
                counts["matched"] += 1
                if before == after:
                    counts["raw_identical"] += 1
                different = [i for i in range(2, 21)
                             if canonical_value(before[i]) != canonical_value(after[i])]
                if not different:
                    counts["equivalent_after_numeric_normalization"] += 1
                else:
                    for index in different:
                        changed_columns[columns[index]] += 1
                    if any(index < 5 for index in different):
                        counts["metadata_conflict"] += 1
                    if any(index >= 5 for index in different):
                        counts["measurement_conflict"] += 1
                    if any((before[index] == "") != (after[index] == "") for index in different):
                        counts["one_side_empty"] += 1
            previous = following
            counts["files"] += 1
    counts["unmatched_previous_midnight"] += len(previous)
    for before in previous.values():
        unmatched_dates[before[0][:10]] += 1
    report = {"comparison": "same station and midnight in adjacent AWS files; numeric strings compare by Decimal",
              "counts": dict(counts), "unmatched_midnight_dates": dict(unmatched_dates),
              "changed_columns": dict(changed_columns),
              "policy": "no duplicate value selected or overwritten by this audit"}
    out = ROOT / "outputs" / "private" / ("smoke" if args.limit_files else "full")
    out.mkdir(parents=True, exist_ok=True)
    (out / "aws_boundary_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
