"""검증 전 지형 설명도를 생성한다. 결빙 위험 등급을 부여하지 않는다."""
from pathlib import Path
import json
import textwrap
import geopandas as gpd
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[1]


def main():
    private = ROOT / "outputs/private"
    out = private / "solar_terrain_features"
    data = gpd.read_file(private / "spatial/segment_scaffold/segments.gpkg")
    attributes = pd.read_csv(out / "segment_terrain.csv")
    manifest = json.loads((private / "external/copernicus_dem/manifest.json").read_text(encoding="utf-8"))
    data = data.merge(attributes, on="seg_id", validate="one_to_one")
    available = {f.name for f in font_manager.fontManager.ttflist}
    for font in ["Malgun Gothic", "Noto Sans CJK KR", "NanumGothic"]:
        if font in available:
            plt.rcParams["font.family"] = font
            break
    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(1, 3, figsize=(13, 7))
    specs = [("dsm_elevation_m", "DSM 높이 (m)", "viridis"),
             ("dsm_relative_500m", "주변 500m 대비 높이 차 (m)", "RdBu_r"),
             ("sky_view_proxy", "지형 차폐 기반 하늘 노출 근삿값", "cividis")]
    for ax, (column, title, cmap) in zip(axes, specs):
        kwargs = {"vmin": 0, "vmax": 1} if column == "sky_view_proxy" else {}
        if column == "dsm_relative_500m":
            maximum = data[column].abs().max()
            kwargs = {"vmin": -maximum, "vmax": maximum}
        data.plot(ax=ax, column=column, cmap=cmap, linewidth=2.5, legend=True,
                  legend_kwds={"shrink": .55, "pad": .02}, **kwargs)
        ax.set_title(title, fontsize=11, pad=12)
        ax.set_axis_off()
    fig.suptitle("도로 환경의 공간 차이: 높이와 차폐는 결빙 위험 자체가 아님", fontsize=15, y=.97)
    fig.text(.04, .11, "대상 중심선 275.889km · 최대 1km 도형 467개 · 각 도형 중점에서 특징 추출\nDSM은 수목·건물 포함. 하늘 노출 1은 지형 차폐가 적음을 뜻하며, 낮·밤 열수지에 서로 다른 영향을 줄 수 있음.\n공식 이정·차로 방향·도로 상판 높이는 미확인. 본 그림은 위험 등급도와 구별되는 환경 설명도.", fontsize=10, color="#475569")
    notice = textwrap.fill(manifest["derived_notice"], width=165) + "\n" + textwrap.fill(manifest["liability_notice"], width=165)
    fig.text(.04, .018, notice, fontsize=6.5, color="#64748b", va="bottom")
    fig.subplots_adjust(left=.03, right=.97, bottom=.24, top=.85, wspace=.25)
    fig.savefig(out / "terrain_evidence.png", dpi=180)
    fig.savefig(out / "terrain_evidence.svg")
    plt.close(fig)
    # 배포 시 이미지와 함께 유지할 원천·가공 고지.
    (out / "terrain_evidence_source.json").write_text(json.dumps({"source_manifest": "external/copernicus_dem/manifest.json", "license_notices": manifest, "risk_score": None}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out / "terrain_evidence.png")


if __name__ == "__main__":
    main()
