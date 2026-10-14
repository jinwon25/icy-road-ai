"""새 지점의 입력 거리·일별 분모·실측 온도별 탐지 손실을 그림으로 검토한다."""
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
    source = ROOT / 'outputs/private/unresolved_review_20261010_v1/analysis'
    target = ROOT / 'docs/images/unresolved_evidence_20261010.png'
    if target.exists() or (source.parent / 'figure_receipt.json').exists():
        raise FileExistsError('Preserve previous figure')
    summary = json.loads((source / 'summary.json').read_text(encoding='utf-8'))
    for name, digest in summary['files'].items():
        if sha(source / name) != digest:
            raise ValueError('Evidence changed')
    plt.rcParams.update({'font.family': 'Malgun Gothic', 'axes.unicode_minus': False,
                         'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    figure, axes = plt.subplots(1, 3, figsize=(16, 5.5))
    figure.suptitle('미해결 사항 검토: 입력 범위와 평가 분모, 실제 놓친 결빙', fontsize=18, fontweight='bold', y=.98)
    blue, orange, grey = '#245b8a', '#cc6b36', '#c9d0d5'
    support = pd.read_csv(source / 'input_support_detail.csv', dtype={'station': str})
    envelope = pd.read_csv(source / 'training_feature_envelope.csv').set_index('feature')
    ids = ['12406', '23405', '33407', '33416']; x = np.arange(4)
    for i, (feature, label, color) in enumerate([('aws_distance_km', 'AWS', blue), ('asos_distance_km', 'ASOS', orange)]):
        values = support.loc[support.feature.eq(feature)].set_index('station').loc[ids, 'observed_maximum']
        bars = axes[0].bar(x + (i - .5) * .35, values, width=.35, label=label, color=color)
        axes[0].bar_label(bars, fmt='%.1f', padding=2, fontsize=8)
        bound = envelope.loc[feature, 'maximum']
        axes[0].axhline(bound, color=color, linestyle='--', linewidth=1.4, label=f'학습 {label} 최대 {bound:.1f}km')
    axes[0].set_xticks(x, ids); axes[0].set_ylabel('선택한 관측소까지 최대 거리 (km)')
    axes[0].set_title('새 4곳: 제한된 기상 캐시의 범위 이탈', pad=12)
    axes[0].set_ylim(0, 125); axes[0].legend(fontsize=8, loc='upper right')
    axes[0].text(.02, -.20, 'AWS 34곳·ASOS 10곳 캐시\n범위 이탈은 오차의 원인 확정이 아님', transform=axes[0].transAxes, fontsize=9)

    metrics = pd.read_csv(source / 'metric_sensitivity.csv')
    metrics = metrics.loc[metrics.domain.eq('opened4') & metrics.min_valid_slots.eq(144)]
    policies = ['original_ice', 'thermal_hgb100', 'thermal_hgb300']; xx = np.arange(3)
    for i, (handling, label, color) in enumerate([('metricwise_omit', '지표별 미정의 제외', blue), ('joint_defined_only', 'P·R 모두 정의되는 날만 (진단)', orange)]):
        rows = metrics.loc[metrics.undefined_policy.eq(handling)].set_index('prediction').loc[policies]
        bars = axes[1].bar(xx + (i - .5) * .35, rows.f1_available_station_macro, width=.35, label=label, color=color)
        axes[1].bar_label(bars, labels=[f'{r.f1_available_station_macro:.4f}\n{int(r.f1_days)}일/{int(r.f1_stations)}곳' for r in rows.itertuples()], padding=3, fontsize=8)
    axes[1].set_xticks(xx, ['기존', '온도100+수분', '온도300+수분']); axes[1].set_ylabel('일별→지점 평균 F1')
    axes[1].set_title('분모를 줄이면 점수가 크게 달라짐', pad=12); axes[1].set_ylim(0, .075)
    axes[1].legend(fontsize=8, loc='upper left')
    axes[1].text(.02, -.20, '고정 예측·동일 477개 완전일\n주황색 처리는 오경보일·완전 미탐일을 누락', transform=axes[1].transAxes, fontsize=9)

    failure = pd.read_csv(source / 'ice_temperature_failure.csv')
    bins = ['<=-2', '(-2,0]', '(0,2]', '>2']; xxx = np.arange(4)
    grouped = failure.groupby('measured_temperature_bin').sum(numeric_only=True).loc[bins]
    for i, (column, label, color) in enumerate([('ice_rows', '실제 Ice', grey), ('original_hits', '기존 탐지', blue), ('thermal100_hits', '온도100+수분 탐지', orange)]):
        bars = axes[2].bar(xxx + (i - 1) * .25, grouped[column], width=.25, label=label, color=color)
        axes[2].bar_label(bars, padding=3, fontsize=9)
    axes[2].set_xticks(xxx, ['≤-2', '(-2,0]', '(0,2]', '>2']); axes[2].set_xlabel('실측 노면온도 (°C)'); axes[2].set_ylabel('10분 시점 수')
    axes[2].set_title('실측 온도 >0°C인 Ice도 정답으로 유지', pad=12); axes[2].set_ylim(0, 47)
    axes[2].legend(fontsize=8, loc='upper right')
    axes[2].text(.02, -.20, '유효 상태 69,101행·Ice 88행\n온도100/300의 탐지 수는 이 구간에서 동일', transform=axes[2].transAxes, fontsize=9)
    for ax in axes:
        ax.set_axisbelow(True); ax.grid(axis='y', color='#e7ebef', linewidth=.8)
    figure.text(.02, .015, '개봉된 첫 겨울의 사후 진단 | 새 모델 학습·재추론 없음 | 공식 미정의 처리와 실제 센서 위치는 미확정', fontsize=10, color='#46515d')
    figure.subplots_adjust(left=.055, right=.98, top=.83, bottom=.23, wspace=.35)
    figure.savefig(target, dpi=170, facecolor='white'); plt.close(figure)
    receipt = dict(figure=str(target.relative_to(ROOT)), sha256=sha(target),
                   source_summary_sha256=sha(source / 'summary.json'))
    (source.parent / 'figure_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print('그림 저장: ' + str(target.relative_to(ROOT)))


if __name__ == '__main__':
    main()
