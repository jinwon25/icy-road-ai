import unittest
import numpy as np
import pandas as pd
from src.external_quality import quality_tables


class ExternalQualityTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame({'station': ['12207']*5,
            'time': pd.to_datetime(['2024-11-01 00:00','2024-11-01 00:10','2024-11-01 00:20','2024-11-01 00:40','2024-11-01 00:50']),
            'state_raw': ['04','04','0','04','13'], 'ice': [1.,1.,np.nan,1.,0.], 'road_temp': [-1.,5.,0.,4.,-2.]})

    def test_unknown_and_time_gaps_break_runs_without_filtering_warm_ice(self):
        station, daily, runs = quality_tables(self.frame(), {'development_start_kst':'2024-11-01','development_end_kst':'2024-11-01'})
        self.assertEqual(station.ice_rows.iloc[0],3)
        self.assertEqual(station.ice_temperature_above_2c_rows.iloc[0],2)
        self.assertEqual(runs.observed_consecutive_slots.tolist(),[2,1])
        self.assertEqual(daily.valid_state_rows.iloc[0],4)
        self.assertEqual(station.undefined_state_rows.iloc[0],1)

    def test_changed_label_or_reserved_date_rejected(self):
        frame=self.frame(); plan={'development_start_kst':'2024-11-01','development_end_kst':'2024-11-01'}
        frame.loc[4,'ice']=1.
        with self.assertRaises(ValueError): quality_tables(frame,plan)
        frame=self.frame(); frame['time']=frame.time+pd.DateOffset(years=1)
        with self.assertRaises(ValueError): quality_tables(frame,plan)


if __name__=='__main__': unittest.main()
