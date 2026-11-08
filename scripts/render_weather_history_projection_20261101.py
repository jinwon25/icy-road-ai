"""검산된 500m 기상 추정 분포를 두 겨울 동일 색 척도로 시각화한다."""
from pathlib import Path
import sys
import shutil

import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_objective_icing import read,write


def main():
    source=ROOT/'outputs/private/weather_history_segment_projection_20261101_v1'
    out=ROOT/'outputs/private/weather_history_projection_review_20261101_v1'
    if out.exists():raise FileExistsError('Preserve weather projection figures')
    summary=read(source/'summary.json');audit=read(source/'independent_verification.json')
    assert audit['status']=='passed' and audit['summary_sha256']==sha(source/'summary.json')
    out.mkdir(parents=True)
    layers={year:gpd.read_file(source/'weather_segments.gpkg',layer=f'winter_{year}') for year in [2024,2025]}
    boundary=gpd.read_file(ROOT/'outputs/private/segment_exposure_20261009_v1/boundary.gpkg')
    fields=[('air_temperature_mean','평균 기온 (°C)','coolwarm'),
            ('relative_humidity_mean','평균 상대습도 (%)','YlGnBu'),('wind_speed_mean','평균 1분 풍속 (m/s)','viridis')]
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':10})
    fig,axes=plt.subplots(2,3,figsize=(11.6,9.1))
    fig.subplots_adjust(left=.04,right=.99,bottom=.10,top=.87,hspace=.15,wspace=.04)
    extent=layers[2024].total_bounds;pad=4000
    for j,(field,label,cmap) in enumerate(fields):
        values=pd.concat([g[field] for g in layers.values()]).dropna()
        norm=Normalize(vmin=float(values.min()),vmax=float(values.max()))
        for i,(year,g) in enumerate(layers.items()):
            ax=axes[i,j];boundary.plot(ax=ax,color='#f0f2f3',edgecolor='#bbc7ce',linewidth=.45)
            g.plot(ax=ax,column=field,cmap=cmap,norm=norm,linewidth=2.7,missing_kwds={'color':'#acacac'})
            # 학습에 없던 ASOS 172 출처 범위는 작은 검은 점으로 함께 표시한다.
            unknown=g.loc[g.new_asos_source_domain]
            if len(unknown):
                locations=unknown.geometry.interpolate(.5,normalized=True)
                ax.scatter(locations.x,locations.y,s=2.5,c='#1d2833',alpha=.85,zorder=4)
            ax.set(xlim=(extent[0]-pad,extent[2]+pad),ylim=(extent[1]-pad,extent[3]+pad));ax.set_axis_off()
            if i==0:ax.set_title(label,fontsize=13,pad=10)
            if j==0:ax.text(-.02,.50,f'{year}.11-{year+1}.02',rotation=90,transform=ax.transAxes,va='center',ha='right',fontsize=11)
            ax.annotate('N',xy=(.93,.94),xytext=(.93,.82),xycoords='axes fraction',ha='center',
                arrowprops={'arrowstyle':'-|>','color':'#334b5a'},fontsize=8,color='#334b5a')
            x=extent[2]-17000;y=extent[1]-1800;ax.plot([x,x+10000],[y,y],color='#334b5a',lw=1.3)
            ax.text(x+5000,y+1800,'10 km',ha='center',fontsize=7,color='#334b5a')
        bar=fig.colorbar(ScalarMappable(norm=norm,cmap=cmap),ax=axes[:,j],orientation='horizontal',fraction=.025,pad=.025,shrink=.84)
        bar.ax.tick_params(labelsize=9)
    fig.suptitle('도로 기상 추정의 공간 분포 · 두 겨울',fontsize=18,y=.985)
    fig.text(.045,.935,'습도: 안정화된 과거 이력 모형 · 기온·풍속: 기존 모형 · 동일 변수는 두 겨울 같은 색 범위',fontsize=11,color='#4d6779')
    fig.text(.045,.047,'검은 점: 학습에 없던 ASOS 172 출처 구간 · 회색: 미산출 · 방향별 843개 보고 구간',fontsize=10,color='#4d6779')
    fig.text(.045,.020,'기상 추정 지도이며 결빙확률·위험등급이 아님. 세 모형의 정확도 검증은 개발 종합관측소 4곳에 한정.',fontsize=10,color='#4d6779')
    fig.savefig(out/'weather_projection_two_winters.png',dpi=190);plt.close(fig)
    figure=ROOT/'docs/images/weather_projection_20261101.png'
    if figure.exists():raise FileExistsError('Preserve existing final weather map')
    shutil.copy2(out/'weather_projection_two_winters.png',figure)
    rows=[]
    for year,g in layers.items():
        for route,q in g.groupby('route_nm'):
            record=dict(winter=year,route=route,segments=len(q),directional_length_m=float(q.len_m.sum()),
                new_asos_source_segments=int(q.new_asos_source_domain.sum()),
                input_range_outside_fraction=float(np.average(q.input_range_outside_fraction,weights=q.len_m)))
            record['humidity_history_outside_fraction']=float(np.average(q.humidity_history_outside_fraction,weights=q.len_m))
            record['humidity_history_partial_fraction']=float(np.average(q.humidity_history_partial_fraction,weights=q.len_m))
            for field,_,_ in fields:record[field]=float(np.average(q[field],weights=q.len_m))
            for t in ['air_temperature','relative_humidity','wind_speed']:
                record[t+'_coverage']=float(np.average(q[t+'_valid_slots']/q.planned_slots,weights=q.len_m))
            rows.append(record)
    pd.DataFrame(rows).to_csv(out/'route_weather_summary.csv',index=False,encoding='utf-8-sig')
    write(out/'receipt.json',dict(status='weather_projection_rendered_pending_visual_review',summary_sha256=sha(source/'summary.json'),
        audit_sha256=sha(source/'independent_verification.json'),route_rows=len(rows),
        files={p.name:sha(p) for p in out.iterdir() if p.is_file()},source_sha256=sha(Path(__file__))))
    print('WEATHER FIGURE RENDERED',len(rows),flush=True)


if __name__=='__main__':main()
