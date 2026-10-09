"""관측소 종류별 제공 센서와 유효값을 감사한다. 보호 지점의 동적 값은 제외한다."""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive, sha256_file
from src.observation_io import daily_members, numeric_observations
from src.validation import canonical_station_id, PROTECTED_STATIONS, normalize_state

META = ["관측 지점번호", "고속도로", "관측소 종류", "관측소 위도", "관측소 경도", "관측소 고도 (m)"]
FIELDS = ["노면상태", "노면온도 (광학)", "시정 (m)", "습도 (%)", "일 누적 강수량 (mm)",
          "적설 (cm)", "기온 (C)", "1분 풍속 (m/s)", "해면기압 (hPa)", "운량"]


def main():
    archive_path = competition_archive(ROOT)
    pieces = []
    with zipfile.ZipFile(archive_path) as archive:
        for kind in ["RWIS", "FOG"]:
            for name in daily_members(archive, kind):
                with archive.open(name) as stream:
                    raw = pd.read_csv(stream, dtype=str, encoding="utf-8-sig", keep_default_na=False)
                raw["station"] = raw["관측 지점번호"].map(canonical_station_id)
                raw = raw.loc[~raw.station.isin(PROTECTED_STATIONS) & raw.station.ne("<missing>")].copy()
                raw["kind"] = kind
                pieces.append(raw[["station", "kind", *META[1:], *[c for c in FIELDS if c in raw]]])
    data = pd.concat(pieces, ignore_index=True)
    records, metadata = [], []
    for (kind, station), part in data.groupby(["kind", "station"]):
        item = {"station": station, "kind": kind, "rows": len(part)}
        for source, dest in zip(META[1:], ["route", "station_type", "lat", "lon", "elevation_m"]):
            values = part[source].str.strip().drop_duplicates()
            if len(values) != 1:
                raise ValueError(f"Changing station metadata: {station} {source}")
            item[dest] = values.iloc[0]
        metadata.append(item)
        for field in FIELDS:
            raw = part[field]
            value = raw.map(normalize_state) if field == "노면상태" else numeric_observations(raw)
            missing_token = raw.fillna("").astype(str).str.strip().eq("")
            records.append({**item, "field": field, "valid_values": int(value.notna().sum()),
                            "blank_or_absent": int(missing_token.sum()),
                            "nonblank_invalid_or_sentinel": int((~missing_token & value.isna()).sum()),
                            "minimum": value.min(), "maximum": value.max()})
    table = pd.DataFrame(records)
    by_type = table.groupby(["kind", "station_type", "field"], as_index=False).agg(
        stations=("station", "nunique"), rows=("rows", "sum"), valid_values=("valid_values", "sum"),
        blank_or_absent=("blank_or_absent", "sum"),
        nonblank_invalid_or_sentinel=("nonblank_invalid_or_sentinel", "sum"))
    out = ROOT / "outputs/private/sensor_availability"
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "by_station.csv", index=False, encoding="utf-8-sig")
    by_type.to_csv(out / "by_type.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(metadata).to_csv(out / "metadata.csv", index=False, encoding="utf-8-sig")
    summary = {"status": "development_sensor_capability_audit", "archive_sha256": sha256_file(archive_path),
               "stations": pd.DataFrame(metadata).groupby("kind").size().to_dict(),
               "policy": "Exclude protected dynamic values; official sentinels and undefined states are missing.",
               "limitations": ["All-blank sensors may be structural or a sustained failure; no zero fill.",
                               "Sensor availability is descriptive, not evidence that missing means no icing.",
                               "Numeric availability is not a physical-range quality guarantee.",
                               "Fog visibility is measured in metres; no temperature or humidity conversion."]}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
