"""기상 단독 구간 입력 캐시와 분모가 명확한 저온·수분 노출 집계."""
import numpy as np
import pandas as pd
from src.weather_features import prior_join,haversine_km
from scripts.baseline_ice_logistic import add_time_features,FEATURES


class WeatherOnlySources:
    """AWS·ASOS와 그 좌표만 받는다. RWIS 정답·참조자료는 입력으로 받지 않는다."""
    def __init__(self,aws,asos,coordinates):
        forbidden={'ice','state_raw','road_temp','SFS','TR1','neighbor_road_temp','near_road_temp'}
        if forbidden & (set(aws)|set(asos)):
            raise ValueError('Road outcomes are forbidden in weather-only inference')
        self.aws={str(s):p.loc[p.air_temp.notna()].drop(columns=['station','lat','lon'],errors='ignore').sort_values('source_time') for s,p in aws.groupby('station')}
        self.asos={str(s):p.drop(columns='station').sort_values('source_time') for s,p in asos.groupby('station')}
        coords=coordinates.copy();coords['lat']=pd.to_numeric(coords.latitudes,errors='raise');coords['lon']=pd.to_numeric(coords.longitudes,errors='raise')
        if set(coords.kind)-{'AWS','ASOS'}:raise ValueError('Only AWS/ASOS coordinate types allowed')
        self.coords={kind:p.set_index('station_id')[['lat','lon']] for kind,p in coords.groupby('kind')}
        if set(self.aws)-set(self.coords['AWS'].index) or set(self.asos)-set(self.coords['ASOS'].index):raise ValueError('Unverified weather station coordinates')


class CachedWeatherPoints:
    """같은 원천·과거 60분·가까운 AWS 3개 규칙을 위치별로 반복한다."""
    def __init__(self,builder,times):
        self.builder=builder;self.times=pd.DatetimeIndex(times);self.cache={}
        if self.times.has_duplicates or self.times.tz is not None:
            raise ValueError('Unique naive KST times required')
        self.time_features=add_time_features(pd.DataFrame({'time':self.times}))

    def joined(self,kind,station):
        key=(kind,station)
        if key not in self.cache:
            source=(self.builder.aws if kind=='AWS' else self.builder.asos)[station]
            columns=['source_time','air_temp','humidity','wind_speed','rain_15m','dewpoint','rain15_max_3h'] if kind=='AWS' else ['source_time','air_temp','snow_cm']
            self.cache[key]=prior_join(pd.DataFrame({'time':self.times}),source[columns],'candidate',60)
        return self.cache[key]

    def build(self,lat,lon):
        b=self.builder;n=len(self.times);x=self.time_features.copy();chosen=np.zeros(n,dtype=bool)
        for name in ['air_temp','humidity','wind_speed','rain_15m','dewpoint','age_minutes','distance_km']:x['aws_'+name]=np.nan
        x['rain15_max_3h']=np.nan;x['aws_station']=pd.Series([None]*n,dtype=object)
        nearest=sorted((haversine_km(lat,lon,r.lat,r.lon),s) for s,r in b.coords['AWS'].iterrows() if s in b.aws and not b.aws[s].empty)[:3]
        for distance,station in nearest:
            j=self.joined('AWS',station);pick=~chosen&j.candidate_air_temp.notna().to_numpy();chosen|=pick
            for name in ['air_temp','humidity','wind_speed','rain_15m','dewpoint','age_minutes']:
                x.loc[pick,'aws_'+name]=j.loc[pick,'candidate_'+name].to_numpy()
            x.loc[pick,'rain15_max_3h']=j.loc[pick,'candidate_rain15_max_3h'].to_numpy()
            x.loc[pick,'aws_distance_km']=distance;x.loc[pick,'aws_station']=station
        distance,station=min((haversine_km(lat,lon,r.lat,r.lon),s) for s,r in b.coords['ASOS'].iterrows() if s in b.asos)
        j=self.joined('ASOS',station)
        x['asos_air_temp']=j.candidate_air_temp;x['asos_age_minutes']=j.candidate_age_minutes;x['asos_distance_km']=distance;x['asos_snow_cm']=j.candidate_snow_cm;x['asos_station']=station
        return x,dict(aws_candidates=[dict(station=s,distance_km=d) for d,s in nearest],asos_station=station,asos_distance_km=distance)


def exposure(temperature,frame):
    t=np.asarray(temperature,dtype=float)
    water=frame[['aws_dewpoint','rain15_max_3h','asos_snow_cm']].to_numpy(dtype=float)
    if t.shape!=(len(frame),) or np.isinf(t).any() or np.isinf(water).any():raise ValueError('Invalid exposure inputs')
    valid=np.isfinite(t)&~np.isnan(water).all(axis=1)
    if not valid.any():raise ValueError('No estimable exposure slots')
    dew=water[:,0]>=t;rain=water[:,1]>0;snow=water[:,2]>0;cold=t<=0;wet=dew|rain|snow;alarm=valid&cold&wet
    return dict(planned_slots=len(frame),valid_slots=int(valid.sum()),valid_fraction=float(valid.mean()),
                cold_hours=float((valid&cold).sum()/6),cold_moist_hours=float(alarm.sum()/6),
                cold_moist_fraction=float(alarm.sum()/valid.sum()),
                dew_cold_hours=float((valid&cold&dew).sum()/6),rain_cold_hours=float((valid&cold&rain).sum()/6),snow_cold_hours=float((valid&cold&snow).sum()/6),
                temp_p05=float(np.quantile(t[np.isfinite(t)],.05)),temp_mean=float(np.nanmean(t))),alarm,valid


def weighted_summary(parts,weights,columns):
    w=np.asarray(weights,dtype=float)
    if len(parts)!=len(w) or not np.isfinite(w).all() or (w<=0).any():raise ValueError('Positive geometry lengths required')
    return {c:float(np.average(parts[c].to_numpy(dtype=float),weights=w)) for c in columns}
