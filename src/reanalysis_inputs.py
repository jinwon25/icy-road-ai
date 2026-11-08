"""공식 단위와 시간 격자를 검사하는 사후 ERA5-Land 입력. 도로 정답을 사용하지 않는다."""
import numpy as np
import pandas as pd
from src.weather_features import haversine_km

FIELDS={
    'temperature_2m':('°C',-80,65),
    'relative_humidity_2m':('%',0,100),
    'dew_point_2m':('°C',-100,65),
    'soil_temperature_0_to_7cm':('°C',-80,80),
    'soil_temperature_7_to_28cm':('°C',-80,80),
    'soil_moisture_0_to_7cm':('m³/m³',0,1),
    'soil_moisture_7_to_28cm':('m³/m³',0,1),
    'snow_depth':('m',0,20),
}


def parse_response(payload,station,lat,lon,start,end,max_distance=20):
    if payload.get('error') or payload['timezone']!='Asia/Seoul' or payload['utc_offset_seconds']!=32400:
        raise ValueError('Successful response with fixed KST timezone required')
    distance=haversine_km(lat,lon,payload['latitude'],payload['longitude'])
    if not np.isfinite(distance) or distance>max_distance:
        raise ValueError('Returned grid is outside declared distance limit')
    hourly=payload['hourly'];units=payload['hourly_units']
    if set(hourly)!={'time',*FIELDS} or any(units.get(k)!=v[0] for k,v in FIELDS.items()):
        raise ValueError('Unexpected fields or units; do not infer conversion')
    expected=pd.date_range(start,pd.Timestamp(end)+pd.Timedelta(days=1),freq='h',inclusive='left')
    moments=pd.DatetimeIndex(pd.to_datetime(hourly['time'],errors='raise'))
    if not moments.equals(expected):raise ValueError('Incomplete, duplicated or misaligned hourly time grid')
    result=pd.DataFrame({'station':str(station),'source_time':moments})
    invalid={}
    for name,(_,low,high) in FIELDS.items():
        a=pd.to_numeric(pd.Series(hourly[name]),errors='raise')
        if len(a)!=len(moments):raise ValueError('Misaligned variable length')
        valid=np.isfinite(a)&a.between(low,high)
        invalid[name]=int((a.notna()&~valid).sum())
        result[name]=a.where(valid).to_numpy(float)
    report=dict(station=str(station),requested_lat=lat,requested_lon=lon,
        grid_lat=float(payload['latitude']),grid_lon=float(payload['longitude']),grid_distance_km=distance,
        grid_elevation_m=payload.get('elevation'),hours=len(result),invalid_values=invalid,
        valid_fractions={k:float(result[k].notna().mean()) for k in FIELDS})
    return result,report


def histories(frame):
    """시각 공백·겨울 경계를 넘지 않고 각 시점까지의 6·24·72시간 정보만 만든다."""
    if set(frame)!={'station','source_time',*FIELDS} or frame.duplicated(['station','source_time']).any():
        raise ValueError('Unique declared meteorological inputs only')
    f=frame.sort_values(['station','source_time']).reset_index(drop=True).copy()
    reset=f.station.ne(f.station.shift())|f.source_time.diff().ne(pd.Timedelta(hours=1))
    groups=reset.cumsum()
    for column in ['temperature_2m','soil_temperature_0_to_7cm','soil_moisture_0_to_7cm','snow_depth']:
        for hours in [6,24,72]:
            f[column+'_mean'+str(hours)+'h']=f[column].groupby(groups).transform(lambda s:s.rolling(hours,min_periods=hours).mean())
    return f
