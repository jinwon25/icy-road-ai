"""점검 범위와 공개 취약구간 목록을 이정 축에 함께 표시한다."""
from pathlib import Path
import sys
import pandas as pd,numpy as np,geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.build_submission_figures import style,BLUE,RED,GRAY
P=ROOT/'outputs/private';B=P/'competition_submission/icy_road_model';O=B/'report/figures'
def main():
 style();areas=pd.read_csv(B/'results/sections/inspection_areas.csv');sections=pd.read_csv(B/'results/sections/section_review.csv')
 inv=pd.read_csv(P/'vulnerability_map_comparison_20261031_v1/inventory_mapping.csv')
 fig,axes=plt.subplots(2,1,figsize=(10.4,5.3),gridspec_kw={'height_ratios':[1.35,1]})
 for ax,route,limits in zip(axes,['호남고속국도','서해안고속국도'],[(116,132),(78,86)]):
  q=areas.loc[areas.route.eq(route)];directions=sorted(q.direction.unique())
  old=inv.loc[inv.route_nm.eq(route)&inv.candidate_segments.gt(0)]
  for y,direction in enumerate(directions):
   for _,r in old.iterrows():
    if str(r.direction) not in ['양방향','방향 미기재','문제 표 미기재',direction] and pd.notna(r.direction):continue
    current=str(r.version)=='2026-09-07';lo=max(float(r.start_km),limits[0]);hi=min(float(r.end_km),limits[1])
    if lo<hi:ax.broken_barh([(lo,hi-lo)],(y-.27,.14),facecolors=BLUE if current else '#CCD5DA')
   for _,r in q.loc[q.direction.eq(direction)].iterrows():
    ax.broken_barh([(r.estimated_km_start,r.estimated_km_end-r.estimated_km_start)],(y-.03,.25),facecolors=RED)
    ax.text((r.estimated_km_start+r.estimated_km_end)/2,y+.30,r.area_id,ha='center',fontsize=8,color=RED)
  ax.set_xlim(*limits);ax.set_ylim(-.6,len(directions)-.35);ax.set_yticks(range(len(directions)),[x.replace('서천군-군산시','서천·군산').replace('고창군-영광군','고창·영광') for x in directions]);ax.set_xlabel('추정 이정 (km)')
  ax.set_title(route.replace('고속국도','고속도로'),loc='left',fontsize=12);ax.grid(axis='x',alpha=.2);ax.spines[['left','top','right']].set_visible(False);ax.tick_params(axis='y',length=0)
 fig.legend(handles=[Patch(color='#CCD5DA',label='문제 표의 취약구간'),Patch(color=BLUE,label='공개 취약구간 (2026.09.07)'),Patch(color=RED,label='추가 계측·시설 확인 범위')],ncol=3,loc='outside lower center',frameon=False,fontsize=9)
 fig.savefig(O/'inspection_locations.png',dpi=240,bbox_inches='tight');fig.savefig(O/'inspection_locations.svg',bbox_inches='tight');plt.close(fig)
 # 새 CSV와 GIS에서 점검 범위를 같은 키로 찾을 수 있도록 한다.
 geo=gpd.read_file(P/'wind_network_segment_projection_20261102_v1/weather_segments.gpkg',layer='winter_2024')[['seg_id','geometry']]
 selected=sections.loc[sections.winter.eq(2024)&sections.inspection_candidate].copy()
 selected=geo.merge(selected,on='seg_id',validate='one_to_one');target=B/'results/sections/inspection_locations.gpkg'
 
 if not target.exists():selected.to_file(target,layer='inspection_segments',driver='GPKG',engine='pyogrio')
 print('INSPECTION FIGURE',len(selected),'segments',flush=True)
if __name__=='__main__':main()
