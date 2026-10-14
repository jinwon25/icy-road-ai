"""경험적 오차 범위의 지점별 포함률과0도 경계의 애매함을 시각화한다."""
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha


def main():
    out = ROOT / 'outputs/private/temperature_uncertainty_20261010_v1'
    summary = json.loads((out / 'summary.json').read_text('utf-8')); audit = json.loads((out / 'independent_verification.json').read_text('utf-8'))
    assert audit['status'] == 'independent_temperature_range_audit_passed' and audit['summary_sha256'] == sha(out / 'summary.json')
    destination = ROOT / 'docs/images/temperature_uncertainty_20261010.png'
    if destination.exists():
        raise FileExistsError('Preserve prior figure')
    plt.rcParams.update({'font.family': 'Malgun Gothic', 'axes.unicode_minus': False, 'font.size': 11})
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.3), gridspec_kw={'width_ratios': [1.7, 1]})
    reports = summary['reports']; names = ['weather_mse300', 'equal_distance_mse_mae300']; labels = ['MSE300 단독', '기상12·MSE/MAE300 평균']
    stations = sorted(reports[names[0]]['stations']); x = np.arange(len(stations))
    for i, name in enumerate(names):
        coverage = [100*reports[name]['stations'][s]['coverage'] for s in stations]
        axes[0].bar(x+(i-.5)*.36, coverage, width=.36, label=labels[i], color=['#788b9f', '#217d87'][i])
    axes[0].axhline(90, ls='--', color='#9a563d', label='보정에 사용한 목표90%')
    axes[0].set_ylim(0, 105); axes[0].set_xticks(x, stations, rotation=45); axes[0].set_ylabel('실제 노면온도가 범위에 포함된 비율 (%)'); axes[0].set_title('전체 약90%여도 일부 지점은74%'); axes[0].legend(fontsize=9, loc='lower right'); axes[0].grid(axis='y', alpha=.15)
    left = np.zeros(2)
    for field, label, color in [('cold_decisive_rows', '범위 전체≤0°C', '#5c8bb5'), ('ambiguous_rows', '범위가0°C를 걸침', '#dfb563'), ('warm_decisive_rows', '범위 전체>0°C', '#bd6c54')]:
        values = np.array([100*reports[n]['temperature_boundary'][field]/reports[n]['n'] for n in names])
        axes[1].barh(np.arange(2), values, left=left, label=label, color=color)
        for row, value, offset in zip(range(2), values, left):
            axes[1].text(offset+value/2, row, f'{value:.1f}%', ha='center', va='center', fontsize=10)
        left += values
    axes[1].set_yticks(range(2), labels, fontsize=9); axes[1].set_xlim(0, 100); axes[1].set_title('온도 경계를 확정하기 어려운 행은약37%'); axes[1].legend(fontsize=9, loc='upper center', bbox_to_anchor=(.5, -.23)); axes[1].set_xlabel('유효 온도155,236행의 비중 (%)')
    fig.suptitle('평가 그룹 정답을 제외해 계산한 경험적 오차 범위', fontsize=15)
    fig.text(.5, .025, '반복 개발 진단 · 90% 포함 보장 없음 · 온도0°C 경계이며 공식04 결빙 확률이나 안전 판정이 아님', ha='center', fontsize=11)
    fig.tight_layout(rect=(0, .19, 1, .93)); fig.savefig(destination, dpi=170); plt.close(fig); print(destination)


if __name__ == '__main__':
    main()
