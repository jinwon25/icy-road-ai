"""Read the supplied ZIP in place; write only private audit summaries."""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_source import competition_archive
from src.validation import PROTECTED_STATIONS, canonical_station_id


ROOT = Path(__file__).resolve().parents[1]
FIELDS = {
    "RWIS": ("관측시각 (KST)", "관측 지점번호", "관측 지점명", "관측소 위도", "관측소 경도", "고속도로", 10),
    "ASOS": ("시간", "지점", "지점명", "위도", "경도", None, 60),
    "AWS": ("시간(KST)", "지점 번호", "지점명", "위도", "경도", None, 10),
}
MISSING_TOKENS = {"", "nan", "na", "null", "none", "#num!", "#n/a", "-"}
NONNUMERIC = {"노면상태", "운형(운형약어)", "현상번호(국내식)"}
STATE_CODES = {"01", "02", "03", "04", "10", "11", "12", "13", "14", "15"}


def decoded_name(info):
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp949")
    except (UnicodeError, UnicodeEncodeError):
        return info.filename


def read_csv(archive, info):
    with archive.open(info) as stream:
        first = stream.read(3)
    candidates = ["utf-8-sig", "cp949"] if first == b"\xef\xbb\xbf" else ["utf-8-sig", "cp949"]
    last = None
    for encoding in candidates:
        try:
            with archive.open(info) as stream:
                frame = pd.read_csv(stream, dtype=str, encoding=encoding, keep_default_na=False,
                                    low_memory=False)
            return frame, encoding, first == b"\xef\xbb\xbf"
        except (UnicodeError, pd.errors.ParserError) as exc:
            last = exc
    raise ValueError(f"Cannot parse {info.filename}: {last}")


def label_file(name):
    match = re.search(r"Jeonbuk_(RWIS|ASOS|AWS)_daily_", name)
    return match.group(1) if match else None


