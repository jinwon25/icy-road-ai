"""개발 RWIS만 같은 지점·시각으로 맞춰 두 배포본의 변경을 집계한다."""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file
from src.observation_io import daily_members, read_columns
from src.validation import PROTECTED_STATIONS, canonical_station_id, normalize_state

COLUMNS = ["관측시각 (KST)", "관측 지점번호", "노면상태", "노면온도 (광학)", "습도 (%)", "일 누적 강수량 (mm)", "기온 (C)"]
NAMES = ["time", "station", "state", "road_temp", "humidity", "rain_cum", "air_temp"]


def read_development(archive, member):
    frame = read_columns(archive, member, COLUMNS, NAMES)
    frame["station"] = frame.station.map(canonical_station_id)
    frame = frame.loc[~frame.station.isin(PROTECTED_STATIONS | {"<missing>"})].copy()
    frame["time"] = pd.to_datetime(frame.time, errors="raise")
    if frame.duplicated(["station", "time"]).any():
        raise ValueError(f"Duplicate development keys: {member}")
    return frame


def compare(old_path, new_path):
    counts, changed, away_midnight, transitions = Counter(), Counter(), Counter(), Counter()
    with zipfile.ZipFile(old_path) as old, zipfile.ZipFile(new_path) as new:
        old_files = {Path(n).name: n for n in daily_members(old, "RWIS")}
        new_files = {Path(n).name: n for n in daily_members(new, "RWIS")}
        if old_files.keys() != new_files.keys():
            raise ValueError("RWIS date coverage differs; review unmatched daily files first")
        for name in sorted(old_files):
            a, b = read_development(old, old_files[name]), read_development(new, new_files[name])
            paired = a.merge(b, on=["station", "time"], how="outer", suffixes=("_old", "_new"),
                             validate="one_to_one", indicator=True)
            counts.update(paired._merge.value_counts().to_dict())
            shared = paired.loc[paired._merge.eq("both")]
            for column in NAMES[2:]:
                x, y = shared[column + "_old"], shared[column + "_new"]
                nx, ny = pd.to_numeric(x, errors="coerce"), pd.to_numeric(y, errors="coerce")
                same = x.eq(y) | (nx.notna() & ny.notna() & nx.eq(ny))
                changed[column] += int((~same).sum())
                away_midnight[column] += int((~same & shared.time.dt.time.ne(pd.Timestamp("00:00").time())).sum())
            old_labels = shared.state_old.map(normalize_state).astype("Int64").fillna(-1).astype(int)
            new_labels = shared.state_new.map(normalize_state).astype("Int64").fillna(-1).astype(int)
            transitions.update(f"{a}->{b}" for a, b in zip(old_labels, new_labels))
    return {"scope": "development RWIS only; protected stations excluded before comparison",
            "old_archive": old_path.name, "new_archive": new_path.name,
            "old_sha256": sha256_file(old_path), "new_sha256": sha256_file(new_path),
            "key_counts": dict(counts), "changed_values_on_shared_keys": dict(changed),
            "changed_values_outside_midnight": dict(away_midnight),
            "label_transitions_on_shared_keys_minus1_is_unknown": dict(transitions)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.old, args.new)
    out = ROOT / "outputs/private/release_comparison"
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
