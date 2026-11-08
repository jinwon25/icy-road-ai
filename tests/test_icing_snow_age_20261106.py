"""잔존 적설 필터의 시간 방향·결측 복귀·다른 수분 근거 보존을 검증한다."""
import unittest
import numpy as np
import pandas as pd
from src.icing_snow_age_20261106 import snow_growth_history,filter_snow_alerts


class SnowAgeTests(unittest.TestCase):
    def test_causality_and_insufficient_history(self):
        f=pd.DataFrame(dict(station='12207',time=pd.date_range('2024-11-01',periods=600,freq='10min'),
                            asos_snow_cm=10.,asos_new_snow3h=np.nan))
        h=snow_growth_history(f)
        self.assertTrue(h.loc[:33,'snow_growth_6h'].isna().all())
        self.assertEqual(h.loc[48,'snow_growth_6h'],0.)
        g=f.copy();g.loc[100:,'asos_snow_cm']=15.
        changed=snow_growth_history(g)
        pd.testing.assert_frame_equal(h.iloc[:100],changed.iloc[:100])
        # 현재의 증가는 다음 시각부터 과거 근거가 된다.
        self.assertEqual(changed.loc[100,'snow_growth_6h'],0.)
        self.assertEqual(changed.loc[101,'snow_growth_6h'],1.)
        # 결측 신적설은 깊이 증가를 알 수 없는 행을 0으로 바꾸지 않는다.
        missing=f.copy();missing.asos_snow_cm=np.nan
        self.assertTrue(snow_growth_history(missing).isna().all().all())

    def test_only_known_old_snow_only_alerts_are_removed(self):
        f=pd.DataFrame(dict(station='12207',time=pd.date_range('2024-11-01',periods=5,freq='10min'),
                            aws_dewpoint=[-5.,-5.,0.,-5.,-5.],aws_age_minutes=10.,
                            rain15_max_3h=[0.,1.,0.,0.,0.],asos_snow_cm=10.))
        runtime=f[['station','time']].copy()
        runtime['estimated_road_temp_c']=-1.
        runtime['predicted_ice']=pd.array([1.,1.,1.,1.,np.nan],dtype='Int64')
        h=pd.DataFrame({k:[0.,0.,0.,np.nan,0.] for k in ['snow_growth_6h','snow_growth_24h','snow_growth_72h']})
        actual=filter_snow_alerts(f,runtime,h)
        np.testing.assert_array_equal(actual['snow_growth_6h'],[0.,1.,1.,1.,np.nan])
        with self.assertRaises(ValueError):
            snow_growth_history(f.assign(ice=0))


if __name__=='__main__':unittest.main()
