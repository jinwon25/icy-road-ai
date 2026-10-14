"""독립 검산된 개발 오차와 결빙 결합의 FP/FN 교환을 시각화한다."""
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha


def load(folder):
    s = json.loads((folder / 'summary.json').read_text('utf-8'))
    a = json.loads((folder / 'independent_verification.json').read_text('utf-8'))
    if a['summary_sha256'] != sha(folder / 'summary.json') or not a['status'].endswith('_audit_passed'):
        raise ValueError('Independently audited results required')
    return s


def main():
    temp = load(ROOT / 'outputs/private/method_blending_20261010_v2')
    ice = load(ROOT / 'outputs/private/score_blending_20261010_v2')
    pairs = load(ROOT / 'outputs/private/temperature_pair_blending_20261010_v1')
    target = ROOT / 'docs/images/method_blending_20261010.png'
    if target.exists():
        raise FileExistsError('Preserve rendered figure')
    plt.rcParams.update({'font.family': 'Malgun Gothic', 'axes.unicode_minus': False, 'font.size': 11})
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 7.2), gridspec_kw={'width_ratios': [1, 1.25]})
    names = ['direct_weather14', 'weather_mse300', 'equal_distance_mse300', 'equal_mse_mae300', 'equal_distance_mse_mae300', 'equal_weather_trio', 'simplex_mse', 'simplex_shrink', 'equal_nine']
    labels = ['기본 100회', '단독 300회', '거리12+MSE300', 'MSE300+MAE300', '거리12+MSE/MAE300', '기본14 포함 3종', '비음수 가중 결합', '고정 수축 가중 결합', '9종 균등 평균']
    metrics = temp['metrics'] | pairs['metrics']
    values = [metrics[n]['pooled']['mae'] for n in names]
    axes[0].barh(labels[::-1], values[::-1], color=['#97a6b2', '#5e8394', '#5e8394', '#97a6b2', '#129b83', '#668aa2', '#129b83', '#e99d33', '#97a6b2'])
    for i, v in enumerate(values[::-1]):
        axes[0].text(v+.015, i, f'{v:.4f}', va='center', fontsize=10)
    axes[0].set(xlim=(0, 1.55), xlabel='노면온도 MAE (°C) · 낮을수록 좋음', title='온도: 고정 일부 결합은 단독 300회보다 개선')
    baseline = ice['metrics']['original']
    colors = ['#668aa2']*4+['#e99d33', '#b45e66', '#89749c']
    methods = ['equal_original_binary', 'equal_original_joint', 'equal_binary_joint', 'equal_three_scores', 'original_and_thermal14', 'original_or_thermal14', 'selected']
    annotations = ['기존+이진', '기존+다중상태', '이진+다중상태', '3점수 평균', 'AND', 'OR', '내부 선택']
    offsets = [(7, 7), (7, -17), (7, 8), (7, 9), (7, 8), (7, 8), (-60, 12)]
    for c, label, color, offset in zip(methods, annotations, colors, offsets):
        r = ice['metrics'][c]; x, y = r['fp']-baseline['fp'], r['fn']-baseline['fn']
        axes[1].scatter(x, y, s=65, c=color, zorder=3)
        axes[1].annotate(label, (x, y), xytext=offset, textcoords='offset points', fontsize=10)
    axes[1].axhline(0, color='#60717d', lw=.8); axes[1].axvline(0, color='#60717d', lw=.8)
    axes[1].set(xlim=(-17000, 12500), ylim=(-1450, 230), xlabel='기존 판정 대비 ΔFP · 왼쪽이 개선', ylabel='기존 판정 대비 ΔFN · 아래쪽이 개선', title='결빙: 모든 채택 기준을 통과한 결합 없음')
    axes[1].text(.035, .035, '왼쪽 아래가 FP·FN 동시 개선\n사건·단일 표본·지점별 탐지도 별도 요구', transform=axes[1].transAxes, fontsize=10, bbox={'facecolor': '#f4f7f8', 'edgecolor': 'none', 'pad': 7})
    for ax in axes:
        ax.spines[['top', 'right']].set_visible(False); ax.grid(axis='x', alpha=.15); ax.set_axisbelow(True)
    fig.suptitle('방법론 블렌딩 검토 · 첫 겨울 개발 9곳 · 반복 연구', fontsize=17, x=.07, ha='left')
    fig.text(.07, .025, '온도 155,236행 / 결빙 155,118행 · 보호·기존 평가·다음 겨울 정답 제외 · 독립 성능 또는 공식 점수가 아님', fontsize=10, color='#52636f')
    fig.tight_layout(rect=(.02, .065, .99, .94)); fig.savefig(target, dpi=170, facecolor='white'); plt.close(fig)
    print(str(target), sha(target))


if __name__ == '__main__':
    main()
