import unittest
import numpy as np
import pandas as pd
from src.extended_ice_rules import consecutive,DailyAccumulator
from src.runtime_metrics import runtime_daily

class ExtendedIceRuleTests(unittest.TestCase):
    def test_fast_metric_matches_daily_and_keeps_missing_station(self):
        parts=[]
        for year in [2024,2025]:
            for station in ['12207','12408']:
                parts.append(pd.DataFrame({'station':station,'winter':year,'time':pd.date_range(f'{year}-11-01',periods=288,freq='10min'),'ice':0.}))
        f=pd.concat(parts,ignore_index=True);f.loc[0:20,'ice']=1.;p=np.zeros(len(f),bool);p[10:40]=True
        valid=np.ones(len(f),bool);valid[-1]=False
        score,_=DailyAccumulator(f,valid).compute(p)
        report,_,_=runtime_daily(f,np.where(valid,p,np.nan))
        self.assertAlmostEqual(score[0].mean(),report['f1_fixed_population'])
    def test_persistence_breaks_at_gap_and_winter_boundary(self):
        f=pd.DataFrame({'station':'12207','time':pd.to_datetime(['2024-11-01 00:00','2024-11-01 00:10','2024-11-01 00:20','2024-11-01 00:40','2025-11-01 00:00','2025-11-01 00:10','2025-11-01 00:20'])})
        np.testing.assert_array_equal(consecutive(f,np.ones(7,bool),3),[0,0,1,0,0,0,1])

if __name__=='__main__':unittest.main()
