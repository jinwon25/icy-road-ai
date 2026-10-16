"""정답 없이 과거 ASOS를 거리·관측 나이 조건으로 찾는다."""
import numpy as np
import pandas as pd
from src.weather_features import haversine_km

FORBIDDEN={'ice','road_temp','state','state_raw','target','label'}


class AsosGapFallback:
    def __init__(self,observations,coordinates,maximum_distance_km=50.,maximum_extra_distance_km=30.,maximum_age_minutes=60):
        if FORBIDDEN & (set(observations.columns)|set(coordinates.columns)):
            raise ValueError('Only ASOS weather and static coordinates are permitted')
        if not {'station','source_time','air_temp','snow_cm'}<=set(observations) or not {'station','lat','lon'}<=set(coordinates):
            raise ValueError('Declared ASOS weather and coordinates required')
        if not np.isfinite([maximum_distance_km,maximum_extra_distance_km,maximum_age_minutes]).all() or min(maximum_distance_km,maximum_age_minutes)<=0 or maximum_extra_distance_km<0:
            raise ValueError('Finite positive weather limits required')
        f=observations[['station','source_time','air_temp','snow_cm']].copy()
        f.station=f.station.astype(str);f.source_time=pd.to_datetime(f.source_time)
        if f.source_time.isna().any() or f.source_time.dt.tz is not None or f.duplicated(['station','source_time']).any():
            raise ValueError('Unique naive KST ASOS observations required')
        for column in ['air_temp','snow_cm']:
            f[column]=pd.to_numeric(f[column],errors='raise').replace([-999.,-99.9,-99.2,-99.7],np.nan)
            if np.isinf(f[column]).any():raise ValueError('Infinite ASOS weather')
        c=coordinates[['station','lat','lon']].copy();c.station=c.station.astype(str)
        if c.station.duplicated().any() or not set(f.station)<=set(c.station):raise ValueError('Unique ASOS station coordinates required')
        if not np.isfinite(c[['lat','lon']].to_numpy(float)).all() or not c.lat.between(-90,90).all() or not c.lon.between(-180,180).all():
            raise ValueError('Finite geographic coordinates required')
        self.coordinates=c.loc[c.station.isin(f.station)].set_index('station')
        self.observations={station:part.loc[part.air_temp.notna()].sort_values('source_time').reset_index(drop=True) for station,part in f.groupby('station')}
        self.maximum_distance=maximum_distance_km;self.maximum_extra=maximum_extra_distance_km;self.maximum_age=maximum_age_minutes

    def select(self,point,times,exclude=()):
        if FORBIDDEN & set(point):raise ValueError('Target outcomes cannot enter weather selection')
        t=pd.DatetimeIndex(times)
        if t.tz is not None or t.isna().any() or t.has_duplicates or ((t.minute%10!=0)|(t.second!=0)|(t.microsecond!=0)|(t.nanosecond!=0)).any():
            raise ValueError('Unique exact ten-minute naive KST targets required')
        if not np.isfinite([point['lat'],point['lon']]).all():raise ValueError('Finite target coordinates required')
        ranked=sorted((haversine_km(point['lat'],point['lon'],r.lat,r.lon),station) for station,r in self.coordinates.iterrows())
        if not ranked:raise ValueError('ASOS weather source inventory is empty')
        primary_distance,primary=ranked[0]
        output=pd.DataFrame({'station':str(point['station']),'time':t,'primary_asos_station':primary,
            'selected_asos_station':pd.Series([None]*len(t),dtype=object),'source_time':pd.NaT,
            'air_temp':np.nan,'snow_cm':np.nan,'age_minutes':np.nan,'distance_km':np.nan})
        for distance,station in ranked:
            if station in set(map(str,exclude)) or distance>self.maximum_distance or distance>primary_distance+self.maximum_extra:continue
            source=self.observations[station]
            if source.empty:continue
            positions=np.searchsorted(source.source_time.to_numpy(),t.to_numpy(),side='left')-1
            safe=np.maximum(positions,0);selected=source.iloc[safe].reset_index(drop=True)
            age=(t-selected.source_time).dt.total_seconds()/60
            use=(positions>=0)&age.gt(0)&age.le(self.maximum_age)&output.selected_asos_station.isna()
            if not use.any():continue
            for column in ['source_time','air_temp','snow_cm']:output.loc[use,column]=selected.loc[use,column].to_numpy()
            output.loc[use,'selected_asos_station']=station
            output.loc[use,'age_minutes']=age.loc[use].to_numpy();output.loc[use,'distance_km']=distance
        return output


def apply_weather_fallback(frame,selection):
    if not frame[['station','time']].reset_index(drop=True).equals(selection[['station','time']].reset_index(drop=True)):
        raise ValueError('ASOS weather selection must match input identities exactly')
    out=frame.copy()
    valid=out.asos_air_temp.notna()&out.asos_age_minutes.gt(0)&out.asos_age_minutes.le(60)
    replace=(~valid)&selection.selected_asos_station.notna().to_numpy()
    for target,source in [('asos_air_temp','air_temp'),('asos_snow_cm','snow_cm'),('asos_age_minutes','age_minutes')]:
        out.loc[replace,target]=selection.loc[replace,source].to_numpy()
    if 'asos_distance_km' in out:out.loc[replace,'asos_distance_km']=selection.loc[replace,'distance_km'].to_numpy()
    return out,replace.to_numpy()