def summarize_station_rows(frame, kind, station_summary, prev_slot, interval_counts):
    time_col, id_col, name_col, lat_col, lon_col, route_col, interval = FIELDS[kind]
    dt = pd.to_datetime(frame[time_col], errors="coerce")
    ids = frame[id_col].map(canonical_station_id)
    for station, indices in ids.groupby(ids, sort=False).groups.items():
        subset = frame.loc[indices]
        times = dt.loc[indices]
        key = (kind, station)
        data = station_summary[key]
        data["rows"] += len(subset)
        data["invalid_time"] += int(times.isna().sum())
        data["duplicate_time_within_file"] += int(times.duplicated().sum())
        for col, destination in ((name_col, "names"), (lat_col, "latitudes"), (lon_col, "longitudes")):
            data[destination].update(subset[col].drop_duplicates().astype(str))
        if route_col:
            data["routes"].update(subset[route_col].drop_duplicates().astype(str))
        clean = times.dropna().sort_values()
        if len(clean):
            first, last = clean.iloc[0], clean.iloc[-1]
            data["first"] = min(data["first"], first) if data["first"] is not None else first
            data["last"] = max(data["last"], last) if data["last"] is not None else last
            if key in prev_slot:
                delta = int((first - prev_slot[key]).total_seconds() / 60)
                interval_counts[(kind, station)][delta] += 1
            for delta, count in clean.diff().dt.total_seconds().div(60).dropna().value_counts().items():
                interval_counts[(kind, station)][int(delta)] += int(count)
            prev_slot[key] = last


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-files", type=int, default=None)
    args = parser.parse_args()
    output = ROOT / "outputs" / "private" / ("smoke" if args.limit_files else "full")
    output.mkdir(parents=True, exist_ok=True)
    archive_path = competition_archive(ROOT)
    files = []
    column_stats = defaultdict(Counter)
    state_counts = Counter()
    station_summary = defaultdict(lambda: {"rows": 0, "invalid_time": 0,
                                           "duplicate_time_within_file": 0, "names": set(),
                                           "latitudes": set(), "longitudes": set(),
                                           "routes": set(), "first": None, "last": None})
    prev_slot = {}
    interval_counts = defaultdict(Counter)
    errors = []
    bridge_tunnel = {}
    with zipfile.ZipFile(archive_path) as archive:
        daily_infos = [i for i in archive.infolist() if label_file(i.filename)]
        if args.limit_files:
            daily_infos = [i for kind in FIELDS for i in [next(x for x in daily_infos if label_file(x.filename) == kind)]]
        for number, info in enumerate(daily_infos, 1):
            kind = label_file(info.filename)
            try:
                frame, encoding, bom = read_csv(archive, info)
                time_col, id_col, name_col, lat_col, lon_col, route_col, interval = FIELDS[kind]
                if any(col not in frame for col in (time_col, id_col, name_col, lat_col, lon_col)):
                    raise ValueError(f"Missing required columns: {frame.columns.tolist()}")
                summarize_station_rows(frame, kind, station_summary, prev_slot, interval_counts)
                development = frame if kind != "RWIS" else frame.loc[~frame[id_col].map(canonical_station_id).isin(PROTECTED_STATIONS)]
                if kind == "RWIS":
                    raw_state = development["노면상태"].astype(str).str.strip()
                    normalized = raw_state.where(raw_state.ne(""), "<blank>")
                    state_counts.update(normalized.value_counts().to_dict())
                static = {time_col, id_col, name_col, lat_col, lon_col, route_col, None, "", "Unnamed: 0"}
                for col in frame:
                    if col in static or col.startswith("Unnamed:"):
                        continue
                    values = development[col].astype(str).str.strip()
                    stats = column_stats[(kind, col)]
                    stats["total"] += len(values)
                    missing = values.str.lower().isin(MISSING_TOKENS)
                    stats["missing_tokens"] += int(missing.sum())
                    if col not in NONNUMERIC:
                        numeric = pd.to_numeric(values.where(~missing), errors="coerce")
                        invalid = ~missing & numeric.isna()
                        stats["malformed_numeric"] += int(invalid.sum())
                        for token, count in values[invalid].value_counts().head(5).items():
                            stats[f"bad:{token}"] += int(count)
                files.append({"file": decoded_name(info), "kind": kind, "bytes": info.file_size,
                              "compressed_bytes": info.compress_size, "encoding": encoding,
                              "utf8_bom": bom, "rows": len(frame), "columns": len(frame.columns),
                              "station_count": frame[id_col].nunique(),
                              "header": " | ".join(frame.columns.astype(str))})
            except Exception as exc:
                errors.append({"file": decoded_name(info), "error": str(exc)})
            if number % 60 == 0:
                print(f"processed {number}/{len(daily_infos)}", flush=True)
        if not args.limit_files:
            for info in archive.infolist():
                name = decoded_name(info)
                if name.startswith(("4. ", "5. ")) and name.endswith(".csv"):
                    try:
                        frame, encoding, bom = read_csv(archive, info)
                        lat_cols = [c for c in frame if c.endswith("위도")]
                        lon_cols = [c for c in frame if c.endswith("경도")]
                        bridge_tunnel[name] = {"rows": len(frame), "encoding": encoding,
                            "columns": frame.columns.tolist(),
                            "identical_start_end": int(((frame[lat_cols[0]] == frame[lat_cols[1]]) &
                                                        (frame[lon_cols[0]] == frame[lon_cols[1]])).sum()),
                            "exact_duplicate_rows": int(frame.duplicated().sum()),
                            "route_counts": frame.iloc[:, 0].value_counts().to_dict()}
                    except Exception as exc:
                        errors.append({"file": name, "error": str(exc)})
        manifest = [{"name": decoded_name(i), "bytes": i.file_size,
                     "compressed_bytes": i.compress_size, "is_dir": i.is_dir()}
                    for i in archive.infolist()]
    station_rows = []
    for (kind, station), summary in sorted(station_summary.items()):
        intervals = interval_counts[(kind, station)]
        expected = FIELDS[kind][-1]
        station_rows.append({"kind": kind, "station_id": station,
            "protected": kind == "RWIS" and station in PROTECTED_STATIONS,
            "rows": summary["rows"], "first_kst": str(summary["first"]),
            "last_kst": str(summary["last"]), "invalid_time": summary["invalid_time"],
            "duplicate_time_within_file": summary["duplicate_time_within_file"],
            "normal_intervals": intervals[expected], "duplicate_or_reversed_intervals": sum(v for d, v in intervals.items() if d <= 0),
            "gap_intervals": sum(v for d, v in intervals.items() if d > expected),
            "nonstandard_intervals": sum(v for d, v in intervals.items() if 0 < d < expected),
            "names": " | ".join(sorted(summary["names"])),
            "latitudes": " | ".join(sorted(summary["latitudes"])),
            "longitudes": " | ".join(sorted(summary["longitudes"])),
            "routes": " | ".join(sorted(summary["routes"]))})
    pd.DataFrame(files).to_csv(output / "file_inventory.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(station_rows).to_csv(output / "station_inventory.csv", index=False, encoding="utf-8-sig")
    variables = [{"kind": kind, "column": col, **dict(counts)} for (kind, col), counts in sorted(column_stats.items())]
    pd.DataFrame(variables).to_csv(output / "variable_quality.csv", index=False, encoding="utf-8-sig")
    (output / "audit_summary.json").write_text(json.dumps({
        "zip_file": archive_path.name, "zip_bytes": archive_path.stat().st_size,
        "archive_entries": len(manifest), "archive_uncompressed_bytes": sum(x["bytes"] for x in manifest),
        "file_counts": dict(Counter(x["kind"] for x in files)),
        "row_counts": dict(Counter({kind: sum(x["rows"] for x in files if x["kind"] == kind) for kind in FIELDS})),
        "station_counts": dict(Counter({kind: sum(x["kind"] == kind for x in station_rows) for kind in FIELDS})),
        "encodings": dict(Counter(x["encoding"] for x in files)),
        "state_counts_development_only": dict(state_counts),
        "bridge_tunnel": bridge_tunnel, "errors": errors,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "archive_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "files": len(files), "stations": len(station_rows),
                      "errors": len(errors)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
