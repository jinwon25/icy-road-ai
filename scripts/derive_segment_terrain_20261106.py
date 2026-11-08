"""검증된 공개 GLO-30 DSM으로 500m 중점의 지형 차폐 맥락을 계산한다. 위험 가중치 없음."""
from pathlib import Path
from datetime import datetime,timezone
import json,sys,time
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.solar_terrain import CopernicusSampler,solar_position
from src.data_source import sha256_file as sha
from scripts.seal_protected_weather_20261106 import W,write

def solar_context(times,lat,lon,horizon):
    altitude,azimuth=solar_position(times,lat,lon)
    index=azimuth/22.5;lower=np.floor(index).astype(int)%16;fraction=index%1
    obstruction=horizon[lower]*(1-fraction)+horizon[(lower+1)%16]*fraction
    day=altitude>0;known=np.isfinite(obstruction)
    visible=day&known&(altitude>obstruction)
    geometric=np.maximum(0,np.sin(np.deg2rad(altitude)))
    # 구름·대기·반사·구조물 상세가 없는 직달 일사 기하 지표. W/m²나 실제 일조시간이 아니다.
    return dict(planned_slots=len(times),daylight_slots=int(day.sum()),horizon_known_daylight_slots=int((known&day).sum()),
        potentially_obstructed_daylight_slots=int((day&known&~visible).sum()),
        potential_shade_daylight_fraction=float((day&known&~visible).sum()/(day&known).sum()) if (day&known).any() else None,
        geometric_direct_horizontal_loss_fraction=float(1-geometric[visible].sum()/geometric[day].sum()) if known[day].all() else None)

def main():
    O=W/'terrain_context';O.mkdir()
    source=ROOT/'outputs/private/releases/20261007/outputs/private/external/copernicus_dem'
    manifest=json.loads((source/'manifest.json').read_text('utf8'))
    for entry in manifest['entries']:assert sha(source/entry['file'])==entry['sha256']
    assert sha(source/'eula_F.pdf')==manifest['license_sha256']
    points_path=W/'icy_road_model/results/weather/weather_segments_500m.csv'
    points=pd.read_csv(points_path,dtype={'seg_id':str},float_precision='round_trip').drop_duplicates('seg_id')
    assert len(points)==843
    write(O/'plan.json',dict(created_utc=datetime.now(timezone.utc).isoformat(),source='Copernicus GLO-30 Public DSM, 2021 AWS release',
        samples='same 843 segment midpoints as weather output',units='EGM2008 metres for surface elevation',
        horizon='16 bearings every 22.5 degrees, 60-m steps through 3 km, positive maximum elevation angle',
        sky_view='mean cosine squared of 16 horizon angles; isotropic geometric proxy',
        time_resolution='10-minute KST, all 120 days per winter',solar='NOAA fractional-year approximation without atmospheric refraction',
        sensitivity='recompute horizon with first 1km versus 3km rays; not a probabilistic uncertainty interval',
        primary_inspection_criteria_changed=False,models_changed=False,weather_or_road_targets_read=False,
        limitations=['DSM includes canopy and structures; road deck elevation and road gradient are not established',
            'Clouds, detailed tunnels and barriers, shadows inside the 30m pixel and local surface validation are absent',
            'Potential direct-beam obstruction is not measured sunshine, radiative flux, or causal freezing effect',
            'Static DSM acquisition vintage predates the winters and may predate road works'],
        source_manifest_sha256=sha(source/'manifest.json'),points_sha256=sha(points_path),
        code_signatures={p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),ROOT/'src/solar_terrain.py']}))
    sampler=CopernicusSampler(sorted(source.glob('*.tif')));rows=[];seasonal=[];started=time.perf_counter()
    for i,p in enumerate(points.itertuples(),1):
        terrain=sampler.features(p.point_lon,p.point_lat)
        horizon=np.array([terrain[f'horizon_{k:02d}_deg'] for k in range(16)])
        # 1km 지평선은 동일 원 격자에서 별도로 계산하며 3km 결과를 변형해 만들지 않는다.
        bearings=np.arange(0.,360.,22.5);distances=np.arange(60.,1001.,60.)
        b,d=np.meshgrid(bearings,distances,indexing='ij')
        xx,yy,_=sampler.geod.fwd(np.full(b.size,p.point_lon),np.full(b.size,p.point_lat),b.ravel(),d.ravel())
        heights=sampler.sample(xx,yy).reshape(b.shape)
        from src.solar_terrain import horizon_angles
        short=horizon_angles(terrain['dsm_elevation_m'],heights,distances)
        assert (horizon+1e-10>=short).all()
        row=dict(seg_id=p.seg_id,point_lat=p.point_lat,point_lon=p.point_lon,**terrain)
        row['horizon_1km_max_deg']=float(short.max());row['sky_view_1km_proxy']=float(np.mean(np.cos(np.deg2rad(short))**2))
        rows.append(row)
        for year in [2024,2025]:
            times=pd.date_range(f'{year}-11-01',f'{year+1}-03-01',freq='10min',inclusive='left')
            full=solar_context(times,p.point_lat,p.point_lon,horizon);near=solar_context(times,p.point_lat,p.point_lon,short)
            seasonal.append(dict(seg_id=p.seg_id,winter=year,**full,
                potential_shade_daylight_fraction_1km=near['potential_shade_daylight_fraction'],
                geometric_direct_horizontal_loss_fraction_1km=near['geometric_direct_horizontal_loss_fraction']))
        if i%200==0:print('TERRAIN',i,'/843',round(time.perf_counter()-started,1),'seconds',flush=True)
    terrain=pd.DataFrame(rows);season=pd.DataFrame(seasonal)
    terrain.to_csv(O/'segment_terrain.csv',index=False,encoding='utf-8-sig')
    season.to_csv(O/'segment_solar_context.csv',index=False,encoding='utf-8-sig')
    assert len(terrain)==843 and len(season)==1686 and terrain.dsm_valid_fraction_500m.eq(1).all()
    assert season.horizon_known_daylight_slots.eq(season.daylight_slots).all()
    assert season.potential_shade_daylight_fraction.ge(season.potential_shade_daylight_fraction_1km-1e-12).all()
    assert season.geometric_direct_horizontal_loss_fraction.ge(season.geometric_direct_horizontal_loss_fraction_1km-1e-12).all()
    summary=dict(status='geometric_terrain_context_computed',segments=len(terrain),season_rows=len(season),
        source_notice=manifest['derived_notice'],liability_notice=manifest['liability_notice'],
        elevation_range_m=[float(terrain.dsm_elevation_m.min()),float(terrain.dsm_elevation_m.max())],
        sky_view_range=[float(terrain.sky_view_proxy.min()),float(terrain.sky_view_proxy.max())],
        potential_shade_fraction_range=[float(season.potential_shade_daylight_fraction.min()),float(season.potential_shade_daylight_fraction.max())],
        geometric_direct_horizontal_loss_range=[float(season.geometric_direct_horizontal_loss_fraction.min()),float(season.geometric_direct_horizontal_loss_fraction.max())],
        full_coverage=True,models_changed=False,inspection_weights_changed=False,seconds=time.perf_counter()-started,
        files={p.name:sha(p) for p in O.iterdir() if p.is_file()})
    write(O/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
