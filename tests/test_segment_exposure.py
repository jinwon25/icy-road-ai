import unittest
import numpy as np
import pandas as pd
from src.segment_exposure import exposure,weighted_summary,CachedWeatherPoints,WeatherOnlySources
from src.point_inputs import PointInputBuilder,AWS_VARIABLES
from src.moisture_memory import MEMORY_FEATURES
from scripts.audit_ice_weather_history import HISTORY
from scripts.baseline_ice_logistic import FEATURES


class SegmentExposureTests(unittest.TestCase):
    def test_weather_only_sources_reject_road_outcomes(self):
        for name in ['ice','state_raw','road_temp','SFS','TR1','near_road_temp']:
            with self.assertRaises(ValueError):WeatherOnlySources(pd.DataFrame({name:[1]}),pd.DataFrame(),pd.DataFrame())
    def test_missing_moisture_does_not_become_a_safe_slot(self):
        f=pd.DataFrame({'aws_dewpoint':[-2,np.nan,-1],'rain15_max_3h':[0,np.nan,1],'asos_snow_cm':[0,np.nan,0]})
        r,p,valid=exposure([-1,-5,2],f)
        np.testing.assert_array_equal(valid,[True,False,True]);self.assertEqual(r['valid_slots'],2);self.assertEqual(r['cold_moist_fraction'],0)
        self.assertEqual(r['cold_hours'],1/6);self.assertEqual(r['valid_fraction'],2/3)
    def test_temperature_and_any_one_moisture_condition_are_both_required(self):
        f=pd.DataFrame({'aws_dewpoint':[-2,-2,3],'rain15_max_3h':[0,1,0],'asos_snow_cm':[1,0,0]})
        r,p,_=exposure([-1,-1,2],f);np.testing.assert_array_equal(p,[True,True,False]);self.assertEqual(r['cold_moist_hours'],2/6)
    def test_boundary_children_are_weighted_by_retained_geometry_length(self):
        r=weighted_summary(pd.DataFrame({'fraction':[1.,0.]}),[100.,500.],['fraction'])
        self.assertEqual(r['fraction'],1/6)
        with self.assertRaises(ValueError):weighted_summary(pd.DataFrame({'fraction':[1.,0.]}),[0.,500.],['fraction'])
    def test_cached_weather_matches_full_prior_builder_at_staleness_boundary(self):
        aws=pd.DataFrame({'station':['a','b','c'],'source_time':pd.to_datetime(['2025-01-01 09:00','2025-01-01 10:00','2025-01-01 10:00'])})
        for c in [*AWS_VARIABLES,*HISTORY,*MEMORY_FEATURES]:aws[c]=1.
        aws['air_temp']=[2.,3.,4.]
        asos=pd.DataFrame({'station':['s'],'source_time':pd.to_datetime(['2025-01-01 10:00']),'air_temp':[1.],'ground_temp':[1.],'snow_cm':[0.]})
        rwis=pd.DataFrame({'station':['12103'],'time':pd.to_datetime(['2025-01-01 10:00']),'road_temp':[-1.],'temp_min60':[-1.],'temp_trend60':[0.],'humidity':[90.],'rain10':[0.]})
        coords=pd.DataFrame({'kind':['AWS']*3+['ASOS'],'station_id':['a','b','c','s'],'latitudes':[35.,35.01,35.02,35.],'longitudes':[127.]*4})
        meta=pd.DataFrame({'station':['12103'],'route':['R'],'lat':[35.],'lon':[127.]})
        builder=PointInputBuilder(aws,asos,rwis,coords,meta);times=pd.to_datetime(['2025-01-01 10:00','2025-01-01 10:10'])
        full,_=builder.build({'station':'12206','route':'R','lat':35.,'lon':127.},times);cached,_=CachedWeatherPoints(builder,times).build(35.,127.)
        cols=FEATURES+['rain15_max_3h','asos_snow_cm'];pd.testing.assert_frame_equal(full[cols],cached[cols],check_dtype=False,rtol=0,atol=0)
        self.assertEqual(cached.aws_station.tolist(),['a','b'])


if __name__=='__main__':unittest.main()
