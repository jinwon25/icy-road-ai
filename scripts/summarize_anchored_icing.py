"""독립 검산된 제한 보정 결과를 후보표·동일 예측 진단·그림으로 요약한다."""
import argparse
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_synoptic_icing import read,write


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['study','audit','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve()
    if out.exists() or not out.is_relative_to((ROOT/'outputs/private').resolve()):raise ValueError('New private output required')
    s=read(a.study/'summary.json');audit=read(a.audit/'receipt.json')
    assert audit['status']=='anchored_icing_independently_verified' and audit['source_summary_sha256']==sha(a.study/'summary.json')
    secondary=read(a.audit/'asos_secondary_checks.json');assert sha(a.audit/'asos_secondary_checks.json')==audit['secondary_checks_sha256']
    rows=[]
    for n,r in s['reports'].items():
        m=r['all'];rows.append(dict(candidate=n,f1=m['f1_fixed_population'],precision=m['precision_available_station_mean'],
            recall=m['recall_available_station_mean'],winter2024=r['2024']['f1_fixed_population'],winter2025=r['2025']['f1_fixed_population'],
            **r['events'],**secondary[n],eligible=r['eligible'],failed_gates=';'.join(k for k,v in r['gates'].items() if not v)))
    table=pd.DataFrame(rows);out.mkdir(parents=True);table.to_csv(out/'candidate_registry.csv',index=False)
    f=pd.read_parquet(a.study/'predictions.parquet');specs=read(a.study/'policies.json');equivalent={}
    for bound in [.25,.5,1,2]:
        n=f'asos_logit_row_reject_only_{bound:g}';control=f'air_threshold_{-bound:g}'
        equivalent[n]=dict(control=control,identical=bool(np.array_equal(f[n],f[control],equal_nan=True)))
    equivalence=[]
    for n in specs:
        for group in equivalence:
            if np.array_equal(f[n],f[group[0]],equal_nan=True):group.append(n);break
        else:equivalence.append([n])
    best=table.loc[table.candidate.isin(specs)&~table.candidate.eq('asos_zero')].sort_values(['f1','candidate'],ascending=[False,True]).iloc[0]
    fonts={f.name for f in font_manager.fontManager.ttflist}
    for font in ['Malgun Gothic','Noto Sans CJK KR','NanumGothic']:
        if font in fonts:plt.rcParams['font.family']=font;break
    plt.rcParams['axes.unicode_minus']=False
    names=['current','asos_zero',best.candidate,'selected_mean_f1','selected_retention_guard']
    labels=['현재 결빙 판정','ASOS 기온 0°C 기준','사후 최고 고정 보정','내부 평균 F1 선택','내부 양성 보존 제한 선택']
    d=table.set_index('candidate').loc[names];fig,axes=plt.subplots(1,3,figsize=(15,5.5))
    for ax,col,title in zip(axes,['f1','winter2024','winter2025'],['두 겨울 통합 F1','첫 겨울 F1','둘째 겨울 F1']):
        values=d[col].to_numpy();ax.barh(np.arange(5),values,color=['#18647e','#6b7280','#b97732','#6877ba','#6877ba'])
        ax.invert_yaxis();ax.set_yticks(np.arange(5),labels if col=='f1' else ['']*5)
        ax.set_xlim(0,max(values)*1.32);ax.set_title(title);ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
        for i,v in enumerate(values):ax.text(v+max(values)*.025,i,f'{v:.5f}',va='center',fontsize=9)
    fig.suptitle('기온 기준선의 제한 보정: 일부 고정 후보의 소폭 이득은 선택 절차에서 유지되지 않음',x=.02,ha='left',fontsize=14)
    fig.text(.02,.025,'기존 개발 9지점 반복 실험 · 공식 점수 아님 | 사후 최고 후보도 첫 겨울 기준선 하락·기존 탐지 사건 4개 손실',fontsize=10)
    fig.tight_layout(rect=(0,.07,1,.92));fig.savefig(out/'anchored_icing_comparison.png',dpi=160);plt.close(fig)
    write(out/'summary.json',dict(status='anchored_icing_summary_complete',rows=len(table),unique_fixed_predictions=len(equivalence),
        equivalence_groups=equivalence,row_weighted_logit_equivalence=equivalent,
        best_fixed_descriptive=best.to_dict(),best_fixed_vs_asos_relative=float(best.f1/table.set_index('candidate').loc['asos_zero','f1']-1),
        eligible_candidates=table.loc[table.eligible,'candidate'].tolist(),
        beats_asos_and_both_winters=table.loc[table.beats_asos&table.both_winters_noninferior,'candidate'].tolist(),
        audit_sha256=sha(a.audit/'receipt.json'),files={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    print('best',best.candidate,best.f1,'unique fixed predictions',len(equivalence),'row-logit equivalent',equivalent,flush=True)


if __name__=='__main__':main()
