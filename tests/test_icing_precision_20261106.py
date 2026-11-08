"""정밀도 연구: 미래 입력 차단과 공식 집계에 대한 정확 선택 검산."""
import unittest
import numpy as np
import pandas as pd
from src.icing_precision_20261106 import WEATHER,features,exact_threshold,binary_prediction
from src.official_metrics_20261106 import evaluate


class PrecisionResearchTests(unittest.TestCase):
    def test_history_is_strictly_past_and_outcome_free(self):
        t=pd.date_range('2024-11-01',periods=180,freq='10min')
        f=pd.DataFrame({'station':'12207','time':t,**{c:np.arange(len(t),dtype=float)/100 for c in WEATHER}})
        f['asos_humidity']=80.
        original=features(f,'process')
        changed=f.copy()
        changed.loc[120:,WEATHER]=99.
        changed['ice']=np.nan
        actual=features(changed,'process')
        pd.testing.assert_frame_equal(original.iloc[:120],actual.iloc[:120])
        self.assertAlmostEqual(original.loc[60,'air_prior_60m'],np.mean(f.loc[54:59,'asos_air_temp']),places=8)
        self.assertTrue(original.loc[:4,'air_prior_60m'].isna().all())
        with self.assertRaises(ValueError):
            features(pd.concat([f,f.iloc[:1]],ignore_index=True),'process')

    def test_threshold_matches_exhaustive_official_mean(self):
        t=pd.date_range('2024-11-01',periods=12,freq='10min').append(pd.date_range('2024-11-02',periods=12,freq='10min'))
        f=pd.DataFrame({'station':np.repeat(['12207','23404','33205'],24),'time':list(t)*3,
                        'available':True,'asos_air_temp':-1.,'ice':0.})
        f.loc[[0,1,2,12,30,31,40],'ice']=1.
        f.loc[6,'ice']=np.nan
        f.loc[8,'available']=False
        f.loc[32,'asos_air_temp']=5.
        rng=np.random.default_rng(20261106)
        for _ in range(4):
            scores=rng.choice([.1,.3,.5,.8],len(f))
            rows=[]
            for threshold in np.unique(scores):
                p=binary_prediction(f,scores,threshold)
                m,_,_=evaluate(f,p,minimum_valid_slots=1,winters=[('2024-11-01','2024-11-03')])
                rows.append(dict(threshold=threshold,**m))
            table=pd.DataFrame(rows)
            precision_floor=float(table.f1.min())
            actual=exact_threshold(f,scores,recall_floor=.40,precision_f1_floor=precision_floor)
            for track in ['f1','precision']:
                candidates=table.loc[table.recall.ge(.40-1e-12)]
                if track=='precision':
                    candidates=candidates.loc[candidates.f1.ge(precision_floor-1e-12)]
                best=candidates.sort_values([track,'fp','threshold'],ascending=[False,True,False]).iloc[0]
                # 실제 Ice 없는 지점 FP는 이 선택의 동률 지표에서 제외. 목적값과 공식 집계를 검산한다.
                self.assertAlmostEqual(actual[track][track],best[track],places=12)
                m,_,_=evaluate(f,binary_prediction(f,scores,actual[track]['threshold']),minimum_valid_slots=1,winters=[('2024-11-01','2024-11-03')])
                for key in ['f1','precision','recall']:
                    self.assertAlmostEqual(actual[track][key],m[key],places=12)
        empty=f.copy()
        empty.ice=0.
        with self.assertRaises(ValueError):
            exact_threshold(empty,np.full(len(empty),.5))

    def test_all_training_classes_are_validated(self):
        from src.icing_precision_20261106 import weights
        f=pd.DataFrame(dict(station=['12207','23404'],winter=[2024,2024],ice=[0,1]))
        np.testing.assert_array_equal(weights(f,'station'),[1.,1.])
        f.loc[0,'ice']=2
        with self.assertRaises(ValueError):
            weights(f,'station')


if __name__=='__main__':
    unittest.main()
