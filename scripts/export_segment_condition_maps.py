"""구간 추정·환경 CSV와 조건 노출 시나리오 지도를 내보낸다."""
import json
from pathlib import Path
import geopandas as gpd
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT=Path(__file__).resolve().parents[1]


def main():
    private=ROOT/'outputs/private';source=private/'segment_inference_v1'
    summary=json.loads((source/'summary.json').read_text(encoding='utf-8'))
    temperature=pd.read_csv(source/'segment_temperature_summary.csv',dtype={'segment_id':str})
    if temperature.near_source.isna().any():raise ValueError('Missing expected RWIS route reference: proposal export blocked')
    environment=pd.read_csv(private/'spatial/environment_features/segment_environment_inventory.csv',dtype={'segment_id':str})
    # 동일 메타데이터 열은 온도 추론 표의 것을 유지한다.
    common=(set(temperature)&set(environment))-{'segment_id'}
    combined=temperature.merge(environment.drop(columns=list(common)),on='segment_id',validate='one_to_one')
    combined['temperature_cutoff_c']=0.;combined['rain_history_hours']=24
    combined['temperature_error_sensitivity_radius_c']=summary['absolute_error_sensitivity_radius_c']
    combined['risk_grade']='not_assigned';combined['interpretation']='estimated_cold_moisture_condition_not_Ice_probability'
    geometry=gpd.read_file(private/'spatial/segment_scaffold/segments.gpkg')[['seg_id','geometry']].rename(columns={'seg_id':'segment_id'})
    joined=geometry.merge(combined,on='segment_id',validate='one_to_one')
    if len(joined)!=467 or len(combined)!=summary['segments']:raise AssertionError('Incomplete segment deliverable')
    out=private/'segment_condition_proposal';out.mkdir(exist_ok=True)
    combined.to_csv(out/'segment_estimates_and_environment.csv',index=False,encoding='utf-8-sig')
    joined.to_file(out/'segment_conditions.gpkg',layer='condition_exposure',driver='GPKG')
    rename={'segment_id':'seg_id','length_m':'len_m','estimated_temperature_mean_c':'tmp_mean',
            'condition_exposure_sample_equivalent_hours':'cond_h','condition_exposure_low_sample_equivalent_hours':'cond_lo_h',
            'condition_exposure_high_sample_equivalent_hours':'cond_hi_h','bridge_overlap_2d_m':'br_ov_m','tunnel_overlap_2d_m':'tu_ov_m',
            'curvature_p90_inv_m':'curv_50','dsm_elevation_m':'dsm_m','sky_view_proxy':'sky_view','near_rwis_distance_km':'ref_km'}
    shape=joined[[*rename,'geometry']].rename(columns=rename);shape['risk_stat']='condition_only'
    shape.to_file(out/'segment_conditions.shp',driver='ESRI Shapefile',encoding='UTF-8')
    for path,key in [(out/'segment_conditions.gpkg','segment_id'),(out/'segment_conditions.shp','seg_id')]:
        reread=gpd.read_file(path)
        if len(reread)!=467 or reread.crs!=joined.crs or set(reread[key])!=set(joined.segment_id):raise AssertionError('Export roundtrip failed')
        if abs(reread.length.sum()-joined.length.sum())>.001:raise AssertionError('Geometry changed on export')
    available={f.name for f in font_manager.fontManager.ttflist}
    for name in ['Malgun Gothic','Noto Sans CJK KR','NanumGothic']:
        if name in available:plt.rcParams['font.family']=name;break
    plt.rcParams['axes.unicode_minus']=False
    radius=summary['absolute_error_sensitivity_radius_c'];fig,axes=plt.subplots(1,3,figsize=(13,7))
    cols=['condition_exposure_low_sample_equivalent_hours','condition_exposure_sample_equivalent_hours','condition_exposure_high_sample_equivalent_hours']
    titles=[f'추정온도 +{radius:.2f}°C 시나리오','기본 온도 추정',f'추정온도 -{radius:.2f}°C 시나리오']
    maximum=float(joined[cols].max().max())
    for ax,col,title in zip(axes,cols,titles):
        joined.plot(ax=ax,column=col,cmap='viridis',vmin=0,vmax=maximum,linewidth=2.8,legend=True,legend_kwds={'shrink':.55,'pad':.02})
        ax.set_title(title,fontsize=11);ax.set_axis_off()
    fig.suptitle('추정 노면온도와 수분 대용조건의 동시 노출 · 두 겨울 시간 표본 합계',fontsize=14,y=.96)
    fig.text(.04,.055,'단위: 10분 표본 수 / 6 (시간). 실제 결빙 지속시간·발생확률·사고 위험 등급이 아님.\n조건: 추정 노면온도 ≤0°C, 그리고 과거 24시간 강수 관측 또는 주변 AWS 이슬점 ≥추정 노면온도.\n양쪽 지도는 개발 오차에 따른 민감도 시나리오이며 신뢰구간이 아님. 도형 중점 추정·공식 이정 및 방향 미확인.',fontsize=10,color='#475569')
    fig.subplots_adjust(left=.03,right=.97,top=.84,bottom=.20,wspace=.25)
    fig.savefig(out/'condition_exposure_sensitivity.jpg',dpi=190);fig.savefig(out/'condition_exposure_sensitivity.png',dpi=190);plt.close(fig)
    manifest={'status':'draft_condition_exposure_and_environment_proposal','segments':len(joined),'crs':str(joined.crs),
              'shapefile_field_map':rename,'risk_grade_assigned':False,'roundtrip_verified':True,
              'source_inference_summary':summary,'copernicus_notices':json.loads((private/'external/copernicus_dem/manifest.json').read_text(encoding='utf-8')),
              'next_required':['Validated Ice classifier output','Final model/evaluation freeze','Official heldout assessment','Chainage linkage when authoritative anchors become available','Demonstration and participant contribution review']}
    final_path=private/'frozen_assessment_v1/summary.json'
    if final_path.exists():
        final=json.loads(final_path.read_text(encoding='utf-8'))
        manifest['frozen_assessment']={'temperature_station_macro':final['temperature_station_macro'],'ice_slot_micro':final['ice_slot_micro']}
        manifest['next_required']=['Reliable Ice detection remains unachieved','Official chainage and direction linkage','Participant contribution confirmation','Unspecified submission-schema and daily-metric edge cases']
        manifest['classification_limitation']='Frozen protected-station Ice detection failed; the condition map is not a validated Ice risk grade.'
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'segments':len(joined),'csv_columns':len(combined.columns),'roundtrip_verified':True}),flush=True)


if __name__=='__main__':main()
