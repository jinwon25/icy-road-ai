"""보호 정답 없이 공공 AWS·ASOS에서 열·수분 입력을 만든다."""
import numpy as np
from src.segment_exposure import CachedWeatherPoints

ASOS_EXTRAS = ('ground_temp','cloud_tenths','solar_mj_m2','rain_mm','humidity')


def strictly_prior_values(times, source, columns):
    """merge_asof와 별개로 과거 60분 원천 행을 조회한다. 같은 시각은 제외한다."""
    ordered = source.sort_values('source_time')
    source_times = ordered.source_time.to_numpy(dtype='datetime64[ns]')
    if len(source_times) == 0 or np.any(source_times[1:] <= source_times[:-1]):
        raise ValueError('Nonempty, unique source timestamps required')
    target = times.to_numpy(dtype='datetime64[ns]')
    positions = np.searchsorted(source_times, target, side='left') - 1
    safe = positions.clip(min=0)
    age = (target-source_times[safe])/np.timedelta64(1,'m')
    valid = (positions>=0) & (age>0) & (age<=60)
    result = ordered[list(columns)].to_numpy(float)[safe].copy()
    result[~valid] = np.nan
    return result


class ThermalWeatherPoints(CachedWeatherPoints):
    def build(self, lat, lon):
        x, mapping = super().build(lat, lon)
        extra = strictly_prior_values(self.times, self.builder.asos[mapping['asos_station']], ASOS_EXTRAS)
        for i, column in enumerate(ASOS_EXTRAS):
            x['asos_'+column] = extra[:,i]
        x['air_min_3h'] = np.nan
        for station in x.aws_station.dropna().unique():
            selected = x.aws_station.eq(station).to_numpy()
            values = strictly_prior_values(self.times, self.builder.aws[station], ['air_min_3h'])[:,0]
            x.loc[selected,'air_min_3h'] = values[selected]
        x['air_dewpoint_gap'] = x.aws_air_temp-x.aws_dewpoint
        x['ground_air_gap'] = x.asos_ground_temp-x.aws_air_temp
        return x, mapping
