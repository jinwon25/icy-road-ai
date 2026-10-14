"""고정 평균의 개발·새 호남 평가를 분모와 채택 조건별로 구별해 표시한다."""
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


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    development = ROOT / 'outputs/private/temperature_mean_20261010_v1'
    blind = ROOT / 'outputs/private/temperature_mean_blind_20261010_v1'
    target = ROOT / 'docs/images/temperature_mean_20261010.png'
    receipt = blind / 'figure_receipt.json'
    if target.exists() or receipt.exists():
        raise FileExistsError('Preserve existing figure and receipt')
    dev, test = read(development / 'summary.json'), read(blind / 'summary.json')
    audits = [read(development / 'independent_verification.json'), read(blind / 'independent_verification.json')]
    for folder, audit in zip([development, blind], audits):
        if sha(folder / 'summary.json') != audit['summary_sha256']:
            raise ValueError('Audited result changed')
    plt.rcParams.update({'font.family': 'Malgun Gothic', 'axes.unicode_minus': False,
                         'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    blue, orange, red = '#245b8a', '#cc6b36', '#ad3841'
    fig, axes = plt.subplots(1, 3, figsize=(17.5, 6.7))
    fig.suptitle('고정 1:1 평균 후보: 개발 개선과 새 지점 결과를 구별', fontsize=18, fontweight='bold', y=.96)
    a, b = dev['metrics']['direct_weather14'], dev['metrics']['equal_mean_weather14_weather12']
    ids = sorted(a['stations'])
    delta = [(b['stations'][s]['mae']/a['stations'][s]['mae']-1)*100 for s in ids]
    bars = axes[0].bar(np.arange(len(ids)), delta, color=[red if d > 0 else blue for d in delta])
    axes[0].bar_label(bars, labels=[f'{d:+.1f}' for d in delta], padding=3, fontsize=9)
    axes[0].axhline(0, color='#708090', linewidth=.8)
    axes[0].axhline(5, color=red, linestyle='--', label='사전 악화 상한 5%')
    axes[0].set_xticks(np.arange(len(ids)), ids, rotation=45, ha='right')
    axes[0].set_ylim(min(delta)-4, 9); axes[0].set_ylabel('지점 MAE 변화율 (%) · 낮을수록 좋음')
    axes[0].set_title('개발 9곳 · 온도 기준 통과', pad=15); axes[0].legend(loc='lower left', fontsize=9)
    base, mean = test['temperature']['weather14'], test['temperature']['equal_mean']
    newids = sorted(base['stations']); xx = np.arange(3)
    for offset, values, label, color in [(-.18, base, '기존 기상14', blue), (.18, mean, '고정 1:1 평균', orange)]:
        v = [values['stations'][s]['mae'] for s in newids] + [test['near_freezing']['weather14' if offset < 0 else 'equal_mean']['pooled']['mae']]
        bars = axes[1].bar(xx+offset, [x if x is not None else np.nan for x in v], width=.36, label=label, color=color)
        axes[1].bar_label(bars, labels=[f'{x:.3f}' if x is not None else '미정의' for x in v], padding=4, fontsize=9)
    axes[1].set_xticks(xx, [*newids, '관측 -2~2°C\n두 지점 합산'])
    ymax = max((r['mae'] or 0) for r in [*base['stations'].values(), *mean['stations'].values(),
                                       test['near_freezing']['weather14']['pooled'], test['near_freezing']['equal_mean']['pooled']])
    axes[1].set_ylim(0, max(ymax*1.4, 1)); axes[1].set_ylabel('동일 유효행 MAE (°C)')
    decision = '통과' if audits[1]['temperature_primary_gate_passed'] else '실패'
    axes[1].set_title(f'새 호남 2곳 · 온도 기준 {decision}', pad=15); axes[1].legend(fontsize=9)
    axes[2].axis('off')
    metrics = [test['ice_metrics'][n] for n in ['original_ice', 'thermal_weather14', 'thermal_equal_mean']]
    rows = []
    for label, key in [('맞힌 결빙 TP', 'tp'), ('오경보 FP', 'fp'), ('놓친 결빙 FN', 'fn'),
                       ('탐지 사건', 'detected_events'), ('탐지 단일 사건', 'detected_single_slot_events')]:
        rows.append([label, *[f"{r[key]:,}" for r in metrics]])
    table = axes[2].table(cellText=rows, colLabels=['동일 유효 상태', '원래 분류', '온도14\n+수분', '평균온도\n+수분'],
                          loc='center', cellLoc='center', colWidths=[.35, .21, .22, .22])
    table.auto_set_font_size(False); table.set_fontsize(10); table.scale(1, 2.35)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor('#dbe3eb')
        if r == 0: cell.set_facecolor('#eaf0f7'); cell.set_text_props(weight='bold')
    ice = audits[1]['ice_gate']; label = '입증 불가 (양성 없음)' if ice['status'] != 'evaluated' else ('통과' if ice['passed'] else '실패')
    axes[2].set_title('새 지점 결빙 기준: '+label, pad=15)
    notes = [f"같은 온도 {a['pooled']['n']:,}행 · 반복 개발\n가중치 탐색·새 모델 학습 없음",
             f"같은 온도 {base['pooled']['n']:,}행 · 첫 겨울 일회 평가\n호남선 2곳, SGIS 전북 경계 밖",
             f"유효 상태 {metrics[0]['n']:,}행 · Ice {metrics[0]['tp']+metrics[0]['fn']:,}행\n사건 {metrics[0]['events']}개 · 단일 {metrics[0]['single_slot_events']}개"]
    for ax, note in zip(axes, notes):
        ax.text(.01, -.23, note, transform=ax.transAxes, fontsize=10, color='#46515d')
        if ax is not axes[2]: ax.set_axisbelow(True); ax.grid(axis='y', color='#e7ebef', linewidth=.8)
    fig.text(.035, .025, '예측·모델 봉인 → 재학습 검산 → 정답 수집 → 일회 평가 | 공식·미래겨울 점수 및 최종 채택 아님', fontsize=11)
    fig.subplots_adjust(left=.065, right=.985, top=.79, bottom=.28, wspace=.37)
    fig.savefig(target, dpi=170, facecolor='white'); plt.close(fig)
    result = dict(figure=str(target.relative_to(ROOT)), sha256=sha(target), plot_source_sha256=sha(__file__),
                  development_summary_sha256=sha(development / 'summary.json'), blind_summary_sha256=sha(blind / 'summary.json'))
    with receipt.open('x', encoding='utf-8') as handle: json.dump(result, handle, indent=2); handle.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
