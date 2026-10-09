"""감사 완료 개발 결과의 집계 그림. 원본 행·모델·예측은 저장소에 넣지 않는다."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, NullFormatter
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); folder = args.experiment.resolve(); output = args.output.resolve()
    if not folder.is_relative_to((ROOT / 'outputs/private').resolve()):
        parser.error('Only private local experiment inputs allowed')
    if not any(output.is_relative_to((ROOT / base).resolve()) for base in ['outputs/private', 'docs/images']):
        parser.error('Write aggregate figures to docs/images or outputs/private')
    if json.loads((folder / 'independent_verification.json').read_text('utf-8'))['status'] != 'passed':
        raise ValueError('Independent audit required before publishing aggregate figure')
    summary = json.loads((folder / 'summary.json').read_text('utf-8'))['metrics']
    ranking = json.loads((folder / 'ranking_diagnostics.json').read_text('utf-8'))
    stations = pd.read_csv(folder / 'station_metrics.csv', dtype={'station': str})
    font = 'Malgun Gothic' if (Path('C:/Windows/Fonts/malgun.ttf')).exists() else 'DejaVu Sans'
    plt.rcParams.update({'font.family': font, 'axes.unicode_minus': False, 'font.size': 10})
    names = ['baseline_prediction', 'thermal_moisture', 'binary_thermal_weather', 'joint_surface_state']
    labels = ['기존 분류', '고정 온도·수분', '새 이진', '새 다중 상태']
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), gridspec_kw={'height_ratios': [1, 1.08]})
    x = np.arange(4); width = .35
    for key, label, shift, color in [('f1', '시점 합산 F1', -width/2, '#27688f'),
                                    ('fixed_ice_day_f1', '실제 결빙일 지점 평균 F1', width/2, '#e79b3b')]:
        bars = axes[0, 0].bar(x + shift, [summary[n][key] for n in names], width, label=label, color=color)
        axes[0, 0].bar_label(bars, fmt='%.4f', padding=3, fontsize=9)
    axes[0, 0].set(xticks=x, xticklabels=labels, ylim=(0, .145), title='같은 155,118개 유효 시점 · 새 후보 성능 하락')
    axes[0, 0].legend(loc='upper right', fontsize=9); axes[0, 0].grid(axis='y', alpha=.2)
    for key, label, shift, color in [('detected_events', '전체 347사건 중 탐지', -width/2, '#27688f'),
                                    ('detected_single_slot_events', '단일 시점 118사건 중 탐지', width/2, '#e79b3b')]:
        bars = axes[0, 1].bar(x + shift, [summary[n][key] for n in names], width, label=label, color=color)
        axes[0, 1].bar_label(bars, fmt='%d', padding=3)
    axes[0, 1].set(xticks=x, xticklabels=labels, ylim=(0, 190), title='오경보 감소만으로 채택하지 않음 · 사건 탐지 확인')
    axes[0, 1].legend(fontsize=9); axes[0, 1].grid(axis='y', alpha=.2)
    ids = sorted(stations.station.unique())
    matrix = stations.pivot(index='policy', columns='station', values='recall').loc[names, ids].to_numpy()
    axes[1, 0].imshow(matrix, cmap='Blues', vmin=0, vmax=1, aspect='auto')
    axes[1, 0].set(xticks=np.arange(len(ids)), xticklabels=ids, yticks=np.arange(4), yticklabels=labels,
                   title='지점별 재현율 · 큰 결빙 집단 33408 탐지 붕괴')
    for row, name in enumerate(names):
        for col, station in enumerate(ids):
            record = stations[(stations.policy == name) & stations.station.eq(station)].iloc[0]
            n = int(record.tp + record.fn)
            axes[1, 0].text(col, row, f'{int(record.tp)}/{n}' if n else 'Ice 없음', ha='center', va='center', fontsize=8,
                            color='white' if matrix[row, col] > .65 else '#222')
    axes[1, 0].tick_params(axis='x', rotation=35)
    scale = [r for r in ranking['score_scales'] if r['group'] == 'tongyeong_geumsan']
    for j, r in enumerate(scale):
        axes[1, 1].bar(j - .18, r['positive_p95_score'], .36, color='#27688f', label='실제 Ice 점수 95백분위' if j == 0 else None)
        axes[1, 1].bar(j + .18, r['threshold'], .36, color='#e79b3b', label='다른 그룹에서 정한 임계값' if j == 0 else None)
        for xpos, value in [(j - .18, r['positive_p95_score']), (j + .18, r['threshold'])]:
            axes[1, 1].text(xpos, value * 1.18, f'{value:.4f}', ha='center', fontsize=10)
    axes[1, 1].set(yscale='log', ylim=(.0006, .15), xticks=[0, 1], xticklabels=['새 이진', '새 다중 상태'],
                   title='금산 그룹: 순위(AP)는 유지되어도 점수·임계값 이전 실패')
    axes[1, 1].yaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{value:g}'))
    axes[1, 1].yaxis.set_minor_formatter(NullFormatter())
    axes[1, 1].legend(fontsize=9); axes[1, 1].grid(axis='y', alpha=.2)
    fig.suptitle('추정 온도 교차 검증 + 노면상태 공동 분류 · 첫 겨울 반복 개발 진단', fontsize=18, y=.98)
    fig.text(.5, .022, '4개 그룹 모두 내부 선택에서 새 후보 탈락 · 공식 점수/새 독립 평가 아님 · 가중 학습 점수는 보정된 위험확률이 아님', ha='center', fontsize=11)
    fig.tight_layout(rect=(0, .045, 1, .95), h_pad=3, w_pad=3)
    output.parent.mkdir(parents=True, exist_ok=True); fig.savefig(output, dpi=145); plt.close(fig)
    print('집계 그림 저장:', output.relative_to(ROOT))


if __name__ == '__main__':
    main()
