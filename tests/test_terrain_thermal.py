import numpy as np
import pandas as pd
from src.terrain_thermal import solar_terrain_inputs


def test_terrain_shading_changes_sun_proxy_without_changing_astronomy():
    times=pd.date_range('2025-01-15',periods=144,freq='10min')
    terrain={f'horizon_{i:02d}_deg':0. for i in range(16)}
    terrain.update(dsm_elevation_m=100.,dsm_relative_500m=2.,dsm_percentile_500m=.5,
                   horizon_max_deg=0.,sky_view_proxy=1.)
    flat=solar_terrain_inputs(times,36.,127.,terrain)
    terrain.update({f'horizon_{i:02d}_deg':40. for i in range(16)})
    shaded=solar_terrain_inputs(times,36.,127.,terrain)
    np.testing.assert_array_equal(flat.solar_altitude_deg,shaded.solar_altitude_deg)
    assert flat.terrain_sun_visible.sum()>0 and shaded.terrain_sun_visible.sum()==0
    assert (flat.loc[flat.solar_altitude_deg<=0,'terrain_solar_proxy']==0).all()
    assert (flat.terrain_solar_proxy>=shaded.terrain_solar_proxy).all()
