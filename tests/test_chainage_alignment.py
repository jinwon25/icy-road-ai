import numpy as np
import pandas as pd
from src.chainage_alignment import aggregate_anchors, interpolate_checked, overlap_sensitivity


def test_interpolation_does_not_extrapolate_or_bridge_long_gap():
    anchors = pd.DataFrame({'x_m':[0., 1000., 6000.], 'km':[20., 19., 14.]})
    km, _, valid = interpolate_checked([-1,0,500,1000,2000,6000,6001], anchors)
    assert valid.tolist() == [False,True,True,True,False,True,False]
    np.testing.assert_allclose(km[valid], [20,19.5,19,14])


def test_coordinate_duplicates_stay_together():
    frame = pd.DataFrame({'longitude':[1,1,2,3], 'latitude':[1,1,2,3],
                          'x_m':[0,0,100,200], 'chainage_km':[1,1.02,1.1,1.2],
                          'source_row':[1,2,3,4], 'distance_m':[3,3,4,5]})
    a, sign = aggregate_anchors(frame)
    assert len(a)==3 and a.iloc[0].source_rows=='1|2' and sign==1
    assert a.iloc[0].km==1.01


def test_interval_uncertainty_and_boundary_contact():
    np.testing.assert_allclose(overlap_sensitivity(10,10.5,10.5,11,250), [0,0,.25])
    n,g,p = overlap_sensitivity(10,11,10.2,10.8,100)
    assert g <= n <= p and abs(n-.6)<1e-10
