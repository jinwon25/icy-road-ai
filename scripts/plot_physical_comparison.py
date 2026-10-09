"""적중·오경보·일별 평가의 상충을 함께 시각화한다."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / "outputs/private/physical_ice_comparison"
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    available = {f.name for f in font_manager.fontManager.ttflist}
    for font in ["Malgun Gothic", "Noto Sans CJK KR", "NanumGothic"]:
        if font in available:
            plt.rcParams["font.family"] = font
            break
    plt.rcParams["axes.unicode_minus"] = False
    variants = ["logistic_slot", "physical_w20_daily", "thermal_w20_slot", "thermal_w20_daily", "inner_selected"]
    labels = ["로지스틱 기준", "기상 물리 / 일별 임계값", "열·수분 / 10분 임계값", "열·수분 / 일별 임계값", "내부 후보 자동 선택"]
    colors = ["#64748b", "#0d9488", "#2563eb", "#7c3aed", "#c2410c"]
    rows = [summary["variants"][v] for v in variants]
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.8), sharey=True, gridspec_kw={"width_ratios": [1, 1.3, 1.25]})
    y = np.arange(len(rows))
    values = [[r["slot_micro"]["tp"] for r in rows], [r["slot_micro"]["fp"] for r in rows], [r["daily_station_macro"]["f1"] for r in rows]]
    titles = ["실제 결빙 239시점 중 적중", "오경보 시점 수", "잠정 지점별 일평균 F1"]
    for ax, numbers, title in zip(axes, values, titles):
        ax.barh(y, numbers, color=colors, height=.57)
        ax.set_title(title, fontsize=12, pad=16)
        ax.set_xlim(0, max(numbers) * 1.3)
        ax.grid(axis="x", alpha=.17)
        ax.set_axisbelow(True)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        for k, value in enumerate(numbers):
            label = f"{value:.5f}" if ax is axes[2] else f"{value:,}"
            ax.text(value + max(numbers) * .025, k, label, va="center", fontsize=10)
    axes[0].set_yticks(y, labels)
    axes[0].invert_yaxis()
    fig.suptitle("주변 열·수분 입력은 오경보를 줄였지만, 미탐과 임계값 선택의 불안정이 남음", fontsize=15, x=.52, y=.96)
    fig.text(.02, .035, "수정본 개발 14지점 · 동일 유효 정답 483,629행 · 공식 보호 지점 제외\n내부 지점에서 임계값 선택. 일평균 F1의 유효 날짜 분모는 모델마다 다름. 최종 공식 점수가 아님.", fontsize=10, color="#475569")
    fig.subplots_adjust(left=.20, right=.98, top=.80, bottom=.20, wspace=.35)
    fig.savefig(folder / "physical_tradeoffs.png", dpi=180)
    fig.savefig(folder / "physical_tradeoffs.svg")
    plt.close(fig)
    print(folder / "physical_tradeoffs.png")


if __name__ == "__main__":
    main()
