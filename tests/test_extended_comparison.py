import numpy as np
import pandas as pd
from src.extended_comparison import physical_ice,event_retention,block_sensitivity


def test_unknown_input_is_not_negative():
    f=pd.DataFrame({'aws_dewpoint':[np.nan,np.nan,-2.], 'rain15_max_3h':[np.nan,1.,0.], 'asos_snow_cm':[np.nan,0.,0.]})
    np.testing.assert_allclose(physical_ice(f,[-1.,np.nan,-1.]),[np.nan,np.nan,0.],equal_nan=True)


def test_event_loss_is_not_hidden_by_gain_or_other_winter():
    f=pd.DataFrame({'station':['12207']*4,'time':pd.to_datetime(['2024-11-01','2024-11-01 00:10','2025-11-01','2025-11-01 00:10'],format='mixed'),'ice':[1,1,1,1]})
    result,events=event_retention(f,[0,0,1,0],[1,0,0,0])
    assert result['observed_events']==2 and result['lost_events']==1 and result['gained_events']==1
    assert len(events)==2


def test_paired_identical_predictions_have_zero_difference():
    n=240;f=pd.DataFrame({'time':pd.date_range('2024-11-01',periods=n,freq='10min'), 'winter':2024,'road_temp':np.arange(n,dtype=float)})
    result=block_sensitivity(f,np.zeros(n),np.zeros(n),draws=30)
    assert result['mae_difference_quantiles']==[0.,0.,0.]
    assert result['relative_improvement_quantiles']==[0.,0.,0.]
