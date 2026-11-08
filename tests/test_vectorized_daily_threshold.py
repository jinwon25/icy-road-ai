import numpy as np
import pandas as pd
from src.vectorized_daily_threshold import threshold_curve,select_threshold
from src.exact_daily_threshold import select_exact_thresholds
from scripts.audit_icing_transition import independent_metrics


def test_vectorized_curve_matches_every_brute_force_threshold_and_old_selector():
    rng=np.random.default_rng(481)
    f=pd.concat([pd.DataFrame({'station':s,'winter':year,'time':pd.date_range(f'{year}-11-01',periods=288,freq='10min'),
                              'ice':rng.choice([0.,1.,np.nan],288,p=[.96,.03,.01])})
                 for s in ['a','b'] for year in [2024,2025]],ignore_index=True)
    # 완전 날짜·무양성 날짜·일부 관측 날짜가 함께 존재한다.
    f.loc[:287,'ice']=0.;f.loc[300:310,'ice']=1.
    f.loc[288:575,'ice']=f.loc[288:575,'ice'].fillna(0)
    p=rng.choice([.1,.3,.5,.7,.9],len(f));p[1000]=np.nan
    table=threshold_curve(f,p)
    for row in table.itertuples():
        pred=np.where(np.isfinite(p),p>=row.threshold,np.nan)
        expected=independent_metrics(f,pred)
        np.testing.assert_allclose(row.mean_f1,expected['f1_fixed_population'],atol=1e-12,rtol=0)
        assert (row.tp,row.fp,row.fn)==(expected['tp'],expected['fp'],expected['fn'])
    old=select_exact_thresholds(f,p)
    for track in old:
        chosen=select_threshold(table,track)
        assert chosen['threshold']==old[track]['threshold']
        np.testing.assert_allclose(chosen[track],old[track][track],atol=1e-12,rtol=0)
