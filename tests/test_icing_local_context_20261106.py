"""가까운 기상·지형 입력의 열 계약과 오래된 AWS 관측 마스킹을 검증한다."""
import unittest
import numpy as np
import pandas as pd
from src.icing_precision_20261106 import WEATHER
from src.icing_local_context_20261106 import features,AWS,TERRAIN

class LocalContextTests(unittest.TestCase):
    def test_representation_counts_and_stale_aws(self):
        f=pd.DataFrame(dict(station='12207',time=pd.date_range('2024-11-01',periods=60,freq='10min'),
             **{c:1. for c in WEATHER},**{c:2. for c in AWS},aws_age_minutes=10.,
             **{c:3. for c in TERRAIN}))
        f.loc[10,'aws_age_minutes']=70.
        a=features(f,'process');b=features(f,'local');c=features(f,'terrain')
        self.assertEqual((len(a.columns),len(b.columns),len(c.columns)),(53,59,68))
        pd.testing.assert_frame_equal(a,b.iloc[:,:53])
        self.assertTrue(b.loc[10,AWS].isna().all())
        self.assertEqual(b.loc[11,'aws_air_temp'],2.)
        self.assertFalse({'ice','road_temp','state_raw','station'}&set(c.columns))
        altered=f.assign(ice=1.,road_temp=-100.,state_raw='04')
        pd.testing.assert_frame_equal(c,features(altered,'terrain'))

if __name__=='__main__':unittest.main()
