import unittest
import numpy as np
import pandas as pd
from src.submission_runtime import FEATURES, prepare_weather, infer


def example():
    f = pd.DataFrame({c:[0., 0., 0.] for c in FEATURES})
    f['station'] = 'example'; f['time'] = pd.date_range('2024-12-01',periods=3,freq='10min')
    f['asos_air_temp'] = -1.; f['aws_dewpoint'] = 0.
    f['rain15_max_3h'] = 0.; f['asos_snow_cm'] = 0.
    return f


class Model:
    feature_names_in_ = np.array(FEATURES)
    def __init__(self, value=-1.): self.value = value
    def predict(self, x): return np.full(len(x), self.value)


class RuntimeTests(unittest.TestCase):
    def test_missing_asos_and_water_abstain(self):
        f=example(); f.loc[1,'asos_air_temp']=np.nan
        f.loc[2,['aws_dewpoint','rain15_max_3h','asos_snow_cm']]=np.nan
        r=infer(f,[Model(),Model()])
        self.assertEqual(r.predicted_ice.iloc[0],1)
        self.assertTrue(r.predicted_ice.iloc[1:].isna().all())
        self.assertEqual(r.condition_evidence.iloc[2],'insufficient_input')

    def test_stale_weather_and_sentinel(self):
        f=example(); f.loc[1,'aws_age_minutes']=61
        f.loc[2,'aws_dewpoint']=-99.9
        clean,_,stale=prepare_weather(f)
        self.assertTrue(stale.iloc[1]); self.assertTrue(clean.aws_dewpoint.iloc[1:].isna().all())

    def test_target_columns_rejected(self):
        for c in ['road_temp','ice','state_raw','LABEL']:
            f=example(); f[c]=0
            with self.assertRaises(ValueError): prepare_weather(f)

    def test_future_and_duplicates_rejected(self):
        for kind in ['future','duplicate','fraction']:
            f=example()
            if kind=='future': f.loc[0,'aws_age_minutes']=-1
            if kind=='duplicate': f.loc[1,'time']=f.time.iloc[0]
            if kind=='fraction': f.loc[0,'time']+=pd.Timedelta(nanoseconds=1)
            with self.assertRaises(ValueError): prepare_weather(f)

    def test_disagreement_is_separate_from_probability(self):
        r=infer(example(),[Model(-2.),Model(1.)])
        self.assertTrue(r.predicted_ice.eq(1).all())
        self.assertTrue(r.condition_evidence.eq('cold_wet_disagreement').all())
        self.assertNotIn('probability',r)

    def test_utc_is_kst(self):
        f=example(); f['time']=pd.date_range('2024-11-30 15:00',periods=3,freq='10min',tz='UTC')
        clean,_,_=prepare_weather(f)
        self.assertEqual(clean.time.iloc[0],pd.Timestamp('2024-12-01'))


if __name__=='__main__': unittest.main()
