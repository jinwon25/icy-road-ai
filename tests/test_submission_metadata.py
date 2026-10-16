import unittest
import pandas as pd
from src.submission_metadata import temperature_evidence


class MetadataTests(unittest.TestCase):
    def test_unequal_station_sizes_distinguish_mae_aggregations(self):
        frame=pd.DataFrame({'station':['12207','12408','12408','12408'],
            'time':pd.to_datetime(['2024-11-01','2024-11-01','2024-11-01 00:10','2024-11-01 00:20'],format='mixed'),
            'road_temp':[0.,0.,0.,0.], 'equal_nohistory_pair':[4.,0.,0.,0.]})
        result=temperature_evidence(frame)
        self.assertEqual(result['temperature_mae_pooled'],1.)
        self.assertEqual(result['temperature_mae_station_mean'],2.)
        self.assertEqual(result['temperature_valid_rows'],4)

    def test_missing_station_temperature_not_hidden(self):
        frame=pd.DataFrame({'station':['12207','12408'],'time':pd.Timestamp('2024-11-01'),
            'road_temp':[0.,float('nan')],'equal_nohistory_pair':[1.,0.]})
        with self.assertRaises(ValueError): temperature_evidence(frame)
