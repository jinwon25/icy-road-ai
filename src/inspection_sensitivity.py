"""계측 검토 구간의 자체 기준과 공개 목록 위치 여유에 대한 민감도 분석."""
import numpy as np
import pandas as pd

def inspection_scenario(frame,overlap,weather_quantile=.75,curve_quantile=.75,margin_m=250,minimum_availability=.95):
    required={'seg_id','winter','prediction_group','weather_index_100','condition_availability','bridge_code_fraction','curve_deg_100m','chainage_available'}
    if not required<=set(frame) or frame.duplicated(['seg_id','winter']).any():raise ValueError('Unique section/winter data required')
    if set(frame.winter)!={2024,2025}:raise ValueError('Both declared winters required')
    if not 0<weather_quantile<1 or not 0<curve_quantile<1 or not 0<minimum_availability<=1:raise ValueError('Invalid criterion')
    if margin_m not in {100,250,500}:raise ValueError('Only margins verified in the included inventory overlap data are supported')
    if not {'version','margin_m','seg_id','possible_overlap_km'}<=set(overlap):raise ValueError('Inventory overlap columns missing')
    group_column='weather_information_group' if 'weather_information_group' in frame else 'prediction_group'
    source=frame.groupby([group_column,'winter']).weather_index_100.agg(['min','max'])
    if ((source['max']-source['min']).dropna()>1e-10).any():raise ValueError('Inconsistent shared weather group')
    f=frame.copy();unique=f.drop_duplicates('seg_id')
    thresholds=f.drop_duplicates([group_column,'winter']).groupby('winter').weather_index_100.quantile(weather_quantile)
    curve=unique.curve_deg_100m.quantile(curve_quantile)
    occupied=set(overlap.loc[overlap.version.eq('2026-09-07')&overlap.margin_m.eq(margin_m)&overlap.possible_overlap_km.gt(0),'seg_id'])
    f['criterion_weather']=f.weather_index_100.ge(f.winter.map(thresholds))
    f['criterion_environment']=f.bridge_code_fraction.gt(0)|f.curve_deg_100m.gt(curve)
    f['criterion_available']=f.condition_availability.ge(minimum_availability)
    f['criterion_alignment']=f.chainage_available.eq(True)
    f['criterion_outside_inventory']=~f.seg_id.isin(occupied)
    names=['criterion_available','criterion_weather','criterion_environment','criterion_alignment','criterion_outside_inventory']
    by=f.groupby('seg_id');census=by[names].all()
    if not by.winter.nunique().eq(2).all():raise ValueError('Missing section winter')
    census['selected']=census[names].all(axis=1)
    return census,dict(weather_quantile=weather_quantile,curve_quantile=curve_quantile,margin_m=margin_m,
        minimum_availability=minimum_availability,weather_quantile_group_column=group_column,weather_threshold_by_winter={str(k):float(v) for k,v in thresholds.items()},
        curve_threshold_deg_100m=float(curve))
