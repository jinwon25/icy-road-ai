"""Check source-file dates, placeholder rows, and midnight overlap."""
from __future__ import annotations
import json
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive
from src.observation_io import daily_members
from src.validation import canonical_station_id
OUT = ROOT / "outputs" / "private" / "full"


def main():
    archive = competition_archive(ROOT)
    records = []
    overlaps = defaultdict(lambda: defaultdict(int))
    with zipfile.ZipFile(archive) as z:
        for kind in ("RWIS", "ASOS", "AWS"):
            names = daily_members(z, kind)
            previous_boundary = {}
            for name in names:
                date_token = re.search(r"daily_(\d{4}-?\d{2}-?\d{2})", name).group(1)
                day = pd.Timestamp(date_token.replace("-", ""))
                with z.open(name) as stream:
                    frame = pd.read_csv(stream, dtype=str, encoding="utf-8-sig", keep_default_na=False)
                timestamp = pd.to_datetime(frame.iloc[:, 1 if kind == "ASOS" else 0], errors="coerce", format="mixed")
                station = frame.iloc[:, 1 if kind != "ASOS" else 2].map(canonical_station_id)
                no_id = station.eq("<missing>")
                all_empty = frame.iloc[:, 1:].eq("").all(axis=1)
                same_day = timestamp.dt.normalize().eq(day)
                next_midnight = timestamp.eq(day + pd.Timedelta(days=1))
                other_day = timestamp.notna() & ~same_day & ~next_midnight
                decimal_id = frame.iloc[:, 1 if kind != "ASOS" else 2].str.match(r"^\d+\.0$")
                valid = ~no_id & timestamp.notna()
                now = {}
                for index in frame.index[valid & timestamp.eq(day)]:
                    key = (station[index], timestamp[index])
                    now[key] = tuple(frame.iloc[index].astype(str))
                for key, raw in previous_boundary.items():
                    if key in now:
                        overlaps[kind]["matched"] += 1
                        overlaps[kind]["identical"] += int(raw == now[key])
                        overlaps[kind]["conflicting"] += int(raw != now[key])
                    else:
                        overlaps[kind]["unmatched"] += 1
                previous_boundary = {}
                for index in frame.index[valid & next_midnight]:
                    key = (station[index], timestamp[index])
                    previous_boundary[key] = tuple(frame.iloc[index].astype(str))
                records.append({"kind": kind, "file": Path(name).name, "rows": len(frame),
                    "missing_id_rows": int(no_id.sum()),
                    "empty_placeholder_rows": int((no_id & all_empty).sum()),
                    "decimal_id_rows": int(decimal_id.sum()),
                    "same_day_rows": int(same_day.sum()),
                    "next_midnight_rows": int(next_midnight.sum()),
                    "other_date_rows": int(other_day.sum()),
                    "invalid_timestamp_rows": int(timestamp.isna().sum()),
                    "other_date_with_id": int((other_day & ~no_id).sum())})
            overlaps[kind]["unmatched"] += len(previous_boundary)
    summary = {}
    for kind in ("RWIS", "ASOS", "AWS"):
        part = [r for r in records if r["kind"] == kind]
        summary[kind] = {key: sum(r[key] for r in part) for key in part[0] if key not in ("kind", "file")}
        summary[kind]["cross_file_midnight"] = dict(overlaps[kind])
    pd.DataFrame(records).to_csv(OUT / "timestamp_quality.csv", index=False, encoding="utf-8-sig")
    (OUT / "timestamp_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
