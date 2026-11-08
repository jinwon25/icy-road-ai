import numpy as np
import pandas as pd
import pytest
from src.official_metrics_20261106 import evaluate

W=[('2024-11-01','2024-11-03')]
def frame(rows):return pd.DataFrame(rows,columns=['station','time','ice'])
def score(f,p,minimum=1):return evaluate(f,p,minimum_valid_slots=minimum,winters=W)

def test_false_alarms_at_station_without_ice_do_not_enter_macro():
    f=frame([('1','2024-11-01 00:00',1),('2','2024-11-01 00:00',0)])
    s,t,d=score(f,[1,1])
    assert s['f1']==1 and s['f1_stations']==1 and s['excluded_no_ice_stations']==['2']
    assert d.loc[d.station.eq('2')&d.valid_slots.gt(0),'f1'].iloc[0]==0
    assert t.loc[t.station.eq('2'),'f1_days'].iloc[0]==0

def test_metric_specific_denominators_and_missed_day():
    f=frame([('1','2024-11-01 00:00',1),('1','2024-11-02 00:00',0)])
    s,t,d=score(f,[0,1])
    assert s['precision']==0 and s['recall']==0 and s['f1']==0
    assert s['precision_days']==1 and s['recall_days']==1 and s['f1_days']==2

def test_daily_then_station_mean_is_not_pooled_or_daily_global_mean():
    f=frame([('1','2024-11-01 00:00',1),('1','2024-11-02 00:00',1),('2','2024-11-01 00:00',1)])
    s,_,_=score(f,[1,0,1])
    assert s['f1']==.75 and s['f1_days']==3 and s['f1_stations']==2

def test_missing_prediction_does_not_hide_station_with_actual_ice():
    f=frame([('1','2024-11-01 00:00',1),('1','2024-11-02 00:00',0)])
    s,t,_=score(f,[np.nan,1])
    assert s['actual_ice_stations']==1 and s['excluded_no_ice_stations']==[] and s['f1']==0
    assert t.observed_ice_slots.iloc[0]==1

def test_both_zero_days_and_no_events_all_stations_are_undefined():
    s,t,d=score(frame([('1','2024-11-01 00:00',0)]),[0])
    assert s['f1'] is None and s['f1_stations']==0 and s['f1_days']==0
    assert d.f1.isna().all()

def test_explicit_partial_day_sensitivity():
    f=frame([('1','2024-11-01 00:00',1)])
    assert score(f,[1],minimum=1)[0]['f1']==1
    assert score(f,[1],minimum=144)[0]['f1'] is None

def test_duplicate_and_shifted_timestamp_are_rejected():
    with pytest.raises(ValueError,match='Duplicate'):score(frame([('1','2024-11-01 00:00',1)]*2),[1,1])
    with pytest.raises(ValueError,match='ten-minute'):score(frame([('1','2024-11-01 00:01',1)]),[1])

def test_utc_is_aligned_to_kst_date():
    f=frame([('1',pd.Timestamp('2024-10-31 15:00:00Z'),1)])
    s,_,d=score(f,[1]);assert s['f1']==1
    assert d.loc[d.valid_slots.gt(0),'date_kst'].iloc[0]==pd.Timestamp('2024-11-01')