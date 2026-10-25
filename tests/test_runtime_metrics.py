import unittest
import numpy as np
import pandas as pd
from src.runtime_metrics import runtime_daily


class RuntimeMetricTests(unittest.TestCase):
    def test_all_predictions_missing_never_become_true_negatives(self):
        frame=pd.DataFrame({'station':['12207']*144,'time':pd.date_range('2024-11-01',periods=144,freq='10min'),
            'winter':2024,'ice':0.})
        report,stations,days=runtime_daily(frame,np.full(144,np.nan),1)
        self.assertEqual(days.valid_slots.sum(),0)
        self.assertEqual(days.tn.sum(),0)
        self.assertEqual(report['missing_prediction_rows'],144)
        self.assertFalse(days.coverage_accepted.any())

    def test_invalid_binary_and_infinite_prediction_rejected(self):
        frame=pd.DataFrame({'station':['12207'],'time':[pd.Timestamp('2024-11-01')],'winter':[2024],'ice':[1.]})
        for p in [[2.],[np.inf],[]]:
            with self.subTest(p=p),self.assertRaises(ValueError):runtime_daily(frame,p)

if __name__=='__main__':unittest.main()
