from itertools import product
import numpy as np
import pandas as pd
import pytest
from src.weather_information import collision_summary,past_hour_trend,extrapolated_temperature


def test_collision_oracle_agrees_with_exhaustive_binary_assignments():
    x=pd.DataFrame({'x':[0,0,0,1,1,np.nan,np.nan]});y=np.array([1,1,0,0,0,1,0]);r=collision_summary(x,y)
    possibilities=[]
    for bits in product([0,1],repeat=3):
        pred=np.array([bits[0]]*3+[bits[1]]*2+[bits[2]]*2);tp=(pred*y).sum();fp=(pred*(1-y)).sum();fn=((1-pred)*y).sum()
        possibilities.append(2*tp/(2*tp+fp+fn))
    assert r['label_aware_pooled_f1_upper_bound']==max(possibilities)
    assert r['minimum_observed_errors']==2 and r['minimum_fp_if_all_observed_positives_retained']==2


def sample():
    q=pd.date_range('2024-11-01 01:10',periods=18,freq='10min');s=(q-pd.Timedelta(nanoseconds=1)).floor('h')
    return pd.DataFrame(dict(station='a',time=q,asos_source_time=s,asos_air_temp=np.repeat([1.,0.,-2.],6),asos_age_minutes=(q-s).total_seconds()/60))


def test_trend_uses_previous_hour_and_future_mutation_cannot_change_past():
    f=sample();before=past_hour_trend(f);g=f.copy();g.loc[g.time.gt('2024-11-01 03:00'),'asos_air_temp']=5
    after=past_hour_trend(g);pd.testing.assert_frame_equal(before.iloc[:12],after.iloc[:12])
    assert before.trend_c_per_hour.iloc[:6].isna().all() and (before.trend_c_per_hour.iloc[6:12]==-1).all()
    np.testing.assert_allclose(extrapolated_temperature([0,0],[10,60],[-1,-1],1,.5),[-1/6,-.5])


def test_gap_and_station_boundary_fall_back_and_future_source_is_rejected():
    f=sample().iloc[[0,12]].copy();r=past_hour_trend(f);assert not r.trend_available.any()
    f=sample();f.loc[f.index>=6,'station']='b';assert not past_hour_trend(f).trend_available.iloc[6:12].any()
    f.loc[0,'asos_source_time']=f.loc[0,'time']
    with pytest.raises(ValueError):past_hour_trend(f)
