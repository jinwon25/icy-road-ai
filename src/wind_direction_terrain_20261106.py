"""제공 ASOS 16방위와 출처가 확인된 DSM의 지형 노출 대리변수."""
import numpy as np
import pandas as pd

CODES=[360,20,50,70,90,110,140,160,180,200,230,250,270,290,320,340]

def direction_features(raw_direction,speed):
    d=pd.Series(raw_direction).astype(float)
    v=pd.Series(speed,index=d.index).astype(float)
    angles=d.map({float(code):i*22.5 for i,code in enumerate(CODES)})
    good=angles.notna() & v.ge(.5)
    a=np.deg2rad(angles.where(good))
    out=pd.DataFrame(index=d.index)
    out['direction_sin']=np.sin(a);out['direction_cos']=np.cos(a)
    out['direction_u']=-v*np.sin(a);out['direction_v']=-v*np.cos(a)
    out['direction_calm']=(d.eq(0)|v.lt(.5)).astype(float).where(d.notna()&v.notna())
    out['direction_missing']=(~good & ~out.direction_calm.eq(1)).astype(float)
    return out,angles.where(good)

def terrain_features(station,angles,speed,terrain):
    t=terrain.reindex(pd.Series(station).astype(str)).reset_index(drop=True)
    x=pd.DataFrame(index=pd.Series(station).index)
    for c in ['dsm_elevation_m','dsm_relative_500m','dsm_percentile_500m','horizon_max_deg','sky_view_proxy']:
        x['terrain_'+c]=t[c].to_numpy(float)
    h=t[[f'horizon_{i:02d}_deg' for i in range(16)]].to_numpy(float)
    a=np.asarray(angles,float);known=np.isfinite(a);pos=np.where(known,a,0)/22.5
    lo=np.floor(pos).astype(int)%16;hi=(lo+1)%16;w=pos-np.floor(pos);row=np.arange(len(t))
    up=h[row,lo]*(1-w)+h[row,hi]*w
    down=h[row,(lo+8)%16]*(1-w)+h[row,(hi+8)%16]*w
    up[~known]=np.nan;down[~known]=np.nan
    x['terrain_upwind_horizon_deg']=up;x['terrain_downwind_horizon_deg']=down
    x['terrain_horizon_asymmetry_deg']=up-down
    x['terrain_wind_shelter_interaction']=np.asarray(speed)*np.sin(np.deg2rad(up))
    return x