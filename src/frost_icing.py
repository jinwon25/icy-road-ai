"""결빙 정답 없이 고정하는 추정 서리 조건과 기온 기준선의 합집합."""
import numpy as np
from src.weather_thermodynamics import vapor_pressure,frost_point


def frost_policies(asos_air,nearest_air,nearest_rh,road_temperature,estimated_air,estimated_rh,wet,available):
    arrays=[np.asarray(v) for v in [asos_air,nearest_air,nearest_rh,road_temperature,estimated_air,estimated_rh,wet,available]]
    if any(v.ndim!=1 or v.shape!=arrays[0].shape for v in arrays):raise ValueError('Aligned vectors required')
    air,near_air,near_rh,road,estimate_air,estimate_rh,wet,available=arrays
    available=available.astype(bool)
    baseline=air<=0
    if not np.isfinite(air[available]).all():raise ValueError('Available baseline temperature required')
    values={};flags={}
    for name,t,rh in [('estimates',estimate_air,estimate_rh),('nearest',near_air,near_rh)]:
        point=frost_point(vapor_pressure(t,rh))
        good=np.isfinite(point)&np.isfinite(road)
        frost=(road<=0)&(road<=point)
        condition=np.where(good,frost,baseline)
        values['frost_'+name]=np.where(available,condition,np.nan)
        values['union_frost_'+name]=np.where(available,baseline|condition,np.nan)
        flags[name+'_frost_point_c']=point
        flags[name+'_physical_available']=good
        if name=='estimates':
            mixed=np.where(good,(road<=0)&(frost|np.asarray(wet,bool)),baseline)
            values['wet_or_frost']=np.where(available,mixed,np.nan)
    values['asos_zero']=np.where(available,baseline,np.nan)
    return values,flags
