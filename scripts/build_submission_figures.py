"""보고서의 지도·관측 대조·날짜별 판정 그림을 실제 결과에서 생성한다."""
from pathlib import Path
import sys,json
import numpy as np,pandas as pd,geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize,ListedColormap
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from matplotlib.font_manager import FontProperties
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import read,write,sha
P=ROOT/'outputs/private';B=P/'competition_submission/icy_road_model';O=B/'report/figures';W=P/'editorial_review_20261106'
BLUE='#29546D';ICE='#5B9FB3';GOLD='#AD7837';RED='#B6534D';GRAY='#727D84'
def save(fig,name):
 fig.savefig(O/(name+'.png'),dpi=240,bbox_inches='tight',facecolor='white')
 fig.savefig(O/(name+'.svg'),bbox_inches='tight',facecolor='white')
 plt.close(fig)
def style():
 plt.rcParams.update({'font.family':FontProperties(fname='C:/Windows/Fonts/malgun.ttf').get_name(),'axes.unicode_minus':False,'font.size':10,'axes.titlesize':12,'axes.labelsize':10,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#C4CCD0','text.color':'#26343D','axes.labelcolor':'#26343D','xtick.color':'#536069','ytick.color':'#536069','figure.constrained_layout.use':True})
def main():
 O.mkdir(parents=True,exist_ok=True);style()
 source=P/'wind_network_segment_projection_20261102_v1/weather_segments.gpkg'
 geo=gpd.read_file(source,layer='winter_2024')[['seg_id','geometry']]
 boundary=gpd.read_file(P/'segment_exposure_20261009_v1/boundary.gpkg').to_crs(geo.crs)
 risk=pd.read_csv(B/'results/sections/section_review.csv',float_precision='round_trip')
 weather=pd.read_csv(B/'results/weather/weather_segments_500m.csv',float_precision='round_trip')
 road=geo.merge(risk.loc[risk.winter.eq(2024),['seg_id','route_nm']],on='seg_id',validate='one_to_one')
 bounds=geo.total_bounds;pad=9000
 def base(ax):
  boundary.plot(ax=ax,facecolor='#F0F3F4',edgecolor='#D4DCE0',linewidth=.6)
  ax.set_xlim(bounds[0]-pad,bounds[2]+pad);ax.set_ylim(bounds[1]-pad,bounds[3]+pad);ax.set_axis_off()
 def bar(ax):
  x=bounds[0]+2500;y=bounds[1]+3000
  ax.plot([x,x+20000],[y,y],color='#52616B',lw=1.2);ax.text(x+10000,y+2200,'20 km',ha='center',fontsize=7,color='#64717A')
 def labels(ax):
  for route,q in road.groupby('route_nm'):
   x=q.geometry.centroid.x.mean();y=q.geometry.centroid.y.mean()
   dx=-18000 if route.startswith('서해안') else (-7000 if route.startswith('통영') else 14000)
   name=route.replace('고속국도','').replace('통영-대전','통영-대전')
   ax.annotate(name,(x,y),xytext=((bounds[0]+1500) if route.startswith('서해안') else x+dx,y+9000),ha='left' if route.startswith('서해안') or dx>0 else 'right',fontsize=8,color='#52616B',arrowprops=dict(arrowstyle='-',color='#96A3AA',lw=.7))
 fig,ax=plt.subplots(figsize=(6.2,5.5));base(ax)
 palette={'서해안고속국도':BLUE,'호남고속국도':ICE,'통영-대전고속국도':GOLD}
 for route,q in road.groupby('route_nm'):q.plot(ax=ax,color=palette[route],linewidth=2.8)
 labels(ax);bar(ax);ax.text(bounds[2]+5000,bounds[3]-7000,'N',ha='center',fontsize=9);ax.annotate('',(bounds[2]+5000,bounds[3]-2000),(bounds[2]+5000,bounds[3]-6000),arrowprops=dict(arrowstyle='-|>',color='#52616B'))
 save(fig,'study_area')
 # 회귀 결과는 전체 관측쌍의 밀도와 일치선으로 표현한다.
 f=pd.read_csv(B/'results/evaluation/observations_predictions.csv',dtype={'station_id':str},float_precision='round_trip')
 names={'12410':'부곡교','23402':'해전','33411':'삼봉'}
 fig,axes=plt.subplots(1,3,figsize=(11.2,3.5),sharex=True,sharey=True)
 cmap=matplotlib.colors.LinearSegmentedColormap.from_list('ice_density',['#E9F2F5','#84B5C4',BLUE])
 for ax,(sid,q) in zip(axes,f.groupby('station_id',sort=True)):
  q=q.dropna(subset=['observed_road_temperature_c','estimated_road_temperature_c'])
  ax.hexbin(q.observed_road_temperature_c,q.estimated_road_temperature_c,gridsize=45,mincnt=1,bins='log',cmap=cmap)
  ax.plot([-15,35],[-15,35],color=GOLD,lw=1,linestyle='--');ax.set_xlim(-15,35);ax.set_ylim(-15,35);ax.set_aspect('equal')
  ax.set_title(f'{names[sid]}  ({sid})');ax.set_xlabel('관측 노면온도 (°C)');ax.grid(alpha=.15)
  ax.text(.04,.94,f'n = {len(q):,}',transform=ax.transAxes,va='top',fontsize=9)
 axes[0].set_ylabel('추정 노면온도 (°C)');save(fig,'road_temperature')
 # 두 겨울 지도는 같은 범례와 색 범위를 공유한다.
 fig,axes=plt.subplots(1,2,figsize=(8.8,5.7))
 for ax,year in zip(axes,[2024,2025]):
  base(ax);q=geo.merge(weather.loc[weather.winter.eq(year),['seg_id','wind_speed_mean']],on='seg_id',validate='one_to_one')
  q.plot(ax=ax,column='wind_speed_mean',cmap='YlGnBu',vmin=.5,vmax=2.5,linewidth=2.5);labels(ax);bar(ax);ax.set_title(f'{year}/{str(year+1)[-2:]} 겨울')
 sm=plt.cm.ScalarMappable(norm=Normalize(.5,2.5),cmap='YlGnBu');fig.colorbar(sm,ax=axes,orientation='horizontal',shrink=.66,pad=.01,label='평균 풍속 (m/s)',ticks=[.5,1,1.5,2,2.5])
 save(fig,'wind_distribution')
 fig,axes=plt.subplots(1,2,figsize=(8.8,5.7))
 for ax,year in zip(axes,[2024,2025]):
  base(ax);q=geo.merge(risk.loc[risk.winter.eq(year),['seg_id','weather_index_100']],on='seg_id',validate='one_to_one')
  q.plot(ax=ax,column='weather_index_100',cmap='YlOrBr',vmin=0,vmax=20,linewidth=2.5);bar(ax);ax.set_title(f'{year}/{str(year+1)[-2:]} 겨울')
 fig.colorbar(plt.cm.ScalarMappable(norm=Normalize(0,20),cmap='YlOrBr'),ax=axes,orientation='horizontal',shrink=.66,pad=.01,label='저온·수분 조건 비율 (%)',ticks=[0,5,10,15,20])
 save(fig,'condition_exposure')
 fig,axes=plt.subplots(1,2,figsize=(8.8,5.7));color={0:'#8F979C',1:'#D8DFE2',2:'#CED8DE',3:'#C69650',4:RED}
 for ax,year in zip(axes,[2024,2025]):
  base(ax);q=geo.merge(risk.loc[risk.winter.eq(year),['seg_id','review_code']],on='seg_id',validate='one_to_one')
  for code,v in q.groupby('review_code'):v.plot(ax=ax,color=color[int(code)],linewidth=2.8 if code==4 else 2.2,zorder=3 if code==4 else 2)
  bar(ax);ax.set_title(f'{year}/{str(year+1)[-2:]} 겨울')
 fig.legend(handles=[Line2D([0],[0],color=color[2],lw=3,label='분석 구간'),Line2D([0],[0],color=color[3],lw=3,label='저온·수분 빈도 높음'),Line2D([0],[0],color=color[4],lw=3,label='빈도 높음 + 도로환경 확인')],loc='outside lower center',ncol=3,frameon=False,fontsize=9)
 save(fig,'section_review')
 route=pd.read_csv(B/'results/sections/route_summary.csv')
 order=['서해안고속국도','통영-대전고속국도','호남고속국도']
 fig,ax=plt.subplots(figsize=(9,2.8))
 for i,name in enumerate(order):
  vals=route.loc[route.route.eq(name)].sort_values('winter').exposure_pct.to_numpy()
  ax.plot(vals,[i,i],color='#C3CCD1',lw=2,zorder=1)
  for j,(value,col) in enumerate(zip(vals,[BLUE,GOLD])):
   ax.scatter(value,i,color=col,s=65,zorder=3);ax.annotate(f'{value:.1f}%',(value,i),xytext=(0,10 if j==0 else -18),textcoords='offset points',ha='center',fontsize=10,color=col)
 ax.set_yticks(range(3),['서해안','통영-대전','호남']);ax.set_xlim(0,20);ax.set_ylim(-.65,2.65);ax.invert_yaxis();ax.set_xlabel('노선별 길이 가중 저온·수분 조건 비율 (%)');ax.grid(axis='x',alpha=.2)
 ax.legend(handles=[Line2D([],[],marker='o',ls='',color=BLUE,label='2024/25'),Line2D([],[],marker='o',ls='',color=GOLD,label='2025/26')],frameon=False,ncol=2,loc='upper right')
 save(fig,'route_exposure')
 # 결빙일 달력: 두 겨울을 각각 같은 120일 축으로 표시한다.
 q=f.loc[f.station_id.eq('12410')].copy();q['time']=pd.to_datetime(q.prediction_time_kst);q['date']=q.time.dt.normalize()
 days=q.groupby('date').agg(observed=('observed_ice',lambda s:bool(s.eq(1).any())),predicted=('predicted_ice',lambda s:bool(s.eq(1).any())))
 image=np.zeros((4,120))
 counts=[]
 for i,year in enumerate([2024,2025]):
  calendar=pd.date_range(f'{year}-11-01',periods=120,freq='D');part=days.reindex(calendar,fill_value=False)
  image[2*i]=part.observed.to_numpy();image[2*i+1]=part.predicted.to_numpy()
  counts.append(dict(winter=year,observed_days=int(part.observed.sum()),predicted_days=int(part.predicted.sum()),missed_days=int((part.observed&~part.predicted).sum()),false_alarm_days=int((~part.observed&part.predicted).sum())))
 fig,ax=plt.subplots(figsize=(10.5,2.6))
 ax.imshow(image,aspect='auto',interpolation='none',cmap=ListedColormap(['#EDF1F3',BLUE]),vmin=0,vmax=1)
 ax.set_yticks(range(4),['2024/25 관측','2024/25 판정','2025/26 관측','2025/26 판정']);ax.set_xticks([0,30,61,92,119],['11월 1일','12월 1일','1월 1일','2월 1일','2월 28일'])
 for x in [30,61,92]:ax.axvline(x-.5,color='white',lw=2)
 ax.axhline(1.5,color='white',lw=7);ax.tick_params(axis='both',length=0);ax.spines[['left','bottom']].set_visible(False)
 save(fig,'icing_calendar');pd.DataFrame(counts).to_csv(B/'results/evaluation/icing_day_counts.csv',index=False,encoding='utf-8-sig')
 # 공식 목록 비교는 기준일과 추정 위치의 차이를 유지한다.
 copy_source=ROOT/'docs/images/inventory_comparison_20261031_v3.png'
 from shutil import copy2
 copy2(copy_source,O/'inventory_comparison.png')
 corridors=pd.read_csv(P/'official_inventory_viewer_20261031_v1/corridors.csv')
 corridors.to_csv(B/'results/inventory/inspection_corridors.csv',index=False,encoding='utf-8-sig')
 write(W/'figures_layout_checked.json',dict(files={p.name:sha(p) for p in O.iterdir() if p.is_file()},icing_day_counts=counts,source_values_changed=False))
 print('FIGURES BUILT',len(list(O.glob('*.png'))),'figures;',counts,flush=True)
if __name__=='__main__':main()
