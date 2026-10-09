import unittest
import numpy as np
import pandas as pd
from src.point_inputs import PointInputBuilder,AWS_VARIABLES
from src.moisture_memory import MEMORY_FEATURES
from scripts.audit_ice_weather_history import HISTORY


class PointInputTests(unittest.TestCase):
    def tables(self):
        aws=pd.DataFrame({'station':['a','b','c'],'source_time':pd.to_datetime(['2025-01-01 09:00','2025-01-01 10:00','2025-01-01 10:00'])})
        for c in [*AWS_VARIABLES,*HISTORY,*MEMORY_FEATURES]:aws[c]=1.
        aws['air_temp']=[2.,3.,4.]
        asos=pd.DataFrame({'station':['s'],'source_time':pd.to_datetime(['2025-01-01 10:00']),'air_temp':[1.],'ground_temp':[1.]})
        rwis=pd.DataFrame({'station':['12103','12209'],'time':pd.to_datetime(['2025-01-01 10:00']*2),'road_temp':[-1.,-2.],'temp_min60':[-1.,-2.],
                           'temp_trend60':[0.,0.],'humidity':[90.,95.],'rain10':[0.,0.]})
        coords=pd.DataFrame({'kind':['AWS']*3+['ASOS'],'station_id':['a','b','c','s'],'latitudes':[35.,35.01,35.02,35.],'longitudes':[127.]*4})
        meta=pd.DataFrame({'station':['12103','12209'],'route':['R','R'],'lat':[35.,35.1],'lon':[127.,127.]})
        return aws,asos,rwis,coords,meta

    def test_fallback_prior_time_and_self_exclusion(self):
        builder=PointInputBuilder(*self.tables())
        point={'station':'12103','route':'R','lat':35.,'lon':127.}
        result,mapping=builder.build(point,pd.to_datetime(['2025-01-01 10:10']))
        self.assertEqual(result.aws_station.iloc[0],'b');self.assertEqual(result.aws_rank.iloc[0],2)
        self.assertEqual(mapping['near_source'],'12209');self.assertEqual(result.near_road_temp.iloc[0],-2)
        earlier,_=builder.build(point,pd.to_datetime(['2025-01-01 10:00']))
        self.assertEqual(earlier.aws_station.iloc[0],'a');self.assertTrue(np.isnan(earlier.near_road_temp.iloc[0]))

    def test_forbidden_reference_and_target_measurements(self):
        builder=PointInputBuilder(*self.tables());point={'station':'12103','route':'R','lat':35.,'lon':127.}
        result,mapping=builder.build(point,pd.to_datetime(['2025-01-01 10:10']),{'12209'})
        self.assertIsNone(mapping['near_source']);self.assertTrue(result.near_road_temp.isna().all())
        with self.assertRaises(ValueError):builder.build({**point,'ice':1},pd.to_datetime(['2025-01-01 10:10']))

    def test_protected_source_rejected(self):
        values=list(self.tables());values[2].loc[0,'station']='12410'
        with self.assertRaises(ValueError):PointInputBuilder(*values)

    def test_road_route_alias_and_unknown_route(self):
        values=list(self.tables());values[4]['route']='서해안'
        builder=PointInputBuilder(*values)
        point={'station':'segment','route':'서해안고속국도','lat':35.,'lon':127.}
        result,mapping=builder.build(point,pd.to_datetime(['2025-01-01 10:10']))
        self.assertEqual(mapping['near_source'],'12103')
        self.assertEqual(result.near_road_temp.iloc[0],-1.)
        with self.assertRaises(ValueError):builder.build({**point,'route':'unknown'},pd.to_datetime(['2025-01-01 10:10']))


if __name__=='__main__':unittest.main()
