"""임의 도로 위치에서 과거 기상·주변 도로 입력을 생성한다. 타깃 정답을 받지 않는다."""
import numpy as np
import pandas as pd
from src.weather_features import haversine_km,prior_join
from src.validation import assert_training_stations,PROTECTED_STATIONS
from src.physical_features import CONTEXT_FEATURES
from src.moisture_memory import MEMORY_FEATURES
from scripts.audit_ice_weather_history import HISTORY
from scripts.baseline_ice_logistic import add_time_features

AWS_VARIABLES=['air_temp','humidity','wind_speed','rain_15m','dewpoint']


def canonical_route(value):
    value=str(value).strip()
    return {'서해안고속국도':'서해안','호남고속국도':'호남선','통영-대전고속국도':'통영-대전중부선'}.get(value,value)


class PointInputBuilder:
    def __init__(self,aws,asos,rwis,weather_coordinates,rwis_metadata):
        assert_training_stations(rwis.station.unique())
        assert_training_stations(rwis_metadata.station.unique())
        if set(rwis.station)-set(rwis_metadata.station):raise ValueError('Missing RWIS metadata')
        self.aws={str(s):p.loc[p.air_temp.notna()].drop(columns=['station','lat','lon'],errors='ignore').sort_values('source_time') for s,p in aws.groupby('station')}
        self.asos={str(s):p.drop(columns='station').sort_values('source_time') for s,p in asos.groupby('station')}
        self.rwis={str(s):p.sort_values('time') for s,p in rwis.groupby('station')}
        coords=weather_coordinates.copy()
        coords['lat']=pd.to_numeric(coords.latitudes,errors='raise');coords['lon']=pd.to_numeric(coords.longitudes,errors='raise')
        self.coords={kind:p.set_index('station_id')[['lat','lon']] for kind,p in coords.groupby('kind')}
        self.meta=rwis_metadata.set_index('station').copy();self.meta['route']=self.meta.route.map(canonical_route)
        self.moisture=set(rwis.loc[rwis.humidity.notna(),'station'])

    @classmethod
    def from_root(cls,root):
        private=root/'outputs/private';p=private/'point_sources'
        meta=pd.read_csv(private/'sensor_availability/metadata.csv',dtype={'station':str})
        return cls(pd.read_parquet(p/'aws.parquet'),pd.read_parquet(p/'asos.parquet'),pd.read_parquet(p/'rwis.parquet'),
                   pd.read_csv(p/'weather_coordinates.csv',dtype={'station_id':str}),meta.loc[meta.kind.eq('RWIS'),['station','route','lat','lon']])

    def _reference(self,point,forbidden,moisture=False):
        pool=self.meta.loc[self.meta.route.eq(canonical_route(point['route'])) & ~self.meta.index.isin(forbidden|{point['station']}|PROTECTED_STATIONS)]
        if moisture:pool=pool.loc[pool.index.isin(self.moisture)]
        if pool.empty:return None,np.nan
        distance,sid=min((haversine_km(point['lat'],point['lon'],r.lat,r.lon),sid) for sid,r in pool.iterrows())
        return sid,distance

    def build(self,point,times,forbidden=()):
        assert_training_stations([point['station']])
        if set(point)&{'ice','state_raw','road_temp'}:raise ValueError('Target measurements are not inference metadata')
        if canonical_route(point['route']) not in set(self.meta.route):raise ValueError('Unknown target route; explicit source crosswalk required')
        forbidden=set(forbidden)
        time=pd.DatetimeIndex(times)
        if time.tz is not None:time=time.tz_convert('Asia/Seoul').tz_localize(None)
        time=time.astype('datetime64[ns]').sort_values()
        if time.has_duplicates:raise ValueError('Duplicate target time')
        if ((time.minute%10!=0)|(time.second!=0)).any():raise ValueError('Expected ten-minute target grid')
        target=pd.DataFrame({'time':time,'station':point['station'],'route':point['route'].strip()})
        selected={}
        nearest=sorted((haversine_km(point['lat'],point['lon'],r.lat,r.lon),sid) for sid,r in self.coords['AWS'].iterrows() if sid in self.aws and not self.aws[sid].empty)[:3]
        extra=[*HISTORY,*MEMORY_FEATURES]
        for c in AWS_VARIABLES:target['aws_'+c]=np.nan
        for c in extra:target[c]=np.nan
        for c in ['aws_age_minutes','aws_distance_km','aws_rank']:target[c]=np.nan
        target['aws_source_time']=pd.NaT;target['aws_station']=pd.Series([None]*len(target),dtype=object)
        for rank,(distance,sid) in enumerate(nearest,1):
            joined=prior_join(target[['time']],self.aws[sid][['source_time',*AWS_VARIABLES,*extra]],'candidate',60)
            pick=target.aws_rank.isna() & joined.candidate_air_temp.notna()
            for c in AWS_VARIABLES:target.loc[pick,'aws_'+c]=joined.loc[pick,'candidate_'+c].to_numpy()
            for c in extra:target.loc[pick,c]=joined.loc[pick,'candidate_'+c].to_numpy()
            target.loc[pick,'aws_source_time']=joined.loc[pick,'candidate_source_time'].to_numpy()
            target.loc[pick,'aws_age_minutes']=joined.loc[pick,'candidate_age_minutes'].to_numpy()
            target.loc[pick,'aws_distance_km']=distance;target.loc[pick,'aws_rank']=rank;target.loc[pick,'aws_station']=sid
        selected['aws_candidates']=[{'station':s,'distance_km':d} for d,s in nearest]
        distance,sid=min((haversine_km(point['lat'],point['lon'],r.lat,r.lon),sid) for sid,r in self.coords['ASOS'].iterrows() if sid in self.asos)
        target=prior_join(target,self.asos[sid],'asos',60)
        target['asos_station']=sid;target['asos_distance_km']=distance;selected['asos_station']=sid
        for moisture,prefix,mapping in [(False,'near',{'road_temp':'road_temp','temp_min60':'temp_min60','temp_trend60':'temp_trend60'}),(True,'moisture',{'humidity':'humidity','rain10':'rain10'})]:
            sid,distance=self._reference(point,forbidden,moisture);selected[prefix+'_source']=sid
            target[prefix+'_distance_km']=distance
            if sid is None:
                for c in mapping.values():target[prefix+'_'+c]=np.nan
                target[prefix+'_age_minutes']=np.nan
            else:
                src=self.rwis[sid][['time',*mapping]].rename(columns={'time':'source_time'})
                joined=prior_join(target[['time']],src,'candidate',30)
                for a,b in mapping.items():target[prefix+'_'+b]=joined['candidate_'+a].to_numpy()
                target[prefix+'_age_minutes']=joined.candidate_age_minutes.to_numpy()
        # 온도 기준 혼합은 이전 검증과 동일하게 유효한 과거 온도, 60분 허용을 쓴다.
        sid=selected['near_source']
        if sid is not None:
            src=self.rwis[sid][['time','road_temp']].dropna().rename(columns={'time':'source_time'})
            joined=prior_join(target[['time']],src,'blend',60)
            target['neighbor_road_temp']=joined.blend_road_temp.to_numpy()
            target['neighbor_age_minutes']=joined.blend_age_minutes.to_numpy()
        else:
            target['neighbor_road_temp']=np.nan;target['neighbor_age_minutes']=np.nan
        target['surface_dewpoint_gap']=target.near_road_temp-target.aws_dewpoint
        target['surface_air_gap']=target.near_road_temp-target.aws_air_temp
        target['air_dewpoint_gap']=target.aws_air_temp-target.aws_dewpoint
        target['air_asos_gap']=target.aws_air_temp-target.asos_air_temp
        target['ground_air_gap']=target.asos_ground_temp-target.aws_air_temp
        return add_time_features(target),selected
