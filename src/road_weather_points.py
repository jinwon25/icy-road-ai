"""도로 정답 없이 위치·시각에서 보완 기상 모형의 입력을 구성한다."""
import numpy as np

from src.thermal_weather_points import ThermalWeatherPoints,strictly_prior_values
from src.solar_terrain import solar_position
from src.road_weather_runtime import INPUT_COLUMNS


EXTRA_FIELDS=['wind_speed','dewpoint_obs','pressure','visibility','new_snow3h','soil5cm']


class RoadWeatherPoints(ThermalWeatherPoints):
    def __init__(self,weather,extra_asos,times):
        super().__init__(weather,times)
        if {'ice','road_temp','state_raw','SFS','TR1'}&set(extra_asos):raise ValueError('Road targets forbidden')
        self.extra={str(s):q.drop(columns='station').sort_values('source_time') for s,q in extra_asos.groupby('station')}
        self.joined_extra={}

    def build(self,lat,lon):
        if not np.isfinite([lat,lon]).all() or not -90<=lat<=90 or not -180<=lon<=180:
            raise ValueError('Valid geographic coordinate required')
        x,mapping=super().build(lat,lon);station=str(mapping['asos_station'])
        if station not in self.extra:raise ValueError('Selected ASOS lacks verified supplementary source')
        if station not in self.joined_extra:
            self.joined_extra[station]=strictly_prior_values(self.times,self.extra[station],EXTRA_FIELDS)
        for i,column in enumerate(EXTRA_FIELDS):x['asos_'+column]=self.joined_extra[station][:,i]
        altitude,_=solar_position(self.times,lat,lon)
        x['solar_altitude_deg']=altitude;x['solar_sine_positive']=np.maximum(0,np.sin(np.deg2rad(altitude)))
        return x[['time']+INPUT_COLUMNS].copy(),mapping
