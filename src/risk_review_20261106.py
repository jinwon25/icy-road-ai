"""기상 조건 노출과 도로환경을 분리한 연구용 현장 검토 행렬. 공식 A/B/C 등급 아님."""
import numpy as np
import pandas as pd

REVIEW_LABELS={0:'입력 보완',1:'해당 조건 미검출',2:'조건 관측 검토',3:'기상 노출 우선 검토',4:'기상·환경 함께 우선 검토'}

def curvature_degrees_per_100m(geometry,spacing=25.):
    """미터 좌표의 중심선을 일정 거리로 다시 표본화한 선형 변화량. 설계 곡률·회전반경 아님."""
    if geometry is None or geometry.is_empty:return np.nan
    parts=[geometry] if geometry.geom_type=='LineString' else list(geometry.geoms) if geometry.geom_type=='MultiLineString' else []
    angle=0.;length=0.
    for line in parts:
        if line.length<2*spacing:continue
        distances=np.arange(0,line.length,spacing)
        if line.length-distances[-1]>=spacing/2:distances=np.r_[distances,line.length]
        points=np.array([[line.interpolate(d).x,line.interpolate(d).y] for d in distances])
        vectors=np.diff(points,axis=0);good=np.linalg.norm(vectors,axis=1)>1e-8
        if len(vectors)<2 or not good.all():continue
        v,w=vectors[:-1],vectors[1:]
        turns=np.abs(np.arctan2(v[:,0]*w[:,1]-v[:,1]*w[:,0],np.einsum('ij,ij->i',v,w)))
        angle+=float(np.rad2deg(turns).sum());length+=float(distances[-1]-distances[0])
    return 100*angle/length if length else np.nan

def review_matrix(frame,*,minimum_availability=.95,weather_upper_quantile=.75,curve_upper_quantile=.75):
    f=frame.copy()
    needed=['seg_id','winter','prediction_group','planned_slots','ice_valid_slots','cold_wet_slots','bridge_code_fraction','tunnel_code_fraction','curve_deg_100m']
    if not set(needed)<=set(f) or f.duplicated(['seg_id','winter']).any():raise ValueError('Unique segment/winter inputs required')
    if not f.planned_slots.gt(0).all() or not (f.ice_valid_slots.between(0,f.planned_slots)&f.cold_wet_slots.between(0,f.ice_valid_slots)).all():raise ValueError('Invalid exposure denominator')
    f['weather_index_100']=100*f.cold_wet_slots.div(f.ice_valid_slots.where(f.ice_valid_slots.gt(0)))
    f['condition_availability']=f.ice_valid_slots/f.planned_slots
    f['bridge_context']=f.bridge_code_fraction.gt(0)&f.bridge_code_fraction.notna()
    f['tunnel_context']=f.tunnel_code_fraction.gt(0)&f.tunnel_code_fraction.notna()
    # 동일 원천 기상을 공유하는 다수 구간을 분위수 표본으로 중복 계산하지 않는다.
    by=f.groupby(['prediction_group','winter']).weather_index_100.agg(['min','max'])
    if ((by['max']-by['min']).dropna()>1e-10).any():raise ValueError('Prediction group has inconsistent exposure')
    thresholds={int(y):float(q.weather_index_100.dropna().quantile(weather_upper_quantile)) for y,q in f.drop_duplicates(['prediction_group','winter']).groupby('winter')}
    curves=f.drop_duplicates('seg_id').curve_deg_100m.dropna()
    curve_threshold=float(curves.quantile(curve_upper_quantile)) if len(curves) else np.nan
    f['curve_context']=f.curve_deg_100m.gt(curve_threshold)
    f['environment_context']=f.bridge_context|f.curve_context
    f['weather_upper_threshold']=f.winter.map(thresholds)
    f['weather_level']=np.where(f.weather_index_100.le(0),0,np.where(f.weather_index_100.ge(f.weather_upper_threshold),2,1))
    f.loc[f.weather_index_100.isna(),'weather_level']=-1
    f['review_code']=np.select([f.condition_availability.lt(minimum_availability)|f.weather_index_100.isna(),
        f.weather_level.eq(0),f.weather_level.eq(2)&f.environment_context,f.weather_level.eq(2)],[0,1,4,3],default=2)
    f['review_label']=f.review_code.map(REVIEW_LABELS)
    return f,dict(minimum_availability=minimum_availability,weather_upper_quantile=weather_upper_quantile,
        weather_threshold_by_winter=thresholds,weather_quantile_population='unique prediction_group within winter',
        curve_upper_quantile=curve_upper_quantile,curve_threshold_deg_100m=curve_threshold,
        curve_quantile_population='unique 500m reporting segments; descriptive geometric proxy',
        use_normalized_dem_as_meters=False,official_risk_grade=False,measured_ice_probability=False)