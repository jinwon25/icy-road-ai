import numpy as np
import pandas as pd
import pytest
from src.residual_icing import prior_margin,residual_prediction,select


def test_zero_residual_recovers_temperature_baseline_with_boundary_and_missingness():
    air=np.array([-1,0,.1,2,np.nan]);available=np.array([1,1,1,1,0],bool)
    b=prior_margin(air,'temperature')
    np.testing.assert_array_equal(residual_prediction(air,b,b,1,'symmetric',available),[1,1,0,0,np.nan])


def test_prior_is_subtracted_once_and_correction_is_bounded():
    air=np.array([-2,-.2,.2,2]);b=prior_margin(air,'temperature');margin=b+np.array([-20,-20,20,20])
    np.testing.assert_array_equal(residual_prediction(air,margin,b,.5,'symmetric',[1]*4),[1,0,1,0])
    np.testing.assert_array_equal(residual_prediction(air,margin,b,.5,'reject_only',[1]*4),[1,0,0,0])
    with pytest.raises(ValueError):residual_prediction(air,[np.nan]*4,b,.5,'symmetric',[1]*4)


def test_guarded_selection_refuses_recall_loss_despite_f1_gain():
    base=dict(candidate='asos_zero',f1=.1,precision=.1,recall=.9,f1_2024=.1,f1_2025=.1,site_a=.1,cap=0,rounds=0,complexity=0)
    table=pd.DataFrame([base,dict(base,candidate='candidate',f1=.2,precision=.2,recall=.89,cap=1,rounds=20,complexity=1)])
    assert select(table,True)=='asos_zero' and select(table,False)=='candidate'
    table.loc[1,'recall']=.9
    assert select(table,True)=='candidate'
