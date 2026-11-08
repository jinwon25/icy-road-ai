"""ASOS 과정 입력에 가까운 AWS 관측과 공개 DSM/태양 위치를 단계적으로 더한다."""
import numpy as np
import pandas as pd
from src.icing_precision_20261106 import features as asos_features
AWS=['aws_air_temp','aws_humidity','aws_wind_speed','aws_rain_15m','aws_dewpoint']
TERRAIN=['dsm_elevation_m','dsm_relative_500m','dsm_percentile_500m','horizon_max_deg',
         'sky_view_proxy','terrain_sun_visible','terrain_solar_proxy','solar_altitude_deg','solar_sine_positive']

def features(frame,kind):
    if kind not in ['process','local','terrain']:
        raise ValueError('Planned representation only')
    x=asos_features(frame,'process')
    if kind=='process':return x
    good=frame.aws_age_minutes.between(0,60,inclusive='right')
    for c in AWS:x[c]=frame[c].where(good).to_numpy(float)
    x['aws_age_minutes']=frame.aws_age_minutes.to_numpy(float)
    if kind=='terrain':
        for c in TERRAIN:x[c]=frame[c].to_numpy(float)
    if np.isinf(x.to_numpy(float)).any():raise ValueError('No infinite weather or terrain values')
    return x
