"""공통 공간 분할의 온도 개선·지점 손실·범위 포함률·결빙 사건을 그린다."""
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
    out = ROOT / 'outputs/private/weather_memory_temperature_20261013_v1'
    s = json.loads((out / 'summary.json').read_text('utf-8')); a = json.loads((out / 'independent_verification.json').read_text('utf-8'))
    assert a['status'] == 'independent_weather_memory_temperature_audit_passed' and a['summary_sha256'] == sha(out / 'summary.json')
    destination = ROOT / 'docs/images/weather_memory_temperature_20261013.png'
    if destination.exists(): raise FileExistsError('Preserve reviewed figure')
    plt.rcParams.update({'font.family': 'Malgun Gothic', 'axes.unicode_minus': False, 'font.size': 10})
    names = ['equal_distance_mse_mae300', 'memory12_mse300', 'memory12_mae300', 'equal_memory_pair', 'equal_trio_memory']
    labels = ['기존3종 평균', '기상 이력MSE', '기상 이력MAE', '이력2종 평균', '기존·이력 평균']
    colors = ['#77899b', '#457ca5', '#5ba08e', '#d59e43', '#8c65a5']
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 10))
    x = np.arange(len(names)); ax = axes[0, 0]
    for field, offset, color, label in [('pooled', -.19, '#447c9d', '전체 MAE'), ('near_freezing', .19, '#cf9b4d', '실제−2~2°C MAE')]:
        values = [s['metrics'][n][field]['mae'] for n in names]
        bars = ax.bar(x+offset, values, width=.36, label=label, color=color)
        ax.bar_label(bars, fmt='%.3f', padding=3, fontsize=9)
    ax.set_xticks(x, labels, rotation=12); ax.set_ylabel('MAE (°C)'); ax.set_ylim(0, max(v['pooled']['mae'] for v in s['metrics'].values())*1.25)
    ax.legend(fontsize=9); ax.set_title('같은155,236유효행에서 온도 오차 비교'); ax.grid(axis='y', alpha=.15)
    stations = sorted(s['metrics'][names[0]]['stations']); y = np.arange(len(stations)); ax = axes[0, 1]
    for name, label, color in zip(names[1:], labels[1:], colors[1:]):
        differences = [100*(s['metrics'][name]['stations'][st]['mae']/s['metrics'][names[0]]['stations'][st]['mae']-1) for st in stations]
        ax.plot(differences, y, marker='o', label=label, color=color, ms=4)
    ax.axvline(0, color='#888', lw=.8); ax.axvline(5, color='#ad5946', ls='--', label='악화 허용5%')
    ax.set_yticks(y, stations); ax.set_xlabel('기존 평균 대비 지점 MAE 변화 (%) · 왼쪽이 개선'); ax.set_title('평균 개선과 모든 지점의 손실을 함께 확인')
    ax.legend(fontsize=8, loc='lower left'); ax.grid(axis='x', alpha=.15)
    ax = axes[1, 0]
    for key, label, color in [('equal_distance_mse_mae300_global', '기존 전역 범위', colors[0]), ('equal_distance_mse_mae300_conditional', '기존 조건별 범위', '#be7751'), ('equal_trio_memory_conditional', '기존·이력 조건별 범위', colors[-1])]:
        values = [100*s['ranges'][key]['stations'][st]['coverage'] for st in stations]
        ax.plot(y, values, marker='o', label=label, color=color)
    ax.axhline(90, color='#999', ls='--', label='보정 목표90%'); ax.axhline(80, color='#ad5946', ls=':', label='개발 지점 하한80%')
    ax.set_xticks(y, stations, rotation=40); ax.set_ylim(50, 102); ax.set_ylabel('실제 온도 포함률 (%)'); ax.set_title('경험적 범위의 지점별 포함률 · 보장 아님')
    ax.legend(fontsize=8, loc='lower right'); ax.grid(axis='y', alpha=.15)
    ax = axes[1, 1]
    events = [s['ice_diagnostic'][n]['detected_events'] for n in names]
    bars = ax.bar(x, events, color=colors); ax.bar_label(bars, padding=3)
    ax.set_xticks(x, labels, rotation=12); ax.set_ylim(0, max(events)*1.22); ax.set_ylabel('탐지한 결빙 사건 수 (전체347사건)')
    ax.set_title('같은0°C·수분 규칙으로 결빙 손실도 점검'); ax.grid(axis='y', alpha=.15)
    fig.suptitle('기상 관측의1·3·12시간 이력과 고정 평균의 공간 개발 비교', fontsize=16)
    fig.text(.5, .018, '첫 겨울 개발9곳 · 새20모델 · 반복 개발 결과 · 독립/공식 점수·최종 위험 등급이 아님', ha='center', fontsize=11)
    fig.tight_layout(rect=(0, .045, 1, .95)); fig.savefig(destination, dpi=160); plt.close(fig); print(destination)


if __name__ == '__main__': main()
