"""검산된 추가 기상 실험의 전체 후보표와 미탐 원인 그림을 만든다."""
import argparse
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_synoptic_icing import read,write


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['study','audit','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve()
    if out.exists() or not out.is_relative_to((ROOT/'outputs/private').resolve()):raise ValueError('New private output required')
    s=read(a.study/'summary.json');audit=read(a.audit/'receipt.json')
    assert audit['status']=='synoptic_icing_independently_verified' and audit['summary_sha256']==sha(a.study/'summary.json')
    gap=read(ROOT/'outputs/private/icing_gap_diagnosis_20261025_v1/summary.json')
    assert audit['diagnostic_sha256']==sha(ROOT/'outputs/private/icing_gap_diagnosis_20261025_v1/summary.json')
    out.mkdir(parents=True);rows=[]
    for name,r in s['reports'].items():
        m=r['all'];rows.append(dict(candidate=name,f1=m['f1_fixed_population'],precision=m['precision_available_station_mean'],
            recall=m['recall_available_station_mean'],winter2024_f1=r['2024']['f1_fixed_population'],winter2025_f1=r['2025']['f1_fixed_population'],
            **r['events'],eligible=r['eligible'],failed_gates=';'.join(k for k,v in r['gates'].items() if not v)))
    registry=pd.DataFrame(rows);registry.to_csv(out/'candidate_registry.csv',index=False)
    candidates=registry.loc[~registry.candidate.isin(['current','asos_zero'])]
    best=candidates.sort_values(['f1','candidate'],ascending=[False,True]).iloc[0].to_dict()
    fonts={f.name for f in font_manager.fontManager.ttflist}
    for font in ['Malgun Gothic','Noto Sans CJK KR','NanumGothic']:
        if font in fonts:plt.rcParams['font.family']=font;break
    plt.rcParams['axes.unicode_minus']=False
    labels={'current':'현재 결빙 판정','asos_zero':'ASOS 기온 ≤ 0°C','selected_mean_f1':'내부 평균 F1로 방법 선택',
            'selected_worst_winter_f1':'내부 최악 겨울 F1로 선택',best['candidate']:'사후 최고: '+{'air_wet_72h':'기온 + 72시간 수분'}.get(best['candidate'],best['candidate'])}
    # 기준선·선택 절차가 사후 최고와 같아도 명시적으로 한 행만 표시한다.
    display=registry.set_index('candidate').loc[list(labels)].reset_index()
    fig,axes=plt.subplots(1,3,figsize=(16,5.6),gridspec_kw={'width_ratios':[1.2,1,1]})
    for ax,metric,title in zip(axes,['f1','precision','recall'],['일별 지점 평균 F1','정밀도','재현율']):
        values=display[metric].fillna(0);ax.barh(range(len(display)),values,color=['#18647e','#6b7280']+['#6877ba']*(len(display)-2))
        ax.set_yticks(range(len(display)),[labels[n] for n in display.candidate] if metric=='f1' else ['']*len(display));ax.invert_yaxis()
        ax.set_xlim(0,max(values)*1.25);ax.set_title(title);ax.spines[['top','right']].set_visible(False)
        for i,v in enumerate(values):ax.text(v+ax.get_xlim()[1]*.02,i,f'{v:.4f}',va='center',fontsize=9)
        ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    fig.suptitle('추가 ASOS 관측 · 날짜 균형 · 상호작용 제한의 비교',x=.02,ha='left',fontsize=15)
    fig.text(.02,.025,'같은 9개 개발 지점 · 두 겨울 · 지역 이중 제외 선택 | 사후 최고값은 독립 평가나 자동 채택 근거가 아님',fontsize=10)
    fig.tight_layout(rect=(0,.07,1,.93));fig.savefig(out/'synoptic_icing_comparison.png',dpi=160);plt.close(fig)
    d=pd.DataFrame(gap['decomposition']);fig,axes=plt.subplots(1,2,figsize=(13,5.6),gridspec_kw={'width_ratios':[1,1.25]})
    missed=[gap['disagreement_totals'][key]['positive'] for key in ['air_only_temperature','air_only_water']]
    axes[0].barh(['노면온도 조건에서 제외','수분 조건에서 제외'],missed,color=['#487ca8','#d88648'])
    for i,v in enumerate(missed):axes[0].text(v+45,i,f'{v:,}행',va='center')
    axes[0].set_xlim(0,3300);axes[0].set_title('기온 기준선이 찾았지만 현재 판정이 놓친 결빙')
    axes[0].set_xlabel('유효 결빙 관측 행 수 · 사건 수와 다름')
    axes[1].barh(d.station,d.delta_f1,color=['#b25151' if v<0 else '#3f8b78' for v in d.delta_f1]);axes[1].axvline(0,color='#555',lw=.8)
    axes[1].set_title('지점별 F1 차이: 현재 판정 - 기온 기준선');axes[1].set_xlabel('음수이면 현재 판정이 낮음')
    for ax in axes:ax.spines[['top','right']].set_visible(False);ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    fig.suptitle('오경보 감소와 미탐 증가가 함께 발생하며, 전체 F1 차이는 33408의 손실이 지배',x=.02,ha='left',fontsize=13)
    fig.text(.02,.025,'관측으로 확인한 계산상 원인 분해이며 센서 오류·제설의 인과관계를 확정하지 않음',fontsize=10)
    fig.tight_layout(rect=(0,.07,1,.92));fig.savefig(out/'icing_baseline_gap.png',dpi=160);plt.close(fig)
    write(out/'summary.json',dict(status='synoptic_icing_summary_complete',candidate_rows=len(registry),best_descriptive=best,
        eligible_candidates=registry.loc[registry.eligible,'candidate'].tolist(),study_sha256=sha(a.study/'summary.json'),
        audit_sha256=sha(a.audit/'receipt.json'),files={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    print(registry.to_string(index=False))


if __name__=='__main__':main()
