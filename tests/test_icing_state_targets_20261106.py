"""다상태 보조 정답에서 Ice만 양성으로 유지하는지 검증한다."""
import unittest
import numpy as np
import pandas as pd
from src.icing_state_targets_20261106 import state_targets,state_day_weights

class StateTargetTests(unittest.TestCase):
    def test_mapping_preserves_binary_target_and_missing(self):
        raw=['01','10','02','11','12','13','14','03','04','15','00',None,-999]
        ice=[0,0,0,0,0,0,0,0,1,0,np.nan,np.nan,np.nan]
        expected=[0,0,1,1,1,1,1,2,3,4,np.nan,np.nan,np.nan]
        np.testing.assert_array_equal(state_targets(raw,ice),expected)
        with self.assertRaises(AssertionError):
            state_targets(['04'],[0.])
    def test_day_class_balance_is_local(self):
        f=pd.DataFrame(dict(station=['12207']*6,winter=[2024]*6,
            time=pd.to_datetime(['2024-11-01 00:00','2024-11-01 00:10','2024-11-01 00:20',
                                 '2024-11-02 00:00','2024-11-02 00:10','2024-11-02 00:20']),
            state_target=[0,0,3,0,1,3]))
        w=state_day_weights(f)
        self.assertAlmostEqual(w.mean(),1.)
        self.assertAlmostEqual(w[0]+w[1],w[2])
        self.assertAlmostEqual(w[:3].sum(),w[3:].sum())
        np.testing.assert_array_equal(w[3:],[1.,1.,1.])
        with self.assertRaises(ValueError):
            state_day_weights(f.assign(state_target=9.))

if __name__=='__main__':unittest.main()
