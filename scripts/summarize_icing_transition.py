"""결빙 전이·임계값 실험의 전체 후보표와 한눈에 보는 집계 그림을 만든다."""
import argparse
from pathlib import Path
import sys
import json
import math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_icing_transition import read, write


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', required=True, type=Path)
    out = parser.parse_args().output.resolve()
    if out.exists() or not out.is_relative_to((ROOT/'outputs/private').resolve()): raise ValueError('New private output required')
    out.mkdir(parents=True)
    paths = {'fixed':ROOT/'outputs/private/icing_transition_20261025_v1', 'exact':ROOT/'outputs/private/icing_threshold_refinement_20261025_v1'}
    audit = read(ROOT/'outputs/private/icing_transition_audit_20261025_v1/receipt.json')
    assert audit['status'] == 'icing_transition_independently_verified'
    sources = {kind:read(p/'summary.json') for kind,p in paths.items()}
    assert audit['checks']['fixed_grid']['summary_sha256'] == sha(paths['fixed']/'summary.json')
    assert audit['checks']['exact_threshold']['summary_sha256'] == sha(paths['exact']/'summary.json')
    rows = []
    for kind, study in sources.items():
        for name, result in study['reports'].items():
            r = result['all']
            rows.append(dict(search=kind, candidate=name, f1=r['f1_fixed_population'], precision=r['precision_available_station_mean'],
                recall=r['recall_available_station_mean'], winter2024_f1=result['2024']['f1_fixed_population'], winter2025_f1=result['2025']['f1_fixed_population'],
                **result['events'], eligible=result['eligible'], failed_gates=';'.join(k for k,v in result['gates'].items() if not v)))
    registry = pd.DataFrame(rows); registry.to_csv(out/'candidate_registry.csv', index=False)
    best = {}
    for kind in paths:
        candidates = registry.loc[registry.search.eq(kind)&~registry.candidate.isin(['current','asos_zero'])]
        best[kind] = candidates.sort_values(['f1','candidate'], ascending=[False,True]).iloc[0].to_dict()
    choices = [
        ('fixed','current','현재 결빙 판정'), ('fixed','asos_zero','ASOS 기온 ≤ 0°C'),
        ('fixed','selected_mean_f1','고정 격자 · 내부 평균 F1 선택'),
        ('fixed','selected_worst_winter_f1','고정 격자 · 내부 최악 겨울 선택'),
        ('exact','selected_mean_f1','모든 점수 · 내부 평균 F1 선택'),
        ('exact','selected_worst_winter_f1','모든 점수 · 내부 최악 겨울 선택'),
        ('fixed',best['fixed']['candidate'],'고정 격자 · 외부 최고값 (사후 설명)'),
        ('exact',best['exact']['candidate'],'모든 점수 · 외부 최고값 (사후 설명)')]
    display = []
    for kind, name, label in choices:
        row = registry.loc[registry.search.eq(kind)&registry.candidate.eq(name)].iloc[0].to_dict(); row['label'] = label; display.append(row)
    available_fonts = {f.name for f in font_manager.fontManager.ttflist}
    for family in ['Malgun Gothic', 'Noto Sans CJK KR', 'NanumGothic']:
        if family in available_fonts: plt.rcParams['font.family'] = family; break
    plt.rcParams['axes.unicode_minus'] = False
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 6.7), gridspec_kw={'width_ratios':[1.2,1,1]})
    colors = ['#19647e','#6b7280'] + ['#6877ba']*4 + ['#a3a9bd']*2
    for ax, metric, title in zip(axes, ['f1','precision','recall'], ['일별 지점 평균 F1','정밀도 (정의된 지점 평균)','재현율 (정의된 지점 평균)']):
        values = [float(r[metric]) if pd.notna(r[metric]) else 0. for r in display]
        ax.barh(range(len(display)), values, color=colors)
        ax.invert_yaxis(); ax.set_title(title, fontsize=11, pad=12)
        ax.set_yticks(range(len(display)), [r['label'] for r in display] if metric == 'f1' else ['']*len(display))
        ax.set_xlim(0, max(values)*1.26 if max(values)>0 else 1)
        for i, value in enumerate(values):
            label = f'{value:.4f}' if pd.notna(display[i][metric]) else '미정의'
            ax.text(value+ax.get_xlim()[1]*.02, i, label, va='center', fontsize=9)
        ax.spines[['top','right']].set_visible(False); ax.grid(axis='x', alpha=.15); ax.set_axisbelow(True)
    fig.suptitle('기상 조건부 결빙 전이와 임계값 선택: 같은 9개 지점의 반복 개발 비교', fontsize=15, x=.02, ha='left')
    fig.text(.02,.035,'지역 두 개를 제외한 내부 선택 · 두 겨울 · 입력 가용 범위 동일 | 사후 최고값은 새 독립 성능이나 채택 근거가 아님', fontsize=10, color='#475569')
    fig.tight_layout(rect=(.01,.08,.99,.94)); fig.savefig(out/'icing_transition_comparison.png', dpi=160); plt.close(fig)
    payload = dict(status='icing_transition_comparison_complete', candidate_rows=len(registry), best_descriptive=best, display=display,
                   eligible_candidates=registry.loc[registry.eligible,['search','candidate']].to_dict('records'), audit_sha256=sha(ROOT/'outputs/private/icing_transition_audit_20261025_v1/receipt.json'),
                   chart_sha256=sha(out/'icing_transition_comparison.png'), protected_labels_read=False, new_independent_assessment=False)
    def clean(value):
        if isinstance(value, dict): return {k:clean(v) for k,v in value.items()}
        if isinstance(value, list): return [clean(v) for v in value]
        return None if isinstance(value, float) and not math.isfinite(value) else value
    payload = clean(payload)
    write(out/'summary.json', payload)
    print(json.dumps({'best': best, 'eligible': payload['eligible_candidates']}, ensure_ascii=False))


if __name__ == '__main__': main()
