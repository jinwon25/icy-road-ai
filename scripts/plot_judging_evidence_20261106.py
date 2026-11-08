"""같은 분모·고정 축·근거 자료를 갖춘 비교 도표를 만든다."""
from pathlib import Path
import sys,json
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.patches import Rectangle
from matplotlib import font_manager
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.seal_protected_weather_20261106 import W,write
from src.solar_terrain import solar_position
from src.data_source import sha256_file as sha
B=W/'icy_road_model';F=B/'report/figures'

def save(fig,name):
    fig.savefig(F/(name+'.png'),dpi=300,facecolor='white',bbox_inches='tight')
    fig.savefig(F/(name+'.svg'),facecolor='white',bbox_inches='tight')
    plt.close(fig)

def main():
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname='C:/Windows/Fonts/malgun.ttf').get_name(),
        'font.size':11,'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False,
        'text.color':'#26343d','axes.labelcolor':'#26343d','axes.edgecolor':'#aab8c0',
        'svg.fonttype':'path','pdf.fonttype':42})
    metrics=pd.read_csv(W/'temperature_benchmarks/metrics.csv')
    names={'asos_air_reference':'ASOS 기온','aws_air_reference':'AWS 우선 기온','asos_ground_reference':'ASOS 지면온도',
        'weather12_regression':'12특성 회귀','estimated':'현재 63특성 회귀'}
    order=list(names);fig,axes=plt.subplots(1,2,figsize=(8.8,3.5),sharex=True,sharey=True)
    for ax,scope,title in zip(axes,['all_temperature','near_freezing_observed_pm2c'],['전체 온도 범위 · 103,131쌍','관측 -2~+2°C · 23,545쌍']):
        q=metrics.loc[metrics.temperature_scope.eq(scope)&metrics.station.eq('station_macro')&metrics.period.eq('all')].set_index('method').loc[order]
        values=q.mae.to_numpy()
        ax.barh(np.arange(5),values,color=['#becbd2','#becbd2','#becbd2','#7e9dad','#29546d'],height=.55)
        ax.set_title(title,fontsize=11,pad=13);ax.set_xlim(0,3.25);ax.grid(axis='x',alpha=.17);ax.set_axisbelow(True)
        ax.set_xlabel('지점 평균 MAE (°C)');ax.set_yticks(np.arange(5),[names[x] for x in order]);ax.tick_params(axis='y',length=0)
        for i,v in enumerate(values):ax.text(v+.055,i,f'{v:.3f}',va='center',fontsize=10)
    axes[0].invert_yaxis();fig.tight_layout(w_pad=2)
    save(fig,'temperature_benchmarks')

    scenarios=pd.read_csv(B/'results/sections/sensitivity/scenario_summary.csv')
    fig,axes=plt.subplots(1,3,figsize=(8.8,3.5),sharex=True,sharey=True)
    quantiles=[.6,.7,.75,.8,.9];norm=Normalize(0,86);image=None
    for ax,m in zip(axes,[100,250,500]):
        matrix=scenarios.loc[scenarios.margin_m.eq(m)].pivot(index='weather_quantile',columns='curve_quantile',values='selected_segments').loc[quantiles,quantiles].to_numpy()
        image=ax.imshow(matrix,cmap='Blues',norm=norm,aspect='equal')
        ax.set_title(f'목록 경계 ±{m}m',fontsize=11,pad=12);ax.set_xticks(range(5),[40,30,25,20,10]);ax.set_yticks(range(5),[40,30,25,20,10])
        ax.set_xlabel('선형 변화 상위 (%)',fontsize=10)
        for i in range(5):
            for j in range(5):
                rgb=plt.get_cmap('Blues')(norm(matrix[i,j]))[:3]
                linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
                luminance=sum(a*b for a,b in zip(linear,[.2126,.7152,.0722]))
                ax.text(j,i,str(matrix[i,j]),ha='center',va='center',fontsize=11,color='black' if luminance>.179 else 'white')
        if m==250:ax.add_patch(Rectangle((1.5,1.5),1,1,fill=False,edgecolor='#ad7837',linewidth=2.2))
        for spine in ax.spines.values():spine.set_visible(False)
    axes[0].set_ylabel('기상 노출 상위 (%)',fontsize=10)
    fig.subplots_adjust(left=.08,right=.99,top=.84,bottom=.22,wspace=.15)
    save(fig,'selection_sensitivity')

    conditions=pd.read_csv(W/'condition_evidence/development_observed_ice_by_condition.csv')
    bins=['<=-2','(-2,0]','(0,2]','>2'];bin_labels=['-2°C 이하','-2~0°C','0~2°C','2°C 초과']
    fig,ax=plt.subplots(figsize=(8.8,3.35))
    for j,(moisture,label,col) in enumerate([('not_detected','수분 대용조건 미검출','#97aebc'),('present','수분 대용조건 있음','#29546d')]):
        q=conditions.loc[conditions.moisture_proxy.eq(moisture)].set_index('temperature_bin').loc[bins]
        rate=100*q.pooled_observed_ice_fraction.to_numpy();x=np.arange(4)+(j-.5)*.34
        ax.bar(x,rate,width=.3,label=label,color=col)
        for xx,yy,n in zip(x,rate,q.valid_pairs):ax.text(xx,yy+.17,f'{yy:.1f}%',ha='center',fontsize=10)
    ax.set_ylim(0,8.8);ax.set_ylabel('실제 Ice 관측 비율 (%)');ax.set_xlabel('지역 제외 예측의 기준온도 Tref')
    ax.set_xticks(range(4),bin_labels);ax.grid(axis='y',alpha=.17);ax.set_axisbelow(True)
    ax.legend(frameon=False,loc='upper right',fontsize=10);fig.tight_layout()
    save(fig,'observed_ice_conditions')

    terrain=pd.read_csv(W/'terrain_context/segment_terrain.csv',dtype={'seg_id':str},float_precision='round_trip')
    solar=pd.read_csv(W/'terrain_context/segment_solar_context.csv',dtype={'seg_id':str},float_precision='round_trip')
    sections=pd.read_csv(B/'results/sections/section_review.csv',dtype={'seg_id':str},float_precision='round_trip')
    road=gpd.read_file(B/'results/weather/weather_segments.gpkg',layer='winter_2024')[['seg_id','geometry']].to_crs(5179)
    road=road.merge(solar.loc[solar.winter.eq(2024),['seg_id','potential_shade_daylight_fraction']],on='seg_id',validate='one_to_one')
    boundary=gpd.read_file(ROOT/'outputs/private/segment_exposure_20261009_v1/boundary.gpkg').to_crs(5179)
    fig=plt.figure(figsize=(8.8,5.7));grid=fig.add_gridspec(2,2,width_ratios=[1.05,1.15],hspace=.5,wspace=.35)
    ax=fig.add_subplot(grid[:,0]);boundary.plot(ax=ax,facecolor='#f1f4f5',edgecolor='#c2cfd6',linewidth=.45)
    road.plot(ax=ax,color='#aebdc8',linewidth=3.1)
    road.plot(ax=ax,column='potential_shade_daylight_fraction',cmap='Purples',vmin=0,vmax=.6,linewidth=2.)
    ax.set_axis_off();ax.set_aspect('equal');ax.set_title('낮의 지형 차폐 가능 비율',fontsize=12,pad=10)
    colorbar=fig.colorbar(plt.cm.ScalarMappable(norm=Normalize(0,.6),cmap='Purples'),cax=fig.add_axes([.07,.105,.32,.02]),orientation='horizontal')
    colorbar.set_ticks([0,.2,.4,.6],labels=['0%','20%','40%','60%'])
    examples=[]
    for i,area in enumerate(['S01','S02']):
        example=sections.loc[sections.winter.eq(2024)&sections.inspection_area_id.eq(area)].sort_values('estimated_km_lo').iloc[0]
        t=terrain.set_index('seg_id').loc[example.seg_id];s=solar.loc[solar.seg_id.eq(example.seg_id)&solar.winter.eq(2024)].iloc[0]
        point=gpd.GeoSeries(gpd.points_from_xy([t.point_lon],[t.point_lat]),crs=4326).to_crs(5179).iloc[0]
        ax.scatter(point.x,point.y,s=27,color='#ad7837',edgecolors='white',linewidth=.8,zorder=5)
        ax.annotate(area,(point.x,point.y),xytext=(7,-10 if i==0 else 7),textcoords='offset points',fontsize=10,color='#795221',bbox=dict(facecolor='white',alpha=.85,edgecolor='none',pad=1))
        horizon=np.array([t[f'horizon_{k:02d}_deg'] for k in range(16)]);az=np.r_[np.arange(0,360,22.5),360];height=np.r_[horizon,horizon[0]]
        sub=fig.add_subplot(grid[i,1]);sub.fill_between(az,height,color='#b4bbc8',alpha=.7,label='DSM 지평선')
        times=pd.date_range('2024-12-21',periods=144,freq='10min');altitude,bearing=solar_position(times,t.point_lat,t.point_lon);day=altitude>0
        sub.plot(bearing[day],altitude[day],color='#ad7837',linewidth=2,label='동지 태양 경로')
        sub.set_xlim(90,270);sub.set_ylim(0,65);sub.set_xticks([90,135,180,225,270],['동','135°','남','225°','서'])
        sub.set_yticks([0,20,40,60]);sub.set_ylabel('고도각 (°)',fontsize=10);sub.tick_params(labelsize=10)
        sub.set_title(f"{area} 중점 · 차폐 가능 낮 {s.potential_shade_daylight_fraction*100:.1f}%",loc='left',fontsize=11,pad=8)
        sub.grid(axis='y',alpha=.15);sub.set_axisbelow(True)
        if i==0:sub.legend(frameon=False,fontsize=9,loc='upper right')
        else:sub.set_xlabel('방위각 · 북쪽 0°, 남쪽 180°',fontsize=10)
        examples.append(dict(area=area,seg_id=example.seg_id,elevation_m=t.dsm_elevation_m,sky_view_proxy=t.sky_view_proxy,
            shade_fraction_2024=s.potential_shade_daylight_fraction,shade_fraction_1km_2024=s.potential_shade_daylight_fraction_1km,
            geometric_direct_horizontal_loss_fraction=s.geometric_direct_horizontal_loss_fraction))
    fig.subplots_adjust(left=.05,right=.99,top=.91,bottom=.17);save(fig,'terrain_solar_context')
    pd.DataFrame(examples).to_csv(F/'terrain_examples.csv',index=False,encoding='utf-8-sig')
    paths=[W/'temperature_benchmarks/metrics.csv',B/'results/sections/sensitivity/scenario_summary.csv',
        W/'condition_evidence/development_observed_ice_by_condition.csv',W/'terrain_context/segment_terrain.csv',W/'terrain_context/segment_solar_context.csv']
    receipt=W/'new_figures.json'
    if receipt.exists():
        saved=W/'new_figures_first_render.json';assert not saved.exists();receipt.replace(saved)
    write(receipt,dict(status='rendered_pending_visual_review',names=['temperature_benchmarks','selection_sensitivity','observed_ice_conditions','terrain_solar_context'],
        examples=examples,sources={p.relative_to(W).as_posix():sha(p) for p in paths}))
    print('신규 근거 도표 4개와 원자료 연결 완료',flush=True)

if __name__=='__main__':main()
