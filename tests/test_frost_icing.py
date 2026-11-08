import numpy as np
from src.frost_icing import frost_policies


def test_union_preserves_every_baseline_alert_and_missing():
    p,flags=frost_policies(np.array([-1.,1.,2.,0.]),np.array([-1.,1.,2.,0.]),np.array([20.,90.,50.,90.]),
        np.array([2.,-4.,3.,-2.]),np.array([-1.,1.,2.,0.]),np.array([20.,90.,50.,90.]),
        np.zeros(4,bool),np.array([True,True,True,False]))
    np.testing.assert_array_equal(p['union_frost_estimates'][:3],[1,1,0])
    np.testing.assert_array_equal(p['frost_estimates'][:3],[0,1,0])
    assert all(np.isnan(v[3]) for v in p.values())
    assert flags['estimates_physical_available'].all()


def test_incomplete_physics_falls_back_without_turning_missing_into_negative():
    p,flags=frost_policies(np.array([-1.,1.]),np.array([-1.,1.]),np.array([np.nan,np.nan]),
        np.array([-3.,-3.]),np.array([-1.,1.]),np.array([np.nan,np.nan]),np.ones(2,bool),np.ones(2,bool))
    for v in p.values():np.testing.assert_array_equal(v,[1,0])
    assert not flags['estimates_physical_available'].any()
