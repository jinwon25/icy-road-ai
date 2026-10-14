"""감사된 여섯 방법의 지표와 사건 탐지 손실을 집계 그림으로 보존한다."""
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

NAMES = ['original', 'thermal14', 'binary100_control', 'hgb_long300', 'hgb_no_distance', 'hgb_history', 'hgb_balanced', 'catboost400', 'hurdle_non_dry']
LABELS = ['기존 분류', '온도·수분 규칙', 'HGB100 대조', 'HGB300', '거리 제거', '과거 기상', '클래스 균형', 'CatBoost400', '2단계 비건조']


def main():
    out = ROOT / 'outputs/private/ice_methodology_20261010_v1'
    summary = json.loads((out / 'summary.json').read_text('utf-8'))
    audit = json.loads((out / 'independent_verification.json').read_text('utf-8'))
    assert audit['status'] == 'independent_ice_methodology_audit_passed' and audit['summary_sha256'] == sha(out / 'summary.json')
    destination = ROOT / 'docs/images/ice_methodology_20261010.png'
    if destination.exists():
        raise FileExistsError('Preserve existing reviewed figure')
    plt.rcParams.update({'font.family': 'Malgun Gothic', 'axes.unicode_minus': False, 'font.size': 10})
    metrics = summary['metrics']; y = np.arange(len(NAMES))
    fig, axes = plt.subplots(1, 3, figsize=(16, 6), sharey=True)
    for ax, field, title in zip(axes, ['f1', 'fixed_ice_day_f1', 'detected_events'], ['시점 합산 F1', '실제 결빙일 지점 평균 F1', '탐지한 결빙 사건 / 347']):
        values = [metrics[name][field] for name in NAMES]
        ax.barh(y, values, color=['#667588', '#d3983e', '#667588', *['#217d87']*6])
        ax.set_title(title, pad=13); ax.grid(axis='x', alpha=.2); ax.set_axisbelow(True)
        ax.set_xlim(0, max(values)*1.25)
        for row, value in zip(y, values):
            ax.text(value+max(values)*.02, row, f'{value:.4f}' if field != 'detected_events' else str(value), va='center')
        if field == 'detected_events':
            ax.axvline(metrics['original'][field], ls='--', color='#667588', lw=1)
    axes[0].set_yticks(y, LABELS); axes[0].invert_yaxis()
    fig.suptitle('같은 개발 9개 지점 · Ice 6,611 / 유효 155,118행 · 설정 고정 후 비교', fontsize=15, y=.98)
    fig.text(.5, .02, '반복 개발 결과: 공식 점수·독립 성능 아님. 합산 F1 상승만으로 지점·미탐·단일시점 사건의 악화를 허용하지 않음.', ha='center', fontsize=11)
    fig.tight_layout(rect=(0, .07, 1, .94)); fig.savefig(destination, dpi=170); plt.close(fig)
    print(destination)


if __name__ == '__main__':
    main()
