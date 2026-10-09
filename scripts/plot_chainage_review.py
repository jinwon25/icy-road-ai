"""연구 참조와 도형의 정합 상태를 시각화한다. 공식 이정 지도가 아니다."""
import json
from pathlib import Path
import geopandas as gpd
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT=Path(__file__).resolve().parents[1]


def main():
    private=ROOT/'outputs/private';out=private/'spatial/chainage_reference'
    checks=pd.read_csv(out/'segment_chainage_candidates.csv')
    shapes=gpd.read_file(private/'spatial/segment_scaffold/segments.gpkg')
    shapes=shapes.merge(checks,left_on='seg_id',right_on='segment_id',validate='one_to_one')
    plt.rcParams['font.family']='Malgun Gothic';plt.rcParams['axes.unicode_minus']=False
    fig,axes=plt.subplots(1,3,figsize=(12,7))
    for ax,route in zip(axes,['서해안고속국도','호남고속국도','통영-대전고속국도']):
        subset=shapes.loc[shapes.route_nm.eq(route)]
        colors=subset.chainage_status.map({'research_chainage_candidate':'#168a62','manual_geometry_review_required':'#e28232'})
        subset.plot(ax=ax,color=colors,linewidth=2.5)
        passed=subset.chainage_status.eq('research_chainage_candidate').sum()
        ax.set_title(f'{route}\n기하 검토 통과 {passed}/{len(subset)}',fontsize=12);ax.set_axis_off()
    fig.suptitle('연구 지도 참조와 제공 도로 도형의 정합성 검토',fontsize=16,y=.96)
    fig.legend(handles=[Line2D([0],[0],color='#168a62',lw=3,label='거리·길이·이정 진행 조건 통과'),Line2D([0],[0],color='#e28232',lw=3,label='수동 검토 필요')],loc='lower center',bbox_to_anchor=(.5,.135),ncol=2,frameon=False)
    fig.text(.06,.055,'공식 이정·상하행·본선/램프 판정이 아님. 참고 자료: 서울시립대 교통안전 DB 연구 지도(공개 표시 자원).\n50m 표본 간격·최대 참조거리 50m·길이 오차 max(20m,20%)·진행 역행 1m 허용은 분석자 검토 기준.\n참조의 기준 시점·재배포 조건은 미확인. 비공개 진단용이며 제출 초안에는 포함하지 않음.',fontsize=10,color='#475569')
    fig.subplots_adjust(left=.04,right=.96,top=.80,bottom=.24,wspace=.18)
    fig.savefig(out/'chainage_geometry_review.png',dpi=170);plt.close(fig)
    print(json.dumps({'segments':len(shapes),'figure':'chainage_geometry_review.png','official_alignment':False}),flush=True)


if __name__=='__main__':main()
