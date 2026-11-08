"""기상·도로환경·공개 목록의 공통 조건으로 계측 검토 구간을 고른다."""
import numpy as np
import pandas as pd
def select_inspection_segments(frame):
 required={'seg_id','winter','prediction_group','weather_index_100','condition_availability','bridge_code_fraction','curve_deg_100m','current_relation','chainage_available'}
 if not required<=set(frame):raise ValueError('Required section columns missing')
 f=frame.copy()
 if f.duplicated(['seg_id','winter']).any():raise ValueError('Duplicate segment/winter')
 if not set(f.winter)=={2024,2025}:raise ValueError('Both declared winters required')
 curve=f.drop_duplicates('seg_id').curve_deg_100m.quantile(.75)
 group_column='weather_information_group' if 'weather_information_group' in f else 'prediction_group'
 unique=f.drop_duplicates([group_column,'winter'])
 thresholds=unique.groupby('winter').weather_index_100.quantile(.75).to_dict()
 row=(f.weather_index_100.ge(f.winter.map(thresholds))&
      (f.bridge_code_fraction.gt(0)|f.curve_deg_100m.gt(curve))&
      f.condition_availability.ge(.95)&
      f.current_relation.eq('outside_inventory_for_margin')&
      f.chainage_available.eq(True))
 census=pd.DataFrame({'seg_id':f.seg_id,'eligible':row,'winter':f.winter}).groupby('seg_id').agg(eligible=('eligible','all'),winters=('winter','nunique'))
 selected=set(census.index[census.eligible&census.winters.eq(2)])
 return f.loc[f.seg_id.isin(selected)].copy(),dict(weather_threshold_pct=thresholds,curve_threshold_deg_per_100m=float(curve))
