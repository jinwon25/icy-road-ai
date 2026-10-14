"""공공 기상 캐시만으로 보호3곳 및 전북 두 규모 구간의 두 겨울 후보 추정을 생성."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib
import json
import shutil
import sys
import joblib
import numpy as np
import pandas as pd
import geopandas as gpd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write,preservation
from src.data_source import sha256_file as sha
from src.segment_exposure import WeatherOnlySources,CachedWeatherPoints
from src.weather_features import haversine_km
from src.submission_runtime import FEATURES,WATER,infer
from src.offline_runtime import deny_network

PRIVATE=ROOT/'outputs/private';OUT=PRIVATE/'submission_candidate_20261013_v1'
CACHE=PRIVATE/'releases/20261007/outputs/private/point_sources'
SPATIAL=PRIVATE/'segment_exposure_20261009_v1'


def main():
    receipt=OUT/'spatial_receipt.json'
    if receipt.exists() or any((OUT/'data/weather_groups').glob('*.parquet')):raise FileExistsError('Preserve spatial candidate')
    frozen=preservation(); prep=read(OUT/'preparation_receipt.json'); assert prep['fits']==2
    for folder in ['data/weather_groups','data/prediction_groups']:(OUT/folder).mkdir(exist_ok=True)
    sources=WeatherOnlySources(pd.read_parquet(CACHE/'aws.parquet'),pd.read_parquet(CACHE/'asos.parquet'),
        pd.read_csv(CACHE/'weather_coordinates.csv',dtype={'station_id':str}))
    # 메타데이터의 정적 위치만 사용한다. 보호 정답·이전 평가 예측은 열지 않는다.
    meta=PRIVATE/'releases/20261007/outputs/private/frozen_assessment_v1/static_metadata.csv'
    protected=pd.read_csv(meta,usecols=['station','lat','lon'],dtype={'station':str})
    protected=protected.loc[protected.station.isin(['12410','33411','23402'])]
    assert protected.station.nunique()==len(protected)==3
    segments={n:pd.read_csv(SPATIAL/f'segment_exposure_{n}m.csv',dtype={'seg_id':str}) for n in [500,1000]}
    # 1km의 기존 통계는500m 길이 가중값이며 좌표가 없다. 이번 후보는 두 규모 모두 구간 중점 추정이다.
    geo1000=gpd.read_file(SPATIAL/'segments_1000m.gpkg')[['seg_id','geometry']]
    midpoints=geo1000.geometry.interpolate(.5,normalized=True).to_crs('EPSG:4326')
    geo1000['point_lat']=midpoints.y;geo1000['point_lon']=midpoints.x
    segments[1000]=segments[1000].merge(geo1000[['seg_id','point_lat','point_lon']],on='seg_id',validate='one_to_one')
    models=[joblib.load(OUT/'model'/(n+'.joblib')) for n in ['weather12_mse300','weather12_mae300']]
    mappings=[];groups={}; summaries=[];protected_parts=[];group_rows=0
    pinned=[Path(__file__),ROOT/'src/submission_runtime.py',ROOT/'src/segment_exposure.py',ROOT/'src/weather_features.py',meta,
        *[CACHE/n for n in ['aws.parquet','asos.parquet','weather_coordinates.csv']],
        *[SPATIAL/f'segment_exposure_{n}m.csv' for n in [500,1000]],SPATIAL/'segments_1000m.gpkg',
        *[OUT/'model'/(n+'.joblib') for n in ['weather12_mse300','weather12_mae300']]]
    with deny_network() as attempts:
        for winter,start,end in [('2024','2024-11-01','2025-03-01'),('2025','2025-11-01','2026-03-01')]:
            times=pd.date_range(start,pd.Timestamp(end)-pd.Timedelta(minutes=10),freq='10min');builder=CachedWeatherPoints(sources,times)
            points=[dict(kind='protected',scale=0,id=r.station,lat=r.lat,lon=r.lon,extra={}) for r in protected.itertuples()]
            for scale,table in segments.items():
                points.extend(dict(kind='segment',scale=scale,id=r.seg_id,lat=r.point_lat,lon=r.point_lon,extra=r._asdict()) for r in table.itertuples(index=False))
            for i,point in enumerate(points):
                lat,lon=point['lat'],point['lon']
                aws=sorted((haversine_km(lat,lon,r.lat,r.lon),s) for s,r in sources.coords['AWS'].iterrows() if s in sources.aws and not sources.aws[s].empty)[:3]
                asos=min((haversine_km(lat,lon,r.lat,r.lon),s) for s,r in sources.coords['ASOS'].iterrows() if s in sources.asos)
                key_data=dict(winter=winter,aws_candidates=[s for _,s in aws],asos_station=asos[1]);key=hashlib.sha256(json.dumps(key_data,sort_keys=True).encode()).hexdigest()[:20]
                if key not in groups:
                    weather,mapping=builder.build(lat,lon);weather['station']=key
                    w=weather[['station','time',*FEATURES,*[c for c in WATER if c not in FEATURES]]]
                    result=infer(w,models);result.to_parquet(OUT/'data/prediction_groups'/(key+'.parquet'),index=False,compression='zstd')
                    w.to_parquet(OUT/'data/weather_groups'/(key+'.parquet'),index=False,compression='zstd')
                    groups[key]=dict(**key_data,rows=len(result),weather_sha256=sha(OUT/'data/weather_groups'/(key+'.parquet')),
                        predictions_sha256=sha(OUT/'data/prediction_groups'/(key+'.parquet')))
                    group_rows+=len(result)
                else: result=pd.read_parquet(OUT/'data/prediction_groups'/(key+'.parquet'))
                mappings.append(dict(kind=point['kind'],scale_m=point['scale'],id=point['id'],winter=winter,prediction_group=key,
                    point_lat=lat,point_lon=lon,asos_distance_km=asos[0],nearest_aws_distance_km=aws[0][0],third_aws_distance_km=aws[-1][0]))
                if point['kind']=='protected':
                    p=result.copy();p.station=point['id'];p['winter']=winter;protected_parts.append(p)
                else:
                    valid=result.predicted_ice.notna();positive=result.predicted_ice.eq(1).fillna(False)
                    extra=point['extra'];allowed=['seg_id','route_nm','flow_lbl','len_m','bridge_code_fraction','tunnel_code_fraction','point_lat','point_lon']
                    summaries.append({k:extra[k] for k in allowed}|dict(scale_m=point['scale'],winter=winter,prediction_group=key,
                        planned_slots=len(result),temperature_valid_slots=int(result.estimated_road_temp_c.notna().sum()),ice_valid_slots=int(valid.sum()),
                        cold_wet_slots=int(positive.sum()),cold_wet_hours=float(positive.sum()/6),cold_wet_fraction=float(positive.sum()/valid.sum()) if valid.any() else None,
                        consensus_slots=int(result.condition_evidence.eq('cold_wet_consensus').sum()),
                        disagreement_slots=int(result.condition_evidence.eq('cold_wet_disagreement').sum()),
                        estimated_temp_mean_c=float(result.estimated_road_temp_c.mean()),
                        asos_distance_km=asos[0],aws_distance_km_max=aws[-1][0],official_chainage_verified=False,
                        sampling='clipped_arc_midpoint',verified_ice_probability=False,risk_grade=None))
                if (i+1)%200==0:print(winter,'위치',i+1,'그룹',len(groups),flush=True)
    assert attempts==[]
    mapping=pd.DataFrame(mappings);mapping.to_csv(OUT/'data/point_prediction_index.csv',index=False,encoding='utf-8-sig')
    p=pd.concat(protected_parts,ignore_index=True).sort_values(['station','time']);assert len(p)==103680
    assert not p.duplicated(['station','time']).any();p.to_csv(OUT/'data/protected_predictions_10min.csv.gz',index=False,encoding='utf-8-sig',compression='gzip')
    summary=pd.DataFrame(summaries);summary.to_csv(OUT/'data/segment_candidate_summary.csv',index=False,encoding='utf-8-sig')
    for scale in [500,1000]:
        geometries=gpd.read_file(SPATIAL/f'segments_{scale}m.gpkg')
        for winter in ['2024','2025']:
            table=summary.loc[summary.scale_m.eq(scale)&summary.winter.eq(winter)]
            geo=geometries[['seg_id','geometry']].merge(table,on='seg_id',validate='one_to_one')
            geo.to_file(OUT/'figures'/f'candidate_conditions_{scale}m_{winter}.gpkg',driver='GPKG')
    write(OUT/'data/prediction_group_manifest.json',groups)
    write(OUT/'spatial_input_signatures.json',{str(p.relative_to(ROOT)):sha(p) for p in pinned})
    assert preservation()==frozen
    write(receipt,dict(status='weather_only_candidate_spatial_complete',created_at_utc=datetime.now(timezone.utc).isoformat(),
        target_predictions=len(p),target_temperature_available=int(p.estimated_road_temp_c.notna().sum()),target_ice_available=int(p.predicted_ice.notna().sum()),
        segments_500m=len(segments[500]),segments_1000m=len(segments[1000]),winters=2,
        segment_slot_records_represented=len(summary)*17280,unique_weather_prediction_groups=len(groups),unique_prediction_rows=group_rows,
        prediction_index_rows=len(mapping),second_winter_weather_used=True,second_winter_training=False,
        protected_labels_or_previous_assessment_predictions_read=False,assessment_outcomes_used=False,
        network_attempts=0,official_submission_schema=False,model_promoted=False,submitted=False))
    print(read(receipt))


if __name__=='__main__':main()
