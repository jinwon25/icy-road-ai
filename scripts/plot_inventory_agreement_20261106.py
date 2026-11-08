"""공개 목록과 기상 기준의 불일치를 같은 분모의 막대와 실제 도로 지도에 표시한다."""
from pathlib import Path
import pandas as pd,numpy as np,geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
ROOT=Path(__file__).resolve().parents[1];B=ROOT/'outputs/private/final_jury_review_20261106/icy_road_model'
def main():
    plt.rcParams.update({'font.family':'Malgun Gothic','font.size':10,'axes.unicode_minus':False,
        'axes.spines.top':False,'axes.spines.right':False,'text.color':'#26343d','axes.labelcolor':'#26343d','svg.fonttype':'path'})
    t=pd.read_csv(B/'results/inventory/agreement/threshold_comparison.csv')
    t=t.loc[t.source.eq('2026-09-07')&t.margin_m.eq(250)].sort_values('weather_quantile')
    f=pd.read_csv(B/'results/sections/section_review.csv',dtype={'seg_id':str})
    o=pd.read_csv(B/'results/inventory/overlap_sensitivity.csv',dtype={'seg_id':str})
    listed=set(o.loc[o.version.eq('2026-09-07')&o.margin_m.eq(250)&o.nominal_overlap_km.gt(0),'seg_id'])
    selected=set(f.loc[f.inspection_candidate,'seg_id'])
    g=gpd.read_file(B/'results/sections/risk_review.gpkg',layer='winter_2024',engine='pyogrio').to_crs(5179)
    fig,(ax,geo)=plt.subplots(1,2,figsize=(8.8,4),gridspec_kw={'width_ratios':[1.65,1]})
    x=np.arange(5);width=.22
    ax.axvspan(1.5,2.5,color='#f3f0e9',zorder=0)
    for offset,col,label,color in [(-width,'nominal_high_2024','2024/25','#29546d'),(0,'nominal_high_2025','2025/26','#76a9b9'),(width,'nominal_high_both','두 겨울 모두','#94652d')]:
        bars=ax.bar(x+offset,t[col],width,color=color,label=label)
        for bar,value in zip(bars,t[col]):ax.text(bar.get_x()+width/2,value+1,str(int(value)),ha='center',va='bottom',fontsize=9)
    ax.set_xticks(x,[f'상위 {round((1-q)*100)}%' for q in t.weather_quantile])
    ax.set_ylim(0,64);ax.set_yticks([0,16,32,48,64]);ax.set_ylabel('명목상 목록과 겹치는 64구간 중 기준 충족 수')
    ax.set_title('겨울에 따라 달라지는 기상 조건',loc='left',fontsize=12,pad=12)
    ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True);ax.legend(frameon=False,fontsize=9,loc='upper right')
    g.plot(ax=geo,color='#ced9df',linewidth=1.3)
    g.loc[g.seg_id.isin(listed)].plot(ax=geo,color='#29546d',linewidth=2.8)
    g.loc[g.seg_id.isin(selected)].plot(ax=geo,color='#a66a2c',linewidth=4)
    geo.set_axis_off();geo.set_title('목록 대조와 추가 계측을 함께 표시',loc='left',fontsize=11,pad=12)
    geo.legend(handles=[Patch(color='#29546d',label='명목상 목록 중첩 64구간'),Patch(color='#a66a2c',label='추가 계측 후보 3구간')],loc='lower center',frameon=False,fontsize=8.5,bbox_to_anchor=(.5,-.06))
    fig.tight_layout(pad=1.2,w_pad=2)
    for ext in ['png','svg']:fig.savefig(B/'report/figures'/('inventory_agreement.'+ext),dpi=300,bbox_inches='tight')
    plt.close(fig)
    print('공개 목록과 기상 문턱의 관계 그림을 생성했습니다.',flush=True)
if __name__=='__main__':main()
