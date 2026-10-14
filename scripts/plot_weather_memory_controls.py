"""온도 최저오차와 기존 사건을 보존하는 균형 후보의 차이를 시각화한다."""
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
    private = ROOT / 'outputs/private'; study = private / 'weather_memory_controls_20261013_v1'
    s = json.loads((study / 'summary.json').read_text('utf-8')); a = json.loads((study / 'independent_verification.json').read_text('utf-8'))
    assert a['summary_sha256'] == sha(study / 'summary.json')
    source = json.loads((private / 'weather_memory_temperature_20261013_v2/summary.json').read_text('utf-8'))
    event = json.loads((private / 'weather_memory_event_review_20261013_v1/review.json').read_text('utf-8'))
    destination = ROOT / 'docs/images/weather_memory_controls_20261013.png'
    if destination.exists(): raise FileExistsError('Preserve final figure')
    plt.rcParams.update({'font.family': 'Malgun Gothic', 'axes.unicode_minus': False, 'font.size': 11})
    names = ['equal_distance_mse_mae300', 'equal_trio_memory', 'equal_nohistory_pair', 'equal_trio_nohistory']
    labels = ['기존3종 평균', '기존·이력 평균', '이력 없는2종 평균', '기존·대조군 평균']; colors = ['#8493a1', '#c89546', '#507da5', '#4b9286']
    fig, axes = plt.subplots(1, 3, figsize=(15, 6)); x = np.arange(4)
    ax = axes[0]; values = [s['metrics'][n]['pooled']['mae'] for n in names]
    bars = ax.bar(x, values, color=colors); ax.bar_label(bars, fmt='%.4f', padding=3)
    ax.set_ylim(0, 1.42); ax.set_xticks(x, labels, rotation=20, fontsize=10); ax.set_ylabel('MAE (°C)'); ax.set_title('온도 오차 · 공통155,236행'); ax.grid(axis='y', alpha=.15)
    ice = [source['ice_diagnostic'][names[0]], source['ice_diagnostic'][names[1]], s['ice_diagnostic'][names[2]], s['ice_diagnostic'][names[3]]]
    ax = axes[1]
    for metric, offset, color, label in [('fp', -.18, '#788fac', '오경보 변화'), ('fn', .18, '#ba7864', '미탐 변화')]:
        v = [r[metric]-ice[0][metric] for r in ice]
        bars = ax.bar(x+offset, v, .34, color=color, label=label); ax.bar_label(bars, padding=3, fontsize=10)
    ax.set_xticks(x, labels, rotation=20, fontsize=10); ax.set_ylabel('기존 대비 행 수 변화 · 음수가 감소'); ax.set_title('결빙 변화 · 공통155,118행'); ax.axhline(0, color='#888', lw=.8); ax.legend(fontsize=9); ax.grid(axis='y', alpha=.15)
    ax = axes[2]
    results = [dict(lost_events=0, gained_events=0), event['comparisons'][names[1]], a['event_identity_checks'][names[2]], a['event_identity_checks'][names[3]]]
    gained, lost = [r['gained_events'] for r in results], [-r['lost_events'] for r in results]
    bars = ax.barh(x, gained, color='#4b9286', label='새로 탐지한 사건'); ax.bar_label(bars, padding=3)
    bars = ax.barh(x, lost, color='#ba7864', label='기존 사건의 신규 누락'); ax.bar_label(bars, padding=3)
    ax.set_yticks(x, labels, fontsize=10); ax.axvline(0, color='#888', lw=.8); ax.set_xlim(-2, 9); ax.set_xlabel('사건 수'); ax.set_title('순증가와 기존 사건 손실을 구별'); ax.legend(fontsize=9, loc='lower right'); ax.grid(axis='x', alpha=.15)
    fig.suptitle('온도 개선과 결빙 사건 보존을 함께 검증한 고정 평균 후보', fontsize=16)
    fig.text(.5, .025, '반복 첫 겨울 개발9곳 · 독립/공식 성능 아님 · 내부 자동 선택은 실패 · 최종 모델 승격 보류', ha='center', fontsize=11)
    fig.tight_layout(rect=(0, .1, 1, .92)); fig.savefig(destination, dpi=160); plt.close(fig); print(destination)


if __name__ == '__main__': main()
