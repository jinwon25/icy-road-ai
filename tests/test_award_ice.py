import unittest
import numpy as np
import pandas as pd
from src.award_ice import threshold_curve, past_score, select_row, history_features, station_class_weights
from src.qa633_metrics import daily_table, aggregate
from src.submission_runtime import FEATURES


class AwardIceTests(unittest.TestCase):
    def test_threshold_curve_matches_daily_reference_and_boundaries(self):
        rng=np.random.default_rng(12)
        f=pd.DataFrame({'station':np.repeat(['12207','12408'],288),
            'time':list(pd.date_range('2024-11-01',periods=288,freq='10min'))*2,
            'ice':rng.choice([0.,1.,np.nan],576,p=[.8,.19,.01])})
        score=rng.choice([0.,.25,.5,1.],len(f))
        thresholds=np.array([0.,.25,.5,1.,1.000001])
        for minimum in [1,130,144]:
            table=threshold_curve(f,score,thresholds,minimum)
            for row in table.itertuples():
                prediction=(score>=row.threshold).astype(int)
                days=daily_table(f,prediction,['12207','12408'],minimum)
                report,stations=aggregate(days,['12207','12408'])
                self.assertAlmostEqual(row.f1_fixed_population,stations.f1.fillna(0).mean(),places=14)
                self.assertEqual(row.f1_days,report['f1_days'])
                self.assertEqual(row.f1_defined_stations,report['f1_stations'])
                self.assertEqual(row.tp,int(((f.ice==1)&(prediction==1)).sum()))
                self.assertEqual(row.fp,int(((f.ice==0)&(prediction==1)).sum()))

    def test_undefined_negative_station_cannot_disappear_from_selection(self):
        f=pd.DataFrame({'station':['12207','12408'],'time':pd.Timestamp('2024-11-01'),'ice':[1.,0.]})
        row=threshold_curve(f,[1.,0.],np.array([.5]),1).iloc[0]
        self.assertEqual(row.f1_fixed_population,.5)
        self.assertEqual(row.f1_defined_stations,1)

    def test_smoothing_is_causal_grouped_and_handles_gaps(self):
        f=pd.DataFrame({'station':['12207']*4+['12408'],
            'time':pd.to_datetime(['2024-11-01 00:00','2024-11-01 00:10','2024-11-01 00:20','2024-11-01 03:00','2024-11-01 00:00'])})
        a=past_score(f,[0,0,0,1,1],30)
        b=past_score(f,[0,0,0,0,0],30)
        np.testing.assert_array_equal(a[:3],b[:3])
        self.assertEqual(a[3],1.)
        self.assertEqual(a[4],1.)

    def test_history_excludes_current_and_future(self):
        f=pd.DataFrame({'station':['12207']*150,'time':pd.date_range('2024-11-01',periods=150,freq='10min')})
        for c in FEATURES:f[c]=1.
        a=history_features(f)
        f.loc[100:,'aws_air_temp']=1000.
        b=history_features(f)
        self.assertEqual(a.loc[100,'aws_air_temp_past_6h_mean'],b.loc[100,'aws_air_temp_past_6h_mean'])
        self.assertNotEqual(a.loc[101,'aws_air_temp_past_6h_mean'],b.loc[101,'aws_air_temp_past_6h_mean'])
        self.assertTrue(a.loc[0,'aws_air_temp_past_24h_mean']!=a.loc[0,'aws_air_temp_past_24h_mean'])

    def test_selection_tie_prefers_fewer_false_alarms(self):
        t=pd.DataFrame({'candidate':['a','b'],'smoothing_minutes':[0,0],
            'threshold':[.1,.2],'f1_fixed_population':[.1,.1],'fp':[100,10]})
        self.assertEqual(select_row(t)['candidate'],'b')

    def test_weights_balance_station_classes_and_reject_protected(self):
        f=pd.DataFrame({'station':['12207']*4+['12408']*4,
            'time':list(pd.date_range('2024-11-01',periods=4,freq='10min'))*2,'ice':[1,0,0,0,1,1,0,0]})
        f['weight']=station_class_weights(f)
        np.testing.assert_allclose(f.groupby(['station','ice']).weight.sum(),2.)
        f.loc[0,'station']='12410'
        with self.assertRaises(ValueError):station_class_weights(f)


if __name__=='__main__':unittest.main()
