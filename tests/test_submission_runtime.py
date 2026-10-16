import unittest
from pathlib import Path
import tempfile
import io
from contextlib import redirect_stdout
from unittest.mock import patch
import numpy as np
import pandas as pd
from src.submission_runtime import FEATURES, prepare_weather, infer, main
from src.submission_io import read_weather


def example():
    f = pd.DataFrame({c:[0., 0., 0.] for c in FEATURES})
    f['station'] = 'example'; f['time'] = pd.date_range('2024-12-01',periods=3,freq='10min')
    f['asos_air_temp'] = -1.; f['aws_dewpoint'] = 0.
    f['rain15_max_3h'] = 0.; f['asos_snow_cm'] = 0.
    f[['aws_age_minutes', 'asos_age_minutes']] = 10.
    return f


class Model:
    feature_names_in_ = np.array(FEATURES)
    def __init__(self, value=-1.): self.value = value
    def predict(self, x): return np.full(len(x), self.value)


class BoundaryModel(Model):
    def predict(self, x):
        return np.where(x.hour_sin.to_numpy() >= 0.10000000000000002, -1., 1.)


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

    def test_canonical_station_duplicate_and_zero_age_rejected(self):
        f=example(); f.loc[0,'station']='12207'; f.loc[1,'station']='12207.0'
        f.loc[1,'time']=f.time.iloc[0]
        with self.assertRaises(ValueError): prepare_weather(f)
        for column in ['aws_age_minutes','asos_age_minutes']:
            f=example(); f.loc[0,column]=0
            with self.assertRaises(ValueError): prepare_weather(f)

    def test_cli_preserves_float_boundary_across_csv_and_parquet(self):
        f=example(); f['hour_sin']=0.10000000000000002
        with tempfile.TemporaryDirectory() as tmp:
            outputs=[]
            for extension in ['csv','parquet']:
                source=Path(tmp)/('input.'+extension); target=Path(tmp)/('output.'+extension)
                if extension=='csv': f.to_csv(source,index=False)
                else: f.to_parquet(source,index=False)
                with patch('sys.argv',['predict','--input',str(source),'--output',str(target)]), \
                        patch('src.submission_runtime.joblib.load',return_value=BoundaryModel()), redirect_stdout(io.StringIO()):
                    main()
                outputs.append(read_weather(target))
            np.testing.assert_array_equal(outputs[0].estimated_road_temp_c,[-1.,-1.,-1.])
            for column in ['estimated_road_temp_c','predicted_ice']:
                np.testing.assert_array_equal(outputs[0][column],outputs[1][column])


if __name__=='__main__': unittest.main()
