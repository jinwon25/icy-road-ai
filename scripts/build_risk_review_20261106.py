"""Q&A716이 허용한 근거 명시형 기상 노출 지수·도로환경 검토 행렬과 CSV/GIS/JPG를 만든다."""
from pathlib import Path
import json,sys
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
from matplotlib.lines import Line2D
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.risk_review_20261106 import review_matrix,curvature_degrees_per_100m,REVIEW_LABELS
from scripts.package_submission_channels import read,write,sha

OUT=ROOT/'outputs/private/risk_review_20261106_v14'
SOURCE=ROOT/'outputs/private/wind_network_segment_projection_20261102_v1'
OLD=ROOT/'outputs/private/submission_candidate_20261101_v12/exports/segment_estimates.csv'

def main():
    if OUT.exists():raise FileExistsError('Preserve existing risk review')
    summary=read(SOURCE/'summary.json');audit=read(SOURCE/'independent_verification.json')
    assert audit['status']=='passed' and audit['summary_sha256']==sha(SOURCE/'summary.json')
    f=pd.read_csv(OLD,dtype={'seg_id':str,'prediction_group':str},float_precision='round_trip')
    f=f.loc[f.scale_m.eq(500)].copy();assert len(f)==1686
    weather=pd.read_csv(SOURCE/'weather_segments_500m.csv',dtype={'seg_id':str},float_precision='round_trip')
    cols=['seg_id','winter','air_temperature_mean','relative_humidity_mean','wind_speed_mean','wind_network_outside_fraction','new_asos_source_domain']
    f=f.merge(weather[cols],on=['seg_id','winter'],validate='one_to_one')
    geometry=gpd.read_file(SOURCE/'weather_segments.gpkg',layer='winter_2024')[['seg_id','geometry']].to_crs(5179)
    assert len(geometry)==843 and geometry.seg_id.is_unique
    curve=geometry[['seg_id']].copy();curve['curve_deg_100m']=geometry.geometry.map(curvature_degrees_per_100m)
    f=f.merge(curve,on='seg_id',validate='many_to_one')
    result,settings=review_matrix(f)
    # 서로 다른 집계 표현을 통해 전체 1,686행의 비율·시간·분모를 검산한다.
    np.testing.assert_allclose(result.weather_index_100,100*result.cold_wet_fraction,atol=1e-12,rtol=0,equal_nan=True)
    np.testing.assert_allclose(result.cold_wet_hours,result.cold_wet_slots/6,atol=1e-12,rtol=0)
    assert result.review_code.between(0,4).all() and result.weather_index_100.dropna().between(0,100).all()
    OUT.mkdir();result.to_csv(OUT/'risk_review_500m.csv',index=False,encoding='utf-8-sig')
    curve.to_csv(OUT/'centerline_curve_context.csv',index=False,encoding='utf-8-sig')
    with pd.option_context('mode.use_inf_as_na',True):
        counts=result.groupby(['winter','review_code','review_label'],observed=True).agg(segments=('seg_id','size'),length_m=('len_m','sum'),weather_groups=('prediction_group','nunique')).reset_index()
    counts.to_csv(OUT/'review_category_summary.csv',index=False,encoding='utf-8-sig')
    spatial=gpd.GeoDataFrame(result.merge(geometry,on='seg_id',validate='many_to_one'),geometry='geometry',crs=geometry.crs)
    shape_columns={'seg_id':'seg_id','winter':'winter','weather_index_100':'wx_index','condition_availability':'wx_avail',
        'curve_deg_100m':'curve100','bridge_code_fraction':'bridge_fr','tunnel_code_fraction':'tunnel_fr',
        'review_code':'review_cd','review_label':'review_nm','wind_network_outside_fraction':'wind_out'}
    for year,q in spatial.groupby('winter'):
        q.to_file(OUT/'risk_review.gpkg',layer=f'winter_{year}',driver='GPKG')
        target=OUT/f'shapefile_{year}';target.mkdir()
        q[[*shape_columns,'geometry']].rename(columns=shape_columns).to_file(target/f'risk_{year}_500m.shp',encoding='UTF-8')
        replay=gpd.read_file(target/f'risk_{year}_500m.shp')
        assert len(replay)==843 and set(replay.seg_id)==set(q.seg_id)
        np.testing.assert_allclose(replay.set_index('seg_id').loc[q.seg_id,'wx_index'],q.weather_index_100,atol=1e-10,rtol=0)
    criteria=[
        dict(item='기상조건 노출지수',formula='100 * cold_wet_slots / ice_valid_slots',threshold='0–100; 미산출은 NA',basis='0°C와 수분 대용조건의 빈도; 기존 보존 v2 조건',meaning='추정 저온·수분 조건 비율; 실제 Ice 발생률·확률 아님'),
        dict(item='겨울 내 상대 노출',formula='고유 prediction_group별 노출지수의 75백분위 이상',threshold=json.dumps(settings['weather_threshold_by_winter'],ensure_ascii=False),basis='자료 내부의 비교 기준; 공식·물리 위험 경계 아님',meaning='같은 기상을 공유하는 500m 구간의 중복 가중 방지'),
        dict(item='교량 맥락',formula='bridge_code_fraction > 0',threshold='제공 중심선 교량 코드가 일부라도 존재',basis='NWS·ODOT의 교량 냉각 특성 안내',meaning='추가 현장 검토 근거; 실제 시설 범위·재질·사고위험 효과 미검증'),
        dict(item='선형 변화 맥락',formula='25m 재표본화 중심선의 방향 변화 합 / 길이 * 100',threshold='전체 고유 500m 구간의 75백분위 초과',basis='중심선으로 파생한 기술통계; 설계 곡률·회전반경·물리 경사도 아님',meaning='결빙 시 조향·노면 마찰 검토 대상; 상대 기준의 현장 검증 필요'),
        dict(item='입력 충분성',formula='ice_valid_slots / planned_slots',threshold='0.95 미만은 입력 보완',basis='연구자가 사전 정한 가용성 점검 기준',meaning='안전·낮은 위험의 판정으로 대체하지 않음'),
        dict(item='터널 맥락',formula='tunnel_code_fraction > 0',threshold='제공 중심선 터널 코드 존재 여부',basis='입·출구와 내부를 동일한 위험으로 해석할 수 없음',meaning='맥락만 표시; 위험 가중치 부여하지 않음'),
        dict(item='기후·고도 제외',formula='10년 기후값과 미터 고도 자료를 갖추지 않은 항목은 별도 미산정',threshold='두 겨울을 10년값으로 환산하지 않음',basis='Q&A716·693',meaning='정규화 DEM을 미터·물리 경사도로 사용하지 않음')]
    pd.DataFrame(criteria).to_csv(OUT/'risk_criteria_catalog.csv',index=False,encoding='utf-8-sig')
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':10})
    fig,axes=plt.subplots(2,2,figsize=(11.5,11.5));vmax=max(1e-8,float(result.weather_index_100.max()))
    palette=['#9ba7ad','#dcebed','#e7c87c','#dd8d48','#ae4b3f'];cmap=ListedColormap(palette)
    for i,year in enumerate([2024,2025]):
        q=spatial.loc[spatial.winter.eq(year)]
        q.plot(column='weather_index_100',ax=axes[i,0],cmap='YlOrRd',vmin=0,vmax=vmax,linewidth=1.8,legend=False)
        q.plot(column='review_code',ax=axes[i,1],cmap=cmap,norm=BoundaryNorm(np.arange(-.5,5.5,1),cmap.N),linewidth=1.8,legend=False)
        for j in [0,1]:
            axes[i,j].set_aspect('equal');axes[i,j].set_axis_off()
            axes[i,j].set_title(f'{year}/{str(year+1)[2:]} 겨울 · '+('저온·수분 조건 노출지수' if j==0 else '기상·도로환경 검토 행렬'),pad=12)
    fig.suptitle('새 Q&A 반영: 기상 노출지수와 현장 검토 근거\n연구용 비교이며 실제 결빙확률·공식 A/B/C 등급·자동 제설 지시가 아닙니다',fontsize=15,y=.98)
    bar=fig.colorbar(plt.cm.ScalarMappable(norm=plt.Normalize(0,vmax),cmap='YlOrRd'),ax=axes[:,0].tolist(),orientation='horizontal',fraction=.025,pad=.02)
    bar.set_label('노출지수 = 100 × 추정 조건 충족 시점 / 판정 가능 시점')
    handles=[Line2D([0],[0],color=palette[i],lw=4,label=REVIEW_LABELS[i]) for i in range(5)]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.72,.035),ncol=1,frameon=False,fontsize=9)
    fig.subplots_adjust(top=.9,bottom=.19,wspace=.05,hspace=.1)
    fig.text(.05,.02,'기존 v2 조건·도로 선형 보존 | 풍속은 채택 69특성 결과 | 같은 원천 기상 구간은 독립 실측 표본이 아닙니다.',fontsize=9,color='#526b75')
    fig.savefig(OUT/'risk_review_maps.jpg',dpi=180,bbox_inches='tight',facecolor='white');plt.close(fig)
    (OUT/'README.md').write_text('''# 새 기준의 기상 노출·도로환경 검토

`risk_review_500m.csv`는 500m 843구간·두 겨울 1,686행입니다. `risk_criteria_catalog.csv`는 공식 Q&A716이 허용한 근거 명시형 새 기준과 산식을 설명합니다. `risk_review.gpkg`, 겨울별 Shapefile, JPG 지도를 함께 제공합니다.

노출지수는 기존 v2 저온·수분 조건의 비율을 0–100으로 표현한 값이며 실제 Ice 발생확률·사고확률이 아닙니다. 현재 제출용 F1 우선 분류 프로필과 조건 노출 지수의 목적은 다릅니다. 교량 코드와 중심선 파생 선형 변화는 함께 검토할 맥락이며 인과효과·공식 위험 배점으로 해석하지 않습니다.

상위 노출은 겨울별 고유 기상 그룹의 75백분위, 선형 변화는 고유 구간의 75백분위를 사용하는 자체 비교 기준입니다. 0.95 가용성 기준도 연구자 점검 조건입니다. 실제 시설 범위·교통량·사고·제설·노면 마찰을 확인해 현장 기준을 보정해야 합니다. 터널 내부·입출구의 차이를 입증하지 못했으므로 터널 코드는 위험 가중치로 사용하지 않습니다.

제공 DEM은 미터가 아니므로 이 기준의 물리 고도·경사도에 사용하지 않습니다. 최근 10년 기후값을 갖추지 못했으므로 두 겨울을 공식 기후 평년처럼 적용하지 않습니다. 미확보 환경 항목에 임의 상수나 A/B/C 등급을 넣지 않았습니다.

근거: [공식 Q&A716](https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=716), [공식 Q&A693](https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=693), [NWS 결빙 안내](https://www.weather.gov/safety/winter-ice-frost), [Oregon DOT 교량·그늘 설명](https://www.oregon.gov/odot/Pages/Winter-Be-Ready-Ice.aspx), [FHWA 도로기상](https://ops.fhwa.dot.gov/weather/weather_events/snow_ice.htm). 참고 원리를 국내 구간의 검증된 효과 크기로 전용하지 않았습니다.
''',encoding='utf8')
    paths=[p for p in OUT.rglob('*') if p.is_file()]
    write(OUT/'receipt.json',dict(status='risk_review_built_pending_visual_review',rows=len(result),segments=843,settings=settings,
        vectorized_exposure_checks=len(result)*3,shapefile_rows_reloaded=1686,protected_outcomes_read=False,
        input_signatures={p.relative_to(ROOT).as_posix():sha(p) for p in [OLD,SOURCE/'summary.json',SOURCE/'weather_segments_500m.csv',SOURCE/'weather_segments.gpkg',
            ROOT/'src/risk_review_20261106.py',Path(__file__)]},files={p.relative_to(OUT).as_posix():sha(p) for p in paths}))
    print('RISK REVIEW BUILT',len(result),'rows;',result.groupby(['winter','review_code']).size().to_dict(),flush=True)

if __name__=='__main__':main()