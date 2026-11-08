"""검산된 공간 이력의 전체·겨울·지역·입력 조건별 결과를 CSV와 그림으로 정리한다."""
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_objective_icing import read, write, now
from src.data_source import sha256_file as sha


def main():
    plan = read(ROOT/'config/weather_network_history_20261102.json'); source = ROOT/plan['output']
    s = read(source/'summary.json'); a = read(source/'independent_verification.json')
    assert a['status'] == 'passed' and a['summary_sha256'] == sha(source/'summary.json')
    out = ROOT/'outputs/private/network_history_review_20261102_v1'
    if out.exists(): raise FileExistsError('Preserve completed review')
    out.mkdir(); rows = []
    for mode, record in s['reports'].items():
        for candidate, report in record['metrics'].items():
            for level, group in [('pooled', {'all': report['pooled']}), ('winter', report['winters']),
                                 ('region', report['regions']), ('cold', {'asos_within_3c': report['cold']})]:
                for name, values in group.items():
                    rows.append(dict(mode=mode, candidate=candidate, level=level, group=name, **values))
    pd.DataFrame(rows).to_csv(out/'comparison_metrics.csv', index=False, encoding='utf-8-sig')
    f = pd.read_parquet(ROOT/plan['input']).sort_values(['station', 'time']).reset_index(drop=True)
    n = pd.read_parquet(ROOT/plan['reference']/'network_features.parquet')
    context = pd.concat([f[['station', 'time']], n[['network_wind_speed_count', 'network_wind_speed_distance_km']]], axis=1)
    diagnostics = []
    for mode in ['spatial', 'joint']:
        p = pd.read_parquet(source/mode/'predictions.parquet').merge(context, on=['station', 'time'], validate='one_to_one')
        masks = [('network_count', str(k), p.network_wind_speed_count.eq(k)) for k in range(5)]
        masks += [('observed_wind', '0_to_0.5', p.observed.lt(.5)),
                  ('observed_wind', '0.5_to_2', p.observed.ge(.5) & p.observed.lt(2)),
                  ('observed_wind', '2_to_5', p.observed.ge(2) & p.observed.lt(5)),
                  ('observed_wind', '5_and_above', p.observed.ge(5)),
                  ('hour', '06_to_18', p.time.dt.hour.ge(6) & p.time.dt.hour.lt(18)),
                  ('hour', '18_to_06', p.time.dt.hour.lt(6) | p.time.dt.hour.ge(18))]
        for dimension, group, mask in masks:
            q = p.loc[mask]
            diagnostics.append(dict(mode=mode, dimension=dimension, group=group, n=len(q),
                current_mae=float(np.abs(q.current-q.observed).mean()) if len(q) else None,
                candidate_mae=float(np.abs(q[plan['candidate']]-q.observed).mean()) if len(q) else None,
                mean_effective_distance_km=float(q.network_wind_speed_distance_km.mean()) if len(q) else None))
    pd.DataFrame(diagnostics).to_csv(out/'descriptive_slices.csv', index=False, encoding='utf-8-sig')
    plt.rcParams.update({'font.family': 'Malgun Gothic', 'axes.unicode_minus': False, 'font.size': 10})
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8))
    for mode, ax in zip(['spatial', 'joint'], axes):
        r = s['reports'][mode]['metrics']
        labels = ['전체', '첫 겨울', '둘째 겨울', '저온 입력']
        keys = [('pooled', None), ('winters', '2024'), ('winters', '2025'), ('cold', None)]
        y = np.arange(4)
        for j, (candidate, name, color) in enumerate([('current', '현 관측망 모형', '#28516a'),
                (plan['candidate'], '공간·기상 이력 추가', '#b76b35')]):
            values = [r[candidate][key]['mae'] if sub is None else r[candidate][key][sub]['mae'] for key, sub in keys]
            ax.barh(y-.18+j*.36, values, .34, color=color, label=name)
            for yy, value in zip(y-.18+j*.36, values):
                ax.text(value+.006, yy, f'{value:.4f}', va='center', fontsize=9)
        ax.set_yticks(y, labels); ax.invert_yaxis(); ax.set_xlim(0, ax.get_xlim()[1]*1.22)
        ax.set_title('지역 제외' if mode == 'spatial' else '지역·겨울 동시 제외')
        ax.set_xlabel('풍속 MAE (m/s), 낮을수록 좋음')
        ax.spines[['top', 'right']].set_visible(False); ax.grid(axis='x', alpha=.2); ax.set_axisbelow(True)
    axes[0].legend(loc='lower left', bbox_to_anchor=(0, 1.08), frameon=False, fontsize=9)
    fig.suptitle('같은 개발 4지역의 반복 비교 · 공식 성적 아님', fontsize=11, y=1.03)
    fig.tight_layout()
    figure = ROOT/'docs/images/weather_network_history_20261102.png'
    if figure.exists(): raise FileExistsError('Preserve existing figure')
    fig.savefig(figure, dpi=170, bbox_inches='tight'); plt.close(fig)
    write(out/'receipt.json', dict(status='network_history_review_complete', at_utc=now(),
        summary_sha256=sha(source/'summary.json'), audit_sha256=sha(source/'independent_verification.json'),
        metric_rows=len(rows), descriptive_rows=len(diagnostics), figure_sha256=sha(figure),
        diagnostics_used_for_selection=False, new_independent_assessment=False,
        files={p.name: sha(p) for p in out.iterdir() if p.is_file()}))
    print('REVIEW', len(rows), 'metrics,', len(diagnostics), 'descriptive slices', flush=True)


if __name__ == '__main__':
    main()
