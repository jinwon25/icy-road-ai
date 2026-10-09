"""NASA POWER 공개 시간별 복사자료를 정규 격자에서 수집한다. 사후 분석 전용."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PARAMETERS = {"ALLSKY_SFC_SW_DWN": "power_shortwave_wh_m2", "ALLSKY_SFC_LW_DWN": "power_longwave_wh_m2"}


def main():
    private = ROOT / "outputs/private"
    roads = gpd.read_file(private / "spatial/jb_road_center_line.shp").to_crs(4326)
    west, south, east, north = roads.total_bounds
    # 정답과 무관한 1도 격자 중심. NASA SYN1DEG 공간 해상도보다 세밀한 도로별 자료로 오인하지 않는다.
    locations = [(float(lat + .5), float(lon + .5))
                 for lat in range(int(np.floor(south)), int(np.floor(north)) + 1)
                 for lon in range(int(np.floor(west)), int(np.floor(east)) + 1)]
    periods = json.loads((ROOT / "config/evaluation.json").read_text(encoding="utf-8"))["evaluation_periods"]
    out = private / "external/nasa_power"
    out.mkdir(parents=True, exist_ok=True)
    entries, frames = [], []
    for lat, lon in locations:
        grid_id = f"N{lat:.1f}_E{lon:.1f}"
        for period in periods:
            start = (pd.Timestamp(period[0]) - pd.Timedelta(days=1)).strftime("%Y%m%d")
            end = pd.Timestamp(period[1]).strftime("%Y%m%d")
            params = {"parameters": ",".join(PARAMETERS), "community": "RE", "longitude": lon,
                      "latitude": lat, "start": start, "end": end, "format": "JSON", "time-standard": "UTC"}
            url = "https://power.larc.nasa.gov/api/temporal/hourly/point?" + urlencode(params)
            path = out / f"{grid_id}_{start}_{end}.json"
            if path.exists():
                raw = path.read_bytes()
            else:
                with urlopen(url, timeout=45) as response:
                    raw = response.read()
                # 검증이 끝나기 전에 캐시를 완료로 저장하지 않는다.
            payload = json.loads(raw)
            if payload["header"]["time_standard"] != "UTC":
                raise ValueError("NASA time standard must be UTC, not local solar time")
            for name in PARAMETERS:
                if payload["parameters"][name]["units"] != "Wh/m^2":
                    raise ValueError("NASA radiation unit changed")
            values = pd.DataFrame(payload["properties"]["parameter"])
            stamps = pd.to_datetime(values.index, format="%Y%m%d%H", utc=True)
            if len(values) != (pd.Timestamp(end) - pd.Timestamp(start)).days * 24 + 24:
                raise ValueError("NASA returned incomplete requested time grid")
            frame = values.rename(columns=PARAMETERS).apply(pd.to_numeric, errors="coerce")
            frame = frame.mask(frame.eq(payload["header"]["fill_value"]))
            frame["source_hour_kst"] = stamps.tz_convert("Asia/Seoul").tz_localize(None)
            # 명시된 hour 내부의 평균값이므로 시간 전체가 지난 뒤에만 결합한다.
            frame["source_interval_end"] = frame.source_hour_kst + pd.Timedelta(hours=1)
            frame["grid_id"], frame["lat"], frame["lon"] = grid_id, lat, lon
            frames.append(frame.reset_index(drop=True))
            path.write_bytes(raw)
            entries.append({"file": path.name, "url": url, "sha256": hashlib.sha256(raw).hexdigest(),
                            "header": payload["header"], "parameters": payload["parameters"],
                            "missing": {field: int(frame[field].isna().sum()) for field in PARAMETERS.values()}})
            print(f"NASA POWER {grid_id} {start}-{end}: {len(frame)} hours", flush=True)
    combined = pd.concat(frames, ignore_index=True)
    if combined.duplicated(["grid_id", "source_hour_kst"]).any():
        raise ValueError("Duplicate NASA grid/hour")
    combined.to_parquet(out / "hourly.parquet", index=False, compression="zstd")
    manifest = {"source": "NASA Langley Research Center POWER Project", "purpose": "사후 미관측 도로 상태 추정에서 복사열 입력 보완",
                "documentation": "https://power.larc.nasa.gov/docs/services/api/temporal/hourly/",
                "latency_documentation": "https://power.larc.nasa.gov/docs/faqs/data/",
                "attribution": "복사 자료 출처: NASA Langley Research Center POWER Project, NASA Earth Science Directorate Applied Science Program.",
                "retrospective_only": True, "grid_points": locations, "entries": entries,
                "limitations": ["Solar products have multi-day publication latency; these are not real-time inputs.",
                                "Only public grid radiation requested; no RWIS temperature/state or protected outcomes requested.",
                                "One-degree radiation does not resolve bridge, tunnel or local terrain shadow.",
                                "Wh/m2 per one-hour interval is retained explicitly; no mixing with ASOS MJ/m2.",
                                "UTC requested explicitly and converted to KST; source hour shifted to conservative interval end."]}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
