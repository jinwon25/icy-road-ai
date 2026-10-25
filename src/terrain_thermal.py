"""공개 DSM·태양 위치의 효과를 기상 이력과 분리해 비교한다."""
import numpy as np
import pandas as pd
from src.solar_terrain import solar_position
from src.thermal_extended import feature_table as thermal_features

SOLAR = ['solar_altitude_deg', 'solar_sine_positive']
TERRAIN = ['dsm_elevation_m', 'dsm_relative_500m', 'dsm_percentile_500m',
           'horizon_max_deg', 'sky_view_proxy', 'terrain_sun_visible', 'terrain_solar_proxy']


def solar_terrain_inputs(times, lat, lon, terrain):
    """16방위 지평선의 주기적 선형 보간. 도로 경사·포장·제설은 추정하지 않는다."""
    altitude, azimuth = solar_position(times, lat, lon)
    horizon = np.asarray([terrain[f'horizon_{i:02d}_deg'] for i in range(16)], float)
    if not np.isfinite(horizon).all():
        raise ValueError('Incomplete terrain horizon')
    directional = np.interp(azimuth, np.arange(17) * 22.5, np.r_[horizon, horizon[0]])
    positive = np.maximum(0., np.sin(np.deg2rad(altitude)))
    visible = ((altitude > directional) & (altitude > 0)).astype(float)
    result = pd.DataFrame({'solar_altitude_deg': altitude, 'solar_sine_positive': positive,
                           'terrain_sun_visible': visible, 'terrain_solar_proxy': positive * visible})
    for c in TERRAIN[:5]:
        result[c] = float(terrain[c])
    if not np.isfinite(result.to_numpy()).all():
        raise ValueError('Invalid terrain or solar input')
    return result


def feature_table(frame, kind):
    if kind not in ['thermal_solar', 'thermal_terrain', 'history_solar', 'history_terrain']:
        raise ValueError('Unknown terrain experiment')
    x = thermal_features(frame, 'thermal_history' if kind.startswith('history_') else 'thermal')
    columns = SOLAR + (TERRAIN if kind.endswith('_terrain') else [])
    return pd.concat([x, frame[columns].astype(float)], axis=1)
