"""서해안의 두 계측 검토 범위와 공개 목록을 실제 이정·도로 선형으로 표시한다."""
from pathlib import Path
import sys
import pandas as pd,numpy as np,geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.seal_protected_weather_20261106 import W
B=W/'icy_road_model'

def main():
    plt.rcParams.update({'font.family':'Malgun Gothic','font.size':11,'axes.unicode_minus':False,
        'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'path'})
    areas=pd.read_csv(B/'results/sections/inspection_areas.csv')
    f=pd.read_csv(B/'results/sections/section_review.csv',dtype={'seg_id':str})
    geometry=gpd.read_file(B/'results/weather/weather_segments.gpkg',layer='winter_2024')[['seg_id','geometry']].to_crs(5179)
    selected=geometry.merge(f.loc[f.winter.eq(2024)&f.inspection_candidate],on='seg_id',validate='one_to_one')
    selected=gpd.GeoDataFrame(selected,geometry='geometry',crs=geometry.crs)
    fig,axes=plt.subplots(1,2,figsize=(8.8,3.5),gridspec_kw={'width_ratios':[.85,1.4]})
    geometry.plot(ax=axes[0],color='#c3d0d7',linewidth=1.5)
    selected.plot(ax=axes[0],color='#b6534d',linewidth=3.5)
    lo,bot,hi,top=selected.total_bounds;pad=2500
    axes[0].set_xlim(lo-pad,hi+pad);axes[0].set_ylim(bot-pad,top+pad)
    for i,a in areas.iterrows():
        point=selected.loc[selected.inspection_area_id.eq(a.area_id)].geometry.iloc[0].interpolate(.5,normalized=True)
        axes[0].annotate(a.area_id,(point.x,point.y),xytext=(7,-11 if i==0 else 7),textcoords='offset points',fontsize=11,color='#9b403b')
    axes[0].plot([lo-pad+600,lo-pad+2600],[bot-pad+500]*2,color='#61717a',lw=1.5)
    axes[0].text(lo-pad+1600,bot-pad+850,'2km',ha='center',fontsize=9,color='#61717a')
    axes[0].set_axis_off();axes[0].set_title('서해안 검토 범위 확대',loc='left',fontsize=12,pad=12)
    directions=sorted(f.loc[f.route_nm.eq('서해안고속국도'),'flow_lbl'].unique())
    inventory=pd.read_csv(B/'results/inventory/inventory_mapping.csv')
    inv=inventory.loc[inventory.route_nm.eq('서해안고속국도')]
    for i,direction in enumerate(directions):
        for r in inv.itertuples():
            if str(r.direction) not in ['양방향','방향 미기재','문제 표 미기재',direction] and pd.notna(r.direction):continue
            left=max(float(r.start_km),76);right=min(float(r.end_km),101)
            if left<right:axes[1].broken_barh([(left,right-left)],(i-.26,.14),facecolors='#29546d' if str(r.source_date)=='2026-09-07' else '#ccd5da')
        for r in areas.loc[areas.direction.eq(direction)].itertuples():
            axes[1].broken_barh([(r.estimated_km_start,r.estimated_km_end-r.estimated_km_start)],(i-.03,.25),facecolors='#b6534d')
            axes[1].text((r.estimated_km_start+r.estimated_km_end)/2,i+.32,r.area_id,ha='center',color='#9b403b',fontsize=10)
    axes[1].set_yticks(range(len(directions)),[r.split('→')[-1].replace('군-','·').replace('군','')+' 방향' for r in directions],fontsize=10)
    axes[1].set_xlim(76,101);axes[1].set_ylim(-.65,len(directions)-.2);axes[1].set_xlabel('추정 이정 (km)')
    axes[1].set_title('공개 목록과 두 검토 범위',loc='left',fontsize=12,pad=12);axes[1].grid(axis='x',alpha=.2)
    axes[1].spines[['left']].set_visible(False);axes[1].tick_params(axis='y',length=0)
    fig.legend(handles=[Patch(color='#ccd5da',label='문제 표'),Patch(color='#29546d',label='공개 목록 2026.09.07'),Patch(color='#b6534d',label='계측·시설 확인')],frameon=False,ncol=3,loc='lower center',fontsize=10)
    fig.subplots_adjust(left=.01,right=.99,top=.84,bottom=.23,wspace=.35)
    for ext in ['png','svg']:fig.savefig(B/'report/figures'/('inspection_locations.'+ext),dpi=300,bbox_inches='tight',facecolor='white')
    plt.close(fig);print('서해안 S01·S02의 세 구간과 목록 비교 도표 완료')

if __name__=='__main__':main()
