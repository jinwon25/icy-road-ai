"""엄격한 과거 AWS 관측망의 거리 가중 통계. 도로 정답은 받지 않는다."""
import numpy as np
import pandas as pd

from src.weather_features import haversine_km

FIELDS = ('air_temp', 'humidity', 'wind_speed', 'rain_15m', 'dewpoint')
FORBIDDEN = {'ice', 'road_temp', 'state_raw', 'SFS', 'TR1',
             'air_temperature', 'relative_humidity'}


class WeatherNetwork:
    def __init__(self, observations, coordinates, neighbours=4, radius_km=50.,
                 max_age_minutes=15., distance_floor_km=1., power=2.):
        if FORBIDDEN & set(observations):
            raise ValueError('Road targets forbidden in weather network')
        if neighbours < 1 or min(radius_km, max_age_minutes, distance_floor_km, power) <= 0:
            raise ValueError('Positive network configuration required')
        self.settings = dict(neighbours=neighbours, radius_km=radius_km,
            max_age_minutes=max_age_minutes, distance_floor_km=distance_floor_km, power=power)
        self.coords = coordinates.copy()
        if not self.coords.index.is_unique or not np.isfinite(self.coords[['lat','lon']]).all().all():
            raise ValueError('Unique finite weather coordinates required')
        self.sources = {}
        for station, part in observations.groupby('station', sort=True):
            q = part.sort_values('source_time').reset_index(drop=True)
            if q.source_time.isna().any() or q.source_time.duplicated().any():
                raise ValueError('Unique finite source times required')
            if str(station) not in self.coords.index:
                raise ValueError('AWS coordinates missing')
            values = q[list(FIELDS)].to_numpy(float)
            if np.isinf(values).any():
                raise ValueError('Infinite weather observation')
            self.sources[str(station)] = (q.source_time.to_numpy(dtype='datetime64[ns]'), values)

    def build(self, times, lat, lon, current):
        times = pd.DatetimeIndex(times)
        if times.tz is not None or times.has_duplicates or times.hasnans:
            raise ValueError('Unique naive KST target times required')
        if not np.isfinite([lat,lon]).all() or not -90<=lat<=90 or not -180<=lon<=180:
            raise ValueError('Valid geographic coordinate required')
        if len(current) != len(times):
            raise ValueError('Current weather and target times must align')
        s = self.settings
        selected = sorted((haversine_km(lat,lon,r.lat,r.lon),station)
            for station,r in self.coords.iterrows() if station in self.sources)
        selected = [(d,k) for d,k in selected if d<=s['radius_km']][:s['neighbours']]
        n,k = len(times),len(selected)
        values = np.full((n,k,len(FIELDS)),np.nan)
        ages = np.full((n,k),np.nan)
        target = times.to_numpy(dtype='datetime64[ns]')
        for j,(distance,station) in enumerate(selected):
            clock,source = self.sources[station]
            if not len(clock):
                continue
            position = np.searchsorted(clock,target,side='left')-1
            safe = np.maximum(position,0)
            age = (target-clock[safe])/np.timedelta64(1,'m')
            valid = (position>=0)&(age>0)&(age<=s['max_age_minutes'])
            values[valid,j,:] = source[safe[valid]]
            ages[valid,j] = age[valid]
        distances = np.array([d for d,_ in selected],float)
        geometric_weights = 1/np.maximum(distances,s['distance_floor_km'])**s['power']
        x = pd.DataFrame(index=np.arange(n))
        for z,field in enumerate(FIELDS):
            a = values[:,:,z]; good = np.isfinite(a)
            w = good*geometric_weights[None,:]; total = w.sum(axis=1)
            normalized = np.divide(w,total[:,None],out=np.zeros_like(w),where=total[:,None]>0)
            mean = (np.nan_to_num(a,nan=0.)*normalized).sum(axis=1)
            mean[total==0] = np.nan
            var = (np.where(good,a-mean[:,None],0.)**2*normalized).sum(axis=1)
            var[total==0] = np.nan
            minimum = np.min(np.where(good,a,np.inf),axis=1,initial=np.inf)
            maximum = np.max(np.where(good,a,-np.inf),axis=1,initial=-np.inf)
            spread = np.full(n,np.nan); have = good.any(axis=1)
            spread[have] = maximum[have]-minimum[have]
            x['network_'+field+'_idw'] = mean
            x['network_'+field+'_sd'] = np.sqrt(var)
            x['network_'+field+'_range'] = spread
            x['network_'+field+'_contrast'] = mean-current['aws_'+field].to_numpy(float)
            x['network_'+field+'_count'] = good.sum(axis=1).astype(float)
            effective_distance = (normalized*distances[None,:]).sum(axis=1)
            effective_distance[total==0] = np.nan
            x['network_'+field+'_distance_km'] = effective_distance
            sum_square = (normalized**2).sum(axis=1)
            x['network_'+field+'_effective_n'] = np.divide(1.,sum_square,
                out=np.full(n,np.nan),where=sum_square>0)
        if np.isinf(x.to_numpy()).any():
            raise ValueError('Infinite network feature')
        mapping = dict(candidates=[dict(station=station,distance_km=d) for d,station in selected],
            max_observation_age_minutes=float(np.nanmax(ages)) if np.isfinite(ages).any() else None,
            observed_source_slots=int(np.isfinite(ages).sum()), strict_past=True)
        return x,mapping
