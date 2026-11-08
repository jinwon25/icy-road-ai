import numpy as np
import pandas as pd
from shapely.geometry import LineString
from src.risk_review_20261106 import curvature_degrees_per_100m,review_matrix

def test_curvature_resampling_does_not_treat_extra_straight_vertices_as_curve():
    a=LineString([(0,0),(100,0)])
    b=LineString([(i,0) for i in range(101)])
    assert curvature_degrees_per_100m(a)==curvature_degrees_per_100m(b)==0
    assert np.isnan(curvature_degrees_per_100m(LineString([(0,0),(10,0)])))

def test_circle_and_line_have_different_geometric_context():
    theta=np.linspace(0,np.pi/2,1000)
    arc=LineString(np.column_stack([100*np.cos(theta),100*np.sin(theta)]))
    value=curvature_degrees_per_100m(arc)
    assert 40<value<60

def test_quantile_is_not_changed_by_repeated_weather_group_segments():
    f=pd.DataFrame(dict(seg_id=['a','b','c'],winter=[2024]*3,prediction_group=['x','y','z'],
        planned_slots=[100]*3,ice_valid_slots=[100]*3,cold_wet_slots=[0,10,20],bridge_code_fraction=[0,0,1],tunnel_code_fraction=[0]*3,curve_deg_100m=[0]*3))
    _,p=review_matrix(f)
    duplicates=pd.concat([f]+[f.iloc[[1]].assign(seg_id='copy'+str(i)) for i in range(30)],ignore_index=True)
    q,t=review_matrix(duplicates)
    assert p['weather_threshold_by_winter']==t['weather_threshold_by_winter']=={2024:15.}
    assert q.loc[q.seg_id.eq('c'),'review_code'].iloc[0]==4

def test_incomplete_inputs_are_not_labeled_low_risk():
    f=pd.DataFrame(dict(seg_id=['a'],winter=[2024],prediction_group=['x'],planned_slots=[100],ice_valid_slots=[0],
        cold_wet_slots=[0],bridge_code_fraction=[0],tunnel_code_fraction=[0],curve_deg_100m=[np.nan]))
    q,_=review_matrix(f);assert q.review_code.iloc[0]==0 and np.isnan(q.weather_index_100.iloc[0])