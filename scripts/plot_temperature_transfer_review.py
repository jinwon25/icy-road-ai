"""개발 개선과 새 지점의 손실을 같은 그림에서 구분해 보여준다."""
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file


def main():
    private = ROOT / 'outputs/private'
    paths = [private / 'temperature_loss_20261010_v1/summary.json',
             private / 'temperature_blind_20261010_v1/summary.json',
             private / 'temperature_blind_20261010_v1/independent_verification.json']
    loss, blind, audit = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
    discrepancy = next(c['maximum_distance_m'] for c in audit['coordinate_checks'] if c['station'] == '33407')
    target = ROOT / 'docs/images/temperature_transfer_20261010.png'
    if target.exists():
        raise FileExistsError('Preserve existing figure')
    font_path = Path('C:/Windows/Fonts/malgun.ttf')
    if font_path.exists():
        plt.rcParams['font.family'] = FontProperties(fname=font_path).get_name()
    plt.rcParams.update({'axes.unicode_minus': False, 'font.size': 11, 'axes.spines.top': False,
                         'axes.spines.right': False, 'axes.titlesize': 14, 'axes.titleweight': 'bold'})
    colors = ['#315B86', '#D28534', '#8F579B']
    fig, axs = plt.subplots(2, 2, figsize=(13.6, 9.2), layout='constrained')
    fig.suptitle('개발 온도 오차의 감소가 새 지점의 결빙 탐지 개선으로 이어지지는 않았다', fontsize=17, fontweight='bold')
    a = axs[0, 0]; x = np.arange(2); width = .32
    values = [[loss['metrics']['direct_weather14']['pooled']['mae'], blind['temperature']['weather_hgb100']['station_macro']['mae']],
              [loss['metrics']['weather_mse300']['pooled']['mae'], blind['temperature']['weather_hgb300']['station_macro']['mae']]]
    for i, (name, vals) in enumerate(zip(['HGB 100회', 'HGB 300회'], values)):
        bars = a.bar(x + (i - .5) * width, vals, width, color=colors[i], label=name)
        a.bar_label(bars, fmt='%.3f', padding=4)
    a.set_xticks(x, ['반복 개발 9곳\n합산 155,236행', '봉인 후 새 4곳\n지점 평균, 69,104행'])
    a.set_ylabel('MAE (°C, 작을수록 좋음)'); a.set_ylim(0, 2.25)
    a.set_title('A. 평가 단계별 온도 오차'); a.legend(loc='upper left', frameon=False)
    a.grid(axis='y', alpha=.15); a.set_axisbelow(True)

    a = axs[0, 1]; stations = sorted(blind['temperature']['weather_hgb100']['stations']); x = np.arange(len(stations))
    for i, name in enumerate(['weather_hgb100', 'weather_hgb300']):
        vals = [blind['temperature'][name]['stations'][s]['mae'] for s in stations]
        bars = a.bar(x + (i - .5) * width, vals, width, color=colors[i])
        a.bar_label(bars, fmt='%.2f', padding=4, fontsize=9)
    a.set_xticks(x, ['12406\n서해시점', '23405\n녹진', '33407*\n마달터널', '33416\n두문'])
    a.set_ylabel('MAE (°C)'); a.set_ylim(0, 3.1)
    a.set_title('B. 새 지점 1곳 개선 · 3곳 악화'); a.grid(axis='y', alpha=.15); a.set_axisbelow(True)

    a = axs[1, 0]; x = np.arange(3)
    names = ['original_ice', 'thermal_hgb100', 'thermal_hgb300']
    metrics = [blind['ice_metrics'][name] for name in names]
    for i, (field, total, label) in enumerate([('detected_events', 56, '전체 사건'), ('detected_single_slot_events', 39, '단일 시점 사건')]):
        vals = [100 * m[field] / total for m in metrics]
        bars = a.bar(x + (i - .5) * width, vals, width, color=[colors[0], colors[2]][i], label=label)
        for bar, m in zip(bars, metrics):
            a.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2, f'{m[field]}/{total}', ha='center', fontsize=10)
    a.set_xticks(x, ['기존 Ice', '온도100+수분', '온도300+수분'])
    a.set_ylabel('탐지 사건 비율 (%)'); a.set_ylim(0, 82)
    a.set_title('C. 오경보 감소와 함께 사건 탐지 손실'); a.legend(loc='upper right', frameon=False)
    a.grid(axis='y', alpha=.15); a.set_axisbelow(True)

    a = axs[1, 1]
    for i, (m, label, dy) in enumerate(zip(metrics, ['기존 Ice', '온도100+수분', '온도300+수분'], [-20, 20, -35])):
        a.scatter(m['fp'], m['fn'], s=110, color=colors[i])
        a.annotate(f'{label}\nFP {m["fp"]:,} / FN {m["fn"]}', (m['fp'], m['fn']), xytext=(8, dy),
                   textcoords='offset points', fontsize=10, color=colors[i])
    a.set_xlim(0, 24000); a.set_ylim(50, 65)
    a.set_xlabel('오경보 시점 FP (작을수록 좋음)'); a.set_ylabel('놓친 결빙 시점 FN (작을수록 좋음)')
    a.set_title('D. 새 4곳 · 유효 상태 69,101행 · Ice 88행'); a.grid(alpha=.15)
    fig.get_layout_engine().set(rect=(0, .06, 1, .93))
    fig.text(.02, .022, f'*33407: 정적 목록과 관측 응답 위치 {discrepancy:.1f}m 차이. 좌표·입력·예측 사후 수정 없음.\n'
             '같은 첫 겨울의 공간 평가이며 공식 점수·미래 겨울 검증이 아니다. 단계별 집계 방식이 달라 개선율은 단계 안에서만 비교한다.', fontsize=10, color='#444444')
    target.parent.mkdir(exist_ok=True)
    fig.savefig(target, dpi=170)
    plt.close(fig)
    receipt = private / 'judge_followup_20261009_v1/temperature_review_figure_receipt.json'
    with receipt.open('x', encoding='utf-8') as f:
        json.dump({'source_sha256': {str(p): sha256_file(p) for p in paths}, 'figure_sha256': sha256_file(target),
                   'script_sha256': sha256_file(__file__), 'row_level_data_in_figure': False}, f, indent=2)
    print(target)


if __name__ == '__main__':
    main()
