"""공개 GLO-30 타일·제품 메타데이터·라이선스를 분석 구역만 수집한다."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

import geopandas as gpd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file


def download(url, path):
    if path.exists():
        return
    temporary = path.with_suffix(path.suffix + ".part")
    with urlopen(url, timeout=45) as response, temporary.open("wb") as stream:
        while chunk := response.read(1024 * 1024):
            stream.write(chunk)
    temporary.replace(path)


def main():
    private = ROOT / "outputs/private"
    roads = gpd.read_file(private / "spatial/jb_road_center_line.shp").to_crs(4326)
    west, south, east, north = roads.total_bounds
    out = private / "external/copernicus_dem"
    out.mkdir(parents=True, exist_ok=True)
    entries = []
    base = "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com"
    for lat in range(int(np.floor(south)), int(np.floor(north)) + 1):
        for lon in range(int(np.floor(west)), int(np.floor(east)) + 1):
            stem = f"Copernicus_DSM_COG_10_N{lat:02}_00_E{lon:03}_00_DEM"
            metadata = f"Copernicus_DSM_10_N{lat:02}_00_E{lon:03}_00.xml"
            for filename in [stem + ".tif", metadata]:
                url = f"{base}/{stem}/{filename}"
                path = out / filename
                download(url, path)
                entries.append({"file": filename, "url": url, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
            print(f"Downloaded/public cache verified: {stem}", flush=True)
    license_url = f"{base}/Copernicus_DSM_COG_10_N35_00_E126_00_DEM/INFO/eula_F.pdf"
    download(license_url, out / "eula_F.pdf")
    manifest = {"dataset": "Copernicus DEM GLO-30 Public via AWS Open Data", "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                "registry": "https://registry.opendata.aws/copernicus-dem/", "license_url": license_url,
                "license_sha256": sha256_file(out / "eula_F.pdf"), "entries": entries,
                "source_notice": "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.",
                "derived_notice": "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.",
                "liability_notice": "The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any use of the Copernicus WorldDEM-30.",
                "limitations": ["Digital surface model includes structures/vegetation; not bare earth or bridge-deck survey.",
                                "Public downloadable tiles only; no restricted view service or credentials used.",
                                "Source acquisition vintage must be read from tile XML; later road works are not guaranteed."]}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
