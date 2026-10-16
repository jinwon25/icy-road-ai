import unittest
import numpy as np
import pandas as pd
from src.asos_gap_fallback import AsosGapFallback,apply_weather_fallback


def source():
    observations=pd.DataFrame({'station':['A','B','B','C'],'source_time':pd.to_datetime(['2024-11-01 12:00','2024-11-01 11:00','2024-11-01 12:00','2024-11-01 12:00']),
        'air_temp':[1.,2.,3.,4.],'snow_cm':[0.,0.,0.,0.]})
    coordinates=pd.DataFrame({'station':['A','B','C'],'lat':[35.,35.1,36.],'lon':[127.,127.,127.]})
    return observations,coordinates


class AsosGapTests(unittest.TestCase):
    point={'station':'12410','lat':35.,'lon':127.}

    def test_exact_target_observation_is_excluded_and_sixty_minutes_is_allowed(self):
        engine=AsosGapFallback(*source())
        selected=engine.select(self.point,pd.to_datetime(['2024-11-01 12:00','2024-11-01 12:10']),exclude=['A'])
        self.assertEqual(selected.air_temp.tolist(),[2.,3.]);self.assertEqual(selected.age_minutes.tolist(),[60.,10.])
        self.assertTrue((selected.source_time<selected.time).all())

    def test_stale_and_distant_sources_do_not_fill(self):
        engine=AsosGapFallback(*source())
        selected=engine.select(self.point,pd.to_datetime(['2024-11-01 13:10']),exclude=['A'])
        self.assertTrue(selected.selected_asos_station.isna().all())
        selected=engine.select(self.point,pd.to_datetime(['2024-11-01 12:10']),exclude=['A','B'])
        self.assertTrue(selected.selected_asos_station.isna().all())

    def test_future_value_cannot_change_weather_selection(self):
        a,c=source();engine=AsosGapFallback(a,c)
        selected=engine.select(self.point,pd.to_datetime(['2024-11-01 12:00']),exclude=['A'])
        a.loc[a.source_time.eq(pd.Timestamp('2024-11-01 12:00')),'air_temp']=50.
        actual=AsosGapFallback(a,c).select(self.point,pd.to_datetime(['2024-11-01 12:00']),exclude=['A'])
        pd.testing.assert_frame_equal(actual,selected)

    def test_existing_valid_input_and_outcome_columns_are_protected(self):
        engine=AsosGapFallback(*source());selected=engine.select(self.point,pd.to_datetime(['2024-11-01 12:10']))
        frame=selected[['station','time']].assign(asos_air_temp=-3.,asos_age_minutes=10.,asos_snow_cm=1.)
        result,replaced=apply_weather_fallback(frame,selected)
        pd.testing.assert_frame_equal(result,frame);self.assertFalse(replaced.any())
        a,c=source();a['road_temp']=0
        with self.assertRaises(ValueError):AsosGapFallback(a,c)

    def test_selection_identity_and_nanosecond_grid_are_checked(self):
        engine=AsosGapFallback(*source())
        with self.assertRaises(ValueError):engine.select(self.point,pd.to_datetime(['2024-11-01 12:10:00.000000001']))
        selected=engine.select(self.point,pd.to_datetime(['2024-11-01 12:10']))
        frame=selected[['station','time']].assign(asos_air_temp=np.nan,asos_age_minutes=np.nan,asos_snow_cm=np.nan)
        selected['station']='23402'
        with self.assertRaises(ValueError):apply_weather_fallback(frame,selected)
