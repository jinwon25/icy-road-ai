import unittest
import numpy as np
import pandas as pd
from src.two_winter import validate,history,daily,curve
from src.submission_runtime import FEATURES


class TwoWinterTests(unittest.TestCase):
    def test_curve_matches_date_station_average_across_winters(self):
        rng=np.random.default_rng(10)
        frames=[]
        for winter in [2024,2025]:
            for station in ['12207','12408']:
                frames.append(pd.DataFrame({'station':station,'time':pd.date_range(f'{winter}-11-01',periods=288,freq='10min'),
                    'winter':winter,'ice':rng.choice([0.,1.],288,p=[.9,.1])}))
        f=pd.concat(frames,ignore_index=True);s=rng.choice([0.,.5,1.],len(f))
        c=curve(f,s,np.array([0.,.5,1.,1.01]))
        for row in c.itertuples():
            report,_,days=daily(f,s>=row.threshold)
            self.assertAlmostEqual(row.f1_fixed_population,report['f1_fixed_population'],places=14)
            self.assertEqual(len(days),480)

    def test_history_does_not_carry_between_winters(self):
        f=pd.DataFrame({'station':['12207']*80,
            'time':list(pd.date_range('2024-11-01',periods=40,freq='10min'))+list(pd.date_range('2025-11-01',periods=40,freq='10min')),
            'winter':[2024]*40+[2025]*40})
        for col in FEATURES:f[col]=1.
        f.loc[:39,'aws_air_temp']=100.
        x=history(f)
        self.assertTrue(pd.isna(x.loc[40,'aws_air_temp_past_6h_mean']))
        self.assertEqual(x.loc[79,'aws_air_temp_past_6h_mean'],1.)

    def test_protected_station_and_nonwinter_rejected(self):
        f=pd.DataFrame({'station':['12410'],'time':[pd.Timestamp('2025-11-01')]})
        with self.assertRaises(ValueError):validate(f)
        f.station='12207';f.time=pd.Timestamp('2025-07-01')
        with self.assertRaises(ValueError):validate(f)

if __name__=='__main__':unittest.main()
