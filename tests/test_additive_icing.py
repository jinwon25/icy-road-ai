import numpy as np
import pandas as pd
import pytest
from src.additive_icing import additive_prediction,metric_table,select_policy
from src.blind_icing import daily_metrics,summarize_days


def test_additions_never_remove_baseline_and_preserve_availability():
    a=np.array([-2,0,.5,1,4,5,np.nan]);s=np.array([0,0,.8,.7,.9,1,.9]);valid=np.array([1,1,1,1,1,1,0],bool)
    result=additive_prediction(a,s,.8,4,valid)
    np.testing.assert_array_equal(result,[1,1,1,0,1,0,np.nan])
    with pytest.raises(ValueError):additive_prediction(a,s,1.1,4,valid)


def test_daily_metric_matrix_agrees_with_missing_days_and_zero_positive_sites():
    rows=[]
    for station in ['a','b']:
        for i,t in enumerate(pd.date_range('2024-11-01',periods=288,freq='10min')):
            rows.append(dict(station=station,time=t,available=not(station=='b' and i==200),ice=int(station=='a' and i==0)))
    f=pd.DataFrame(rows);pred=np.where(f.available,np.arange(len(f))%50==0,np.nan)
    policy=dict(candidate='asos_zero',model=None,cap=0,threshold=1,complexity=0)
    r=metric_table(f,pred[:,None],[policy]).iloc[0]
    check=summarize_days(daily_metrics(f,pred,['a','b'],[['2024-11-01','2024-11-03']]),['a','b'])
    assert r.f1==check['f1_fixed_population'] and r.fp==check['fp']


def test_selection_falls_back_when_precision_or_site_harms_and_ties_prefer_baseline():
    base=dict(candidate='asos_zero',f1=.1,precision=.1,f1_2024=.1,f1_2025=.1,site_a=.1,cap=0,threshold=1,complexity=0)
    t=pd.DataFrame([base,dict(base,candidate='bad',f1=.2,precision=.09,cap=2,complexity=1)])
    assert select_policy(t,True)=='asos_zero' and select_policy(t,False)=='bad'
    t.loc[1,'precision']=.2;t.loc[1,'site_a']=.09
    assert select_policy(t,True)=='asos_zero'
    t.loc[1,'site_a']=.2
    assert select_policy(t,True)=='bad'
    t.loc[1,'f1']=.1
    assert select_policy(t,False)=='asos_zero'
