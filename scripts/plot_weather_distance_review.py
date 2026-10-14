"""거리 제거의 지점별 손실과 기상망 확장 후보의 한계를 그림으로 기록한다."""
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha


def main():
    experiment = ROOT / 'outputs/private/weather_distance_20261010_v1'
    metadata = ROOT / 'outputs/private/weather_network_review_20261010_v1/metadata_analysis'
    target = ROOT / 'docs/images/weather_distance_20261010.png'
    receipt = experiment / 'figure_receipt.json'
    if target.exists() or receipt.exists():
        raise FileExistsError('Preserve previous figure and receipt')
    summary = json.loads((experiment / 'summary.json').read_text(encoding='utf-8'))
    verification = json.loads((experiment / 'independent_verification.json').read_text(encoding='utf-8'))
    assert sha(experiment / 'summary.json') == verification['summary_sha256']
    network_summary = json.loads((metadata / 'summary.json').read_text(encoding='utf-8'))
    network_audit = json.loads((metadata / 'independent_verification.json').read_text(encoding='utf-8'))
    assert sha(metadata / 'summary.json') == network_audit['summary_sha256']
    path = metadata / 'development_distance_comparison.csv'
    assert sha(path) == network_summary['files'][path.name]
    plt.rcParams.update({'font.family': 'Malgun Gothic', 'axes.unicode_minus': False,
                         'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.8))
    fig.suptitle('거리 변수 제거와 기상망 확장: 평균 개선·지점 손실·실측 미확보를 구별', fontsize=17, fontweight='bold', y=.97)
    blue, orange, red = '#245b8a', '#cc6b36', '#ad3841'
    baseline = summary['metrics']['direct_weather14']
    candidate = summary['metrics']['weather12_no_distance']
    ids = sorted(baseline['stations'])
    delta = [(candidate['stations'][s]['mae'] / baseline['stations'][s]['mae'] - 1) * 100 for s in ids]
    bars = axes[0].bar(np.arange(len(ids)), delta, color=[red if d > 5 else blue for d in delta])
    axes[0].bar_label(bars, labels=[f'{d:+.1f}' for d in delta], padding=3, fontsize=9)
    axes[0].axhline(0, color='#708090', linewidth=.8)
    axes[0].axhline(5, color=red, linestyle='--', label='사전 허용 악화 5%')
    axes[0].set_xticks(np.arange(len(ids)), ids, rotation=45, ha='right')
    axes[0].set_ylabel('지점 MAE 변화율 (%) · 낮을수록 좋음')
    axes[0].set_ylim(-24, 10); axes[0].legend(loc='lower left', fontsize=9)
    axes[0].set_title('8곳 개선, 12207의 5.94% 악화로 미채택', pad=12)

    names = ['direct_weather14', 'weather12_no_distance', 'selected_temperature']
    xx = np.arange(3)
    for i, (field, label, color) in enumerate([('mae', 'MAE', blue), ('rmse', 'RMSE', orange)]):
        values = [summary['metrics'][n]['station_macro'][field] for n in names]
        bars = axes[1].bar(xx+(i-.5)*.34, values, width=.34, color=color, label=label)
        axes[1].bar_label(bars, fmt='%.3f', padding=3, fontsize=9)
    axes[1].set_xticks(xx, ['기존 날씨14', '거리 제거12', '내부 선택'])
    axes[1].set_ylabel('지점 평균 온도 오차 (°C)'); axes[1].set_ylim(0, 2.35)
    axes[1].legend(fontsize=9); axes[1].set_title('같은 개발 9곳·유효 온도 155,236행', pad=12)

    distances = pd.read_csv(path)
    xx = np.arange(2)
    for i, (column, label, color) in enumerate([('current_cache_nearest_km', '기존 캐시 좌표', blue),
                                              ('metadata_candidate_km', '공식 이력 후보 좌표', orange)]):
        values = distances.groupby('kind')[column].mean().loc[['AWS', 'ASOS']]
        bars = axes[2].bar(xx+(i-.5)*.34, values, width=.34, color=color, label=label)
        axes[2].bar_label(bars, fmt='%.2f', padding=3, fontsize=9)
    axes[2].set_xticks(xx, ['AWS', 'ASOS']); axes[2].set_ylim(0, 23)
    axes[2].set_ylabel('23개 개발 위치의 최근접 평균 거리 (km)')
    axes[2].set_title('메타데이터 비교 · 관측값·성능 확보 전', pad=12)
    axes[2].legend(fontsize=9)
    notes = ['개발 반복 비교이며 새 독립 평가가 아님\n내부 선택도 외부 지점 손실 기준을 통과하지 못함',
             '고정 수분 규칙 F1 0.1090 → 0.1176\n추가 TP 71행은 모두 33408 · 공식 점수 아님',
             'AWS 578곳·ASOS 96곳의 기간 안정 후보\n실제 AWS API 403 · 거리 감소가 성능 증거는 아님']
    for ax, note in zip(axes, notes):
        ax.set_axisbelow(True); ax.grid(axis='y', color='#e7ebef', linewidth=.8)
        ax.text(.01, -.27, note, transform=ax.transAxes, fontsize=9, color='#46515d')
    fig.text(.035, .015, '첫 겨울 개발 전용 | 새 학습 10건·별도 재추론 검산 완료 | 기존 보호·다음 겨울·개봉 8/4곳의 평가 봉인 보존', fontsize=10)
    fig.subplots_adjust(left=.06, right=.985, top=.81, bottom=.28, wspace=.35)
    fig.savefig(target, dpi=170, facecolor='white'); plt.close(fig)
    result = dict(figure=str(target.relative_to(ROOT)), sha256=sha(target),
                  plot_source_sha256=sha(Path(__file__)), experiment_summary_sha256=sha(experiment / 'summary.json'),
                  metadata_summary_sha256=sha(metadata / 'summary.json'))
    receipt.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
