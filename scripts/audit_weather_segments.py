"""843구간 위치·출처·전량 집계와 고정 대표 구간의 세 모형 추론을 검산한다."""
from pathlib import Path
import math
import sys

import geopandas as gpd
import joblib
import numpy as np
import pandas as pd
from pyproj import Transformer
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.segment_exposure import WeatherOnlySources
from src.road_weather_points import RoadWeatherPoints
from src.road_weather_runtime import INPUT_COLUMNS,OUTPUT_COLUMNS
from src.road_weather_transfer import features,baselines,constrain
from src.offline_runtime import deny_network
from scripts.evaluate_objective_icing import read,write,verify_preserved


def distance(lat,lon,other_lat,other_lon):
    a,b,c,d=map(math.radians,[lat,lon,other_lat,other_lon])
    h=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 6371.0088*2*math.asin(math.sqrt(h))


def main():
    out=ROOT/'outputs/private/weather_segment_projection_20261031_v1';destination=out/'independent_verification.json'
    if destination.exists():raise FileExistsError('Preserve weather segment audit')
    plan=read(out/'plan.json');settings=plan['settings'];summary=read(out/'summary.json')
    for p,h in plan['signatures'].items():assert sha(ROOT/p)==h,p
    for p,h in summary['files'].items():assert sha(out/p)==h,p
    points=pd.read_csv(ROOT/settings['point_geometry'],dtype={'seg_id':str})
    geometry=gpd.read_file(ROOT/settings['geometry'],columns=['seg_id','geometry']).set_index('seg_id')
    transform=Transformer.from_crs(5179,4326,always_xy=True)
    source=ROOT/settings['weather_sources'];coords=pd.read_csv(source/'weather_coordinates.csv',dtype={'station_id':str})
    aws=pd.read_parquet(source/'aws.parquet');asos=pd.read_parquet(source/'asos.parquet')
    weather=WeatherOnlySources(aws,asos,coords)
    times=pd.DatetimeIndex(np.concatenate([pd.date_range(a,b,freq='10min',inclusive='left').values for a,b in settings['winters']]))
    builder=RoadWeatherPoints(weather,pd.read_parquet(ROOT/settings['input_preparation']/'asos_supplementary.parquet'),times)
    supplement=ROOT/settings['supplement'];metadata=read(supplement/'model/metadata.json')
    models={t:joblib.load(supplement/'model'/r['file']) for t,r in metadata['targets'].items()}
    training=pd.read_parquet(supplement/'data/training.parquet',columns=INPUT_COLUMNS)
    low=training.min();high=training.max()
    selected=set()
    for _,q in points.groupby(['route_nm','flow_lbl']):
        q=q.sort_values(['chain_id','m0','seg_id'])
        selected.update(q.iloc[[0,len(q)//2,len(q)-1]].seg_id)
    new_source=sorted(r['seg_id'] for r in summary['point_records'] if r['new_asos_source_domain'])
    if new_source:selected.add(new_source[0])
    records={r['seg_id']:r for r in summary['point_records']}
    table=pd.read_csv(out/'weather_segments_500m.csv',dtype={'seg_id':str,'asos_station':str}).set_index(['seg_id','winter'])
    daily=pd.read_parquet(out/'weather_segment_daily.parquet');daily_parts={k:q for k,q in daily.groupby('seg_id',sort=False)}
    model_values=0;row_values=0;aggregate_checks=0;source_checks=0
    for i,point in enumerate(points.itertuples(),1):
        record=records[point.seg_id];path=out/'points'/(point.seg_id+'.parquet')
        assert sha(path)==record['prediction_sha256']
        middle=geometry.loc[point.seg_id,'geometry'].interpolate(.5,normalized=True)
        lon,lat=transform.transform(middle.x,middle.y)
        np.testing.assert_allclose([lat,lon],[point.point_lat,point.point_lon],atol=1e-10,rtol=0)
        for kind in ['ASOS','AWS']:
            ids=set(weather.asos if kind=='ASOS' else weather.aws)
            available=coords.loc[coords.kind.eq(kind)&coords.station_id.isin(ids)]
            nearest=sorted((distance(lat,lon,r.latitudes,r.longitudes),r.station_id) for r in available.itertuples())
            if kind=='ASOS':
                assert record['mapping']['asos_station']==nearest[0][1]
                np.testing.assert_allclose(record['mapping']['asos_distance_km'],nearest[0][0],atol=1e-9,rtol=0)
            else:
                assert [r['station'] for r in record['mapping']['aws_candidates']]==[s for _,s in nearest[:3]]
                np.testing.assert_allclose([r['distance_km'] for r in record['mapping']['aws_candidates']],
                    [d for d,_ in nearest[:3]],atol=1e-9,rtol=0)
            source_checks+=1
        f=pd.read_parquet(path);assert pd.DatetimeIndex(f.time).equals(times)
        assert len(f)==34560 and set(f)=={'time','outside_training_input_range',*OUTPUT_COLUMNS.values()}
        assert f.estimated_humidity_pct.dropna().between(0,100).all() and f.estimated_wind_speed_ms.dropna().ge(0).all()
        if point.seg_id in selected:
            with deny_network() as attempts,threadpool_limits(limits=2):
                frame,_=builder.build(point.point_lat,point.point_lon);x=features(frame)
                for t,m in models.items():
                    a,b=baselines(frame,t);valid=np.isfinite(a)&np.isfinite(b)
                    expected=np.full(len(f),np.nan);expected[valid]=constrain(m.predict(x.loc[valid])+b[valid],t)
                    np.testing.assert_allclose(expected,f[OUTPUT_COLUMNS[t]],rtol=0,atol=1e-10,equal_nan=True)
                    model_values+=len(f)
                outside=((frame[INPUT_COLUMNS]<low)|(frame[INPUT_COLUMNS]>high)).any(axis=1)
                np.testing.assert_array_equal(outside,f.outside_training_input_range)
            assert not attempts
        d=daily_parts[point.seg_id].sort_values('date').reset_index(drop=True)
        assert pd.DatetimeIndex(d.date).equals(times[::144])
        for t,c in OUTPUT_COLUMNS.items():
            values=f[c].to_numpy().reshape(240,144);valid=np.isfinite(values).sum(axis=1)
            mean=np.divide(np.nansum(values,axis=1),valid,out=np.full(240,np.nan),where=valid>0)
            np.testing.assert_allclose(mean,d[t+'_mean'],atol=1e-11,rtol=0,equal_nan=True)
            np.testing.assert_array_equal(valid,d[t+'_valid_slots']);aggregate_checks+=480
        np.testing.assert_array_equal(f.outside_training_input_range.to_numpy().reshape(240,144).sum(axis=1),d.outside_training_input_range_slots)
        aggregate_checks+=240
        for year in [2024,2025]:
            q=f.iloc[:17280] if year==2024 else f.iloc[17280:];r=table.loc[(point.seg_id,year)]
            assert r.planned_slots==17280 and str(r.asos_station)==record['mapping']['asos_station']
            assert bool(r.new_asos_source_domain)==record['new_asos_source_domain']
            np.testing.assert_allclose(q.outside_training_input_range.to_numpy().mean(),r.input_range_outside_fraction,atol=1e-12,rtol=0)
            for t,c in OUTPUT_COLUMNS.items():
                a=q[c].dropna().to_numpy();assert len(a)==r[t+'_valid_slots']
                expected=[a.sum()/len(a),*np.percentile(a,[10,50,90])] if len(a) else [np.nan]*4
                np.testing.assert_allclose(expected,[r[t+'_'+key] for key in ['mean','p10','p50','p90']],atol=1e-10,rtol=0,equal_nan=True)
                aggregate_checks+=5
            for a,b in [('air_temperature','relative_humidity'),('air_temperature','wind_speed'),('relative_humidity','wind_speed')]:
                x=q[[OUTPUT_COLUMNS[a],OUTPUT_COLUMNS[b]]].dropna().to_numpy();assert len(x)==r[a+'__'+b+'_paired_slots']
                centered=x-x.mean(axis=0);den=np.sqrt((centered**2).sum(axis=0).prod())
                value=np.dot(centered[:,0],centered[:,1])/den if den>0 else np.nan
                np.testing.assert_allclose(value,r[a+'__'+b+'_correlation'],atol=1e-10,rtol=0,equal_nan=True);aggregate_checks+=2
        row_values+=len(f)
        if i%100==0:print('SPATIAL AUDIT',i,'/843',flush=True)
    combined=pd.read_csv(out/'weather_and_preserved_road_estimates.csv',dtype={'seg_id':str},float_precision='round_trip')
    old=pd.read_csv(ROOT/settings['archived_segment_estimates'],dtype={'seg_id':str})
    old=old.loc[old.scale_m.eq(500)].set_index(['seg_id','winter'])
    for c in ['prediction_group','estimated_temp_mean_c','cold_wet_fraction']:
        a=combined.set_index(['seg_id','winter'])[c].sort_index();b=old[c].sort_index()
        pd.testing.assert_series_equal(a,b,check_exact=True)
    for year in [2024,2025]:
        layer=gpd.read_file(out/'weather_segments.gpkg',layer=f'winter_{year}').set_index('seg_id')
        assert len(layer)==843 and layer.crs.to_epsg()==5179
        for s in geometry.index:assert layer.loc[s,'geometry'].equals_exact(geometry.loc[s,'geometry'],tolerance=1e-8)
    assert verify_preserved()==plan['preservation']
    write(destination,dict(status='passed',summary_sha256=sha(out/'summary.json'),geometry_rows=843,
        source_selections=source_checks,ten_minute_rows_checked=row_values,aggregate_checks=aggregate_checks,
        model_replay_segments=sorted(selected),model_replay_values=model_values,unchanged_road_estimate_rows=len(combined),
        gis_layers=2,audit_source_sha256=sha(Path(__file__)),new_independent_assessment=False))
    print('WEATHER SPATIAL AUDIT PASSED',row_values,model_values,aggregate_checks,flush=True)


if __name__=='__main__':main()
