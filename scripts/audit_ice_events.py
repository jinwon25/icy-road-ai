"""Audit adjacent road states around development-only Ice runs without relabeling."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validation import PROTECTED_STATIONS


def canonical_code(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    code = str(value).strip()
    if code.endswith(".0") and code[:-2].isdigit():
        code = code[:-2]
    return code.zfill(2) if code.isdigit() else code


def neighbor(row: pd.Series | None, event_time: pd.Timestamp, direction: int) -> tuple[str | None, int | None]:
    if row is None or (row.time - event_time).total_seconds() != 600 * direction:
        return None, None
    return str(row.state_raw), int(row.ice) if pd.notna(row.ice) else None


def main() -> None:
    private = ROOT / "outputs" / "private"
    data = pd.read_parquet(private / "ice_features" / "features.parquet",
                           columns=["station", "time", "state_raw", "ice"])
    data["station"] = data.station.astype(str)
    if set(data.station) & PROTECTED_STATIONS:
        raise AssertionError("Protected RWIS entered Ice-event audit")
    data = data.sort_values(["station", "time"]).reset_index(drop=True)
    rows = []
    for station, part in data.groupby("station", sort=True):
        part = part.reset_index(drop=True)
        positive_indices = part.index[part.ice.eq(1)].tolist()
        if not positive_indices:
            continue
        starts = []
        ends = []
        for index in positive_indices:
            if not ends or (part.loc[index, "time"] - part.loc[ends[-1], "time"]).total_seconds() != 600:
                starts.append(index)
                ends.append(index)
            else:
                ends[-1] = index
        for first, last in zip(starts, ends, strict=True):
            before = part.loc[first - 1] if first > 0 else None
            after = part.loc[last + 1] if last + 1 < len(part) else None
            prev_raw, prev_label = neighbor(before, part.loc[first, "time"], -1)
            next_raw, next_label = neighbor(after, part.loc[last, "time"], 1)
            rows.append({"station": station, "start_kst": part.loc[first, "time"],
                         "end_kst": part.loc[last, "time"],
                         "ice_slots": last - first + 1,
                         "previous_state_raw": prev_raw,
                         "previous_ice_label": prev_label,
                         "next_state_raw": next_raw,
                         "next_ice_label": next_label})
    events = pd.DataFrame(rows)
    expected = json.loads((private / "development" / "eda_summary.json").read_text(
        encoding="utf-8"))
    if (len(events) != expected["ice_events"]
            or int(events.ice_slots.sum()) != expected["ice_slots"]
            or int(events.ice_slots.eq(1).sum()) != expected["single_slot_events"]):
        raise AssertionError("Event runs differ from prior development EDA")
    single = events.loc[events.ice_slots.eq(1)].copy()
    single["previous_code"] = single.previous_state_raw.map(canonical_code)
    single["next_code"] = single.next_state_raw.map(canonical_code)
    summary = {
        "status": "development_event_context_audit_only",
        "events": len(events), "single_slot_events": len(single),
        "single_with_both_adjacent_valid_labels": int((single.previous_ice_label.notna()
                                                        & single.next_ice_label.notna()).sum()),
        "single_with_both_adjacent_nonice": int((single.previous_ice_label.eq(0)
                                                  & single.next_ice_label.eq(0)).sum()),
        "single_with_previous_wet": int(single.previous_code.eq("02").sum()),
        "single_with_next_wet": int(single.next_code.eq("02").sum()),
        "single_between_code_12": int((single.previous_code.eq("12")
                                       & single.next_code.eq("12")).sum()),
        "single_between_code_15": int((single.previous_code.eq("15")
                                       & single.next_code.eq("15")).sum()),
        "single_adjacent_to_code_12_or_15": int((single.previous_code.isin(["12", "15"])
                                                 | single.next_code.isin(["12", "15"])).sum()),
        "single_without_immediate_previous": int(single.previous_state_raw.isna().sum()),
        "single_without_immediate_next": int(single.next_state_raw.isna().sum()),
        "interpretation": "Neighbor transitions are context, not proof of sensor error. Original Ice labels remain unchanged."
    }
    out = private / "ice_event_audit"
    out.mkdir(parents=True, exist_ok=True)
    events.to_csv(out / "events.csv", index=False, encoding="utf-8-sig")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
