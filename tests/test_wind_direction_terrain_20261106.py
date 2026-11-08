import unittest
import numpy as np,pandas as pd
from src.wind_direction_terrain_20261106 import direction_features,terrain_features
class WindDirectionTerrainTests(unittest.TestCase):
 def test_calm_is_not_north_and_north_is_360(self):
  f,a=direction_features(pd.Series([0,360,20,990,np.nan]),pd.Series([.2,2,2,2,2]))
  self.assertTrue(np.isnan(a.iloc[0]));self.assertEqual(a.iloc[1],0);self.assertEqual(a.iloc[2],22.5)
  self.assertEqual(f.direction_calm.iloc[0],1);self.assertEqual(f.direction_missing.iloc[3],1)
  self.assertAlmostEqual(f.direction_v.iloc[1],-2)
 def test_low_speed_direction_is_unknown_and_future_unavailable_not_filled(self):
  f,a=direction_features(pd.Series([90,np.nan,90]),pd.Series([.3,np.nan,2]))
  self.assertTrue(a.iloc[:2].isna().all());self.assertEqual(f.direction_missing.iloc[1],1);self.assertAlmostEqual(f.direction_u.iloc[2],-2)
 def test_circular_horizon_interpolation_and_unknown(self):
  t=pd.DataFrame({'station':['x'],**{c:[0] for c in ['dsm_elevation_m','dsm_relative_500m','dsm_percentile_500m','horizon_max_deg','sky_view_proxy']},**{f'horizon_{i:02d}_deg':[i] for i in range(16)}}).set_index('station')
  x=terrain_features(pd.Series(['x','x','x']),pd.Series([348.75,0,np.nan]),pd.Series([1,1,1]),t)
  self.assertAlmostEqual(x.terrain_upwind_horizon_deg.iloc[0],7.5);self.assertAlmostEqual(x.terrain_downwind_horizon_deg.iloc[0],7.5)
  self.assertEqual(x.terrain_upwind_horizon_deg.iloc[1],0);self.assertTrue(np.isnan(x.terrain_upwind_horizon_deg.iloc[2]))
if __name__=='__main__':unittest.main()