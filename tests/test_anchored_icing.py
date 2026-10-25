import numpy as np
import pandas as pd
import pytest
from src.anchored_icing import anchored_prediction,linear_features,ASOS_FEATURES,binary_matrix_metrics,choose_policy


def test_anchor_limits_and_na():
    air=np.array([-3,-2.1,-.1,0,.1,2.1,3,np.nan]);score=np.linspace(0,1,len(air))
    for bound in [.25,.5,1,2]:
        p=anchored_prediction(air,score,bound,'symmetric')
        assert (p[air < -bound]==1).all() and (p[air>bound]==0).all() and np.isnan(p[-1])
        q=anchored_prediction(air,score,bound,'reject_only');assert (q[air>0]==0).all()
    np.testing.assert_array_equal(anchored_prediction(air,score,0,'symmetric'),np.where(np.isfinite(air),air<=0,np.nan))


def test_anchor_invalid_values():
    for score in [[np.nan],[1.1],[-.1]]:
        with pytest.raises(ValueError):anchored_prediction([0],score,1,'symmetric')
    with pytest.raises(ValueError):anchored_prediction([0],[.5],3,'symmetric')


def test_features_never_take_outcomes():
    f=pd.DataFrame({c:[1.,np.nan] for c in ASOS_FEATURES});x=linear_features(f)
    f['ice']=1;f['road_temp']=99;f['station']='protected'
    pd.testing.assert_frame_equal(x,linear_features(f))


def test_matrix_complete_days_and_retention():
    f=pd.DataFrame(dict(station=['a']*288,group=['g']*288,winter=[2024]*288,time=pd.date_range('2024-11-01',periods=288,freq='10min'),available=True,ice=0,asos_air_temp=-1.))
    f.loc[0,'ice']=1
    p=np.zeros((288,3));p[0,:2]=1;p[144:,1]=1;p[:,2]=1
    r=binary_matrix_metrics(f,p)
    assert r.mean_f1.tolist()==[1.,.5,1/145]
    assert r.minimum_group_winter_retention.tolist()==[1.,1.,1.]
    p[0,0]=0;assert binary_matrix_metrics(f,p).minimum_group_winter_retention.iloc[0]==0
    p[4,0]=np.nan
    with pytest.raises(ValueError):binary_matrix_metrics(f,p)


def test_guard_rejects_transfer_risk():
    t=pd.DataFrame([dict(candidate='asos_zero',mean_f1=.03,worst_winter_f1=.01,f1_2024=.04,f1_2025=.01,fp=100,complexity=0,minimum_group_winter_retention=1.),
        dict(candidate='fragile',mean_f1=.04,worst_winter_f1=.02,f1_2024=.06,f1_2025=.02,fp=50,complexity=1,minimum_group_winter_retention=.97)])
    assert choose_policy(t,'mean_f1')['candidate']=='fragile'
    assert choose_policy(t,'retention_guard')['candidate']=='asos_zero'
