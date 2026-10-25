import unittest
import numpy as np
import pandas as pd
from src.extended_search import feature_table,weights,temperature_gate
from src.submission_runtime import FEATURES

class ExtendedSearchTests(unittest.TestCase):
    def frame(self):
        f=pd.DataFrame({'station':['12207']*160,'time':list(pd.date_range('2024-11-01',periods=80,freq='10min'))+list(pd.date_range('2025-11-01',periods=80,freq='10min')),'winter':[2024]*80+[2025]*80})
        for name in FEATURES:f[name]=1.
        return f
    def test_history_future_and_other_winter_cannot_change_past(self):
        f=self.frame();a=feature_table(f,'history');f.loc[100:,'aws_air_temp']=99.
        b=feature_table(f,'history');pd.testing.assert_frame_equal(a.iloc[:100],b.iloc[:100])
        self.assertTrue(a.loc[80,'aws_air_temp_past_mean_60m']!=a.loc[80,'aws_air_temp_past_mean_60m'])
    def test_derived_features_ignore_outcomes(self):
        f=self.frame();f['road_temp']=1.;a=feature_table(f,'derived');f.road_temp=-999.
        pd.testing.assert_frame_equal(a,feature_table(f,'derived'))
        f.station='12410'
        with self.assertRaises(ValueError):feature_table(f)
    def test_group_weights_have_equal_total_not_equal_rows(self):
        f=pd.DataFrame({'group':['a','a','a','b']});w=weights(f,{'group_balance':True})
        self.assertAlmostEqual(w[:3].sum(),w[3]);self.assertAlmostEqual(w.mean(),1.)
    def test_missing_denominator_change_is_rejected(self):
        f=self.frame();f['road_temp']=0.;f['group']='a'
        with self.assertRaises(ValueError):temperature_gate(f,np.r_[np.nan,np.ones(159)],np.ones(160),{})

if __name__=='__main__':unittest.main()
