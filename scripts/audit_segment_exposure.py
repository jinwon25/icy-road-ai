"""경계 교차·시설 코드 길이·전체 노출 분모·1km 집계와 대표 예측을 독립 감사한다."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,sys
import geopandas as gpd,joblib,numpy as np,pandas as pd,pyogrio
from shapely.geometry import shape
from shapely.ops import substring
from shapely import get_parts
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.audit_joint_surface import read,sha,close
from scripts.fresh_station_validation import SOURCE,PRIVATE,DEFAULT_OUT,old_freezes
from src.point_inputs import PointInputBuilder
from src.weather_features import haversine_km
from scripts.baseline_ice_logistic import FEATURES,add_time_features


def independent_exposure(q,column):
    t=q[column].to_numpy();water=q[['aws_dewpoint','rain15_max_3h','asos_snow_cm']].to_numpy();valid=np.isfinite(t)&~np.isnan(water).all(axis=1)
    dew=water[:,0]>=t;rain=water[:,1]>0;snow=water[:,2]>0;cold=t<=0;alarm=valid&cold&(dew|rain|snow)
    r=dict(planned_slots=len(q),valid_slots=int(valid.sum()),valid_fraction=float(valid.mean()),cold_hours=int((valid&cold).sum())/6,cold_moist_hours=int(alarm.sum())/6,cold_moist_fraction=int(alarm.sum())/int(valid.sum()),dew_cold_hours=int((valid&cold&dew).sum())/6,rain_cold_hours=int((valid&cold&rain).sum())/6,snow_cold_hours=int((valid&cold&snow).sum())/6,temp_p05=float(np.quantile(t[np.isfinite(t)],.05)),temp_mean=float(np.nanmean(t)))
    return r,alarm,valid


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--experiment',type=Path,default=PRIVATE/'segment_exposure_20261009_v1');args=parser.parse_args();out=args.experiment.resolve()
    if not out.is_relative_to(PRIVATE.resolve()):parser.error('Private experiment required')
    target=out/'independent_verification.json'
    if target.exists():raise FileExistsError('Preserve existing audit')
    summary=read(out/'summary.json');assert not summary['official_chainage_verified'] and not summary['source_gaps_filled']
    for name,value in summary['signatures'].items():assert sha(out/name)==value
    for r in read(out/'input_signature.json').values():assert sha(r['path'])==r['sha256']
    boundary=shape(read(PRIVATE/'sgis_boundary_2024_v1/response.geojson')['features'][0]['geometry']);assert boundary.is_valid
    source=SOURCE/'spatial/official_directed_environment_review_v1';archive=SOURCE/'external/official_nodelink_20240325/NODELINKDATA.zip'
    links=pyogrio.read_dataframe('/vsizip/'+archive.resolve().as_posix()+'/MOCT_LINK.shp',where="ROAD_RANK='101' AND ROAD_NO IN ('15','25','35')",encoding='CP949').to_crs(5179).set_index('LINK_ID')
    pieces=pd.read_csv(source/'segment_piece_environment.csv',dtype={'LINK_ID':str,'ROAD_TYPE':str,'seg_id':str});saved=pd.read_csv(out/'clipped_piece_environment.csv',dtype={'LINK_ID':str,'ROAD_TYPE':str,'seg_id':str,'UPDATEDATE':str});frames={};geometry_count=0
    for size in [500,1000]:
        g=gpd.read_file(out/f'segments_{size}m.gpkg');original=gpd.read_file(source/f'candidate_environment_{size}m.gpkg').set_index('seg_id');frames[size]=g
        assert g.crs.to_epsg()==5179 and g.seg_id.is_unique and g.official_chainage_verified.eq(False).all()
        assert g.official_km_start.isna().all() and g.official_km_end.isna().all() and g.risk_grade.isna().all() and g.verified_ice_probability.eq(False).all()
        expected={s for s,geom in original.geometry.items() if geom.intersection(boundary).length>1e-6};assert set(g.seg_id)==expected
        for row in g.itertuples(index=False):
            origin=original.loc[row.seg_id];expected_geometry=origin.geometry.intersection(boundary)
            # GPKG는 단일 선을 단일 조각의 MultiLineString으로 승격한다. 조각 좌표·순서는 그대로 대조한다.
            actual_parts=list(get_parts(row.geometry));expected_parts=list(get_parts(expected_geometry));assert len(actual_parts)==len(expected_parts)
            assert all(a.equals_exact(b,1e-8) for a,b in zip(actual_parts,expected_parts))
            assert row.geometry.difference(boundary).length<1e-6 and row.len_m<=size+1e-5
            close(row.len_m,row.geometry.length);assert row.chain_id==origin.chain_id and row.flow_lbl==origin.flow_lbl
            total=0;classes={'003':0.,'004':0.};found=[]
            for p in pieces[pieces.size_m.eq(size)&pieces.seg_id.eq(row.seg_id)].itertuples(index=False):
                link=links.loc[p.LINK_ID];geom=substring(link.geometry,p.link_m0,p.link_m1).intersection(boundary)
                if geom.length<=1e-6:continue
                state=str(link.ROAD_TYPE).zfill(3);assert str(p.ROAD_TYPE).zfill(3)==state;total+=geom.length
                if state in classes:classes[state]+=geom.length
                found.append(dict(LINK_ID=p.LINK_ID,length_m=float(geom.length),ROAD_TYPE=state,LANES=int(link.LANES),MAX_SPD=int(link.MAX_SPD),UPDATEDATE=str(link.UPDATEDATE)))
            recorded=saved[saved.size_m.eq(size)&saved.seg_id.eq(row.seg_id)].drop(columns=['seg_id','size_m']).reset_index(drop=True)
            pd.testing.assert_frame_equal(recorded,pd.DataFrame(found)[recorded.columns],check_dtype=False,rtol=0,atol=1e-6)
            assert abs(total-row.len_m)<1e-5
            assert abs(row.bridge_code_fraction-classes['003']/total)<1e-12 and abs(row.tunnel_code_fraction-classes['004']/total)<1e-12;geometry_count+=1
        shp=gpd.read_file(out/f'segments_{size}m.shp');assert list(shp.seg_id)==list(g.seg_id)
        np.testing.assert_allclose(shp.geometry.length,g.len_m,atol=1e-6,rtol=0);np.testing.assert_allclose(shp.cm_frac,g.cold_moist_fraction,atol=1e-12,rtol=0)
    temperature_models=[joblib.load(DEFAULT_OUT/'weather_hgb23.joblib')]
    for group in ['honam_baekyang','seohaean_seocheon','tongyeong_geumsan','tongyeong_seosang']:temperature_models.append(joblib.load(PRIVATE/'weather_fallback_20261009_v1'/group/'outer_models/augmented_hgb/model.joblib'))
    plan=read(out/'analysis_plan.json');start,end=plan['period_kst'];cutoff=pd.Timestamp(end)+pd.Timedelta(days=1)
    assert plan.get('model_training_period_kst',['2024-11-01','2025-02-28'])==['2024-11-01','2025-02-28']
    source_points=SOURCE/'point_sources';aws=pd.read_parquet(source_points/'aws.parquet');asos=pd.read_parquet(source_points/'asos.parquet')
    assert not {'ice','state_raw','road_temp','SFS','TR1'}&(set(aws)|set(asos))
    coordinates=pd.read_csv(source_points/'weather_coordinates.csv',dtype={'station_id':str})
    builder=None
    if start=='2024-11-01':
        rwis=pd.read_parquet(source_points/'rwis.parquet',filters=[('time','<',pd.Timestamp('2025-03-01'))])
        meta=pd.read_csv(SOURCE/'sensor_availability/metadata.csv',dtype={'station':str});meta=meta.loc[meta.kind.eq('RWIS'),['station','route','lat','lon']]
        builder=PointInputBuilder(aws.loc[aws.source_time.lt(cutoff)],asos.loc[asos.source_time.lt(cutoff)],rwis,coordinates,meta)
    # 두 번째 겨울은 AWS·ASOS 직접 as-of 결합으로 재계산하며 RWIS를 읽지 않는다.
    def weather_matrix(lat,lon,grid):
        x=add_time_features(pd.DataFrame({'time':grid}));available=set(aws.loc[aws.source_time.lt('2025-03-01')&aws.air_temp.notna(),'station'])
        nearest=sorted((haversine_km(lat,lon,float(r.latitudes),float(r.longitudes)),r.station_id) for r in coordinates[coordinates.kind.eq('AWS')].itertuples(index=False) if r.station_id in available)[:3]
        for name in ['air_temp','humidity','wind_speed','rain_15m','dewpoint','age_minutes','distance_km']:x['aws_'+name]=np.nan
        x['rain15_max_3h']=np.nan
        for distance,station in nearest:
            source=aws.loc[aws.station.eq(station)&aws.air_temp.notna()&aws.source_time.lt(cutoff),['source_time','air_temp','humidity','wind_speed','rain_15m','dewpoint','rain15_max_3h']].sort_values('source_time')
            j=pd.merge_asof(x[['time']],source,left_on='time',right_on='source_time',direction='backward',allow_exact_matches=False,tolerance=pd.Timedelta(minutes=60))
            pick=x.aws_air_temp.isna()&j.air_temp.notna()
            for name in ['air_temp','humidity','wind_speed','rain_15m','dewpoint']:x.loc[pick,'aws_'+name]=j.loc[pick,name].to_numpy()
            x.loc[pick,'rain15_max_3h']=j.loc[pick,'rain15_max_3h'].to_numpy();x.loc[pick,'aws_distance_km']=distance
            x.loc[pick,'aws_age_minutes']=(j.loc[pick,'time']-j.loc[pick,'source_time']).dt.total_seconds().to_numpy()/60
        available=set(asos.loc[asos.source_time.lt('2025-03-01'),'station']);distance,station=min((haversine_km(lat,lon,float(r.latitudes),float(r.longitudes)),r.station_id) for r in coordinates[coordinates.kind.eq('ASOS')].itertuples(index=False) if r.station_id in available)
        source=asos.loc[asos.station.eq(station)&asos.source_time.lt(cutoff),['source_time','air_temp','snow_cm']].sort_values('source_time')
        j=pd.merge_asof(x[['time']],source,left_on='time',right_on='source_time',direction='backward',allow_exact_matches=False,tolerance=pd.Timedelta(minutes=60))
        x['asos_air_temp']=j.air_temp;x['asos_age_minutes']=(j.time-j.source_time).dt.total_seconds()/60;x['asos_distance_km']=distance;x['asos_snow_cm']=j.snow_cm
        return x
    replays=set(frames[500].iloc[np.linspace(0,len(frames[500])-1,21,dtype=int)].seg_id);query_rows=0;full_replay_rows=0
    grid=pd.date_range(start,cutoff,freq='10min',inclusive='left');stat_cols=None
    for row in frames[500].itertuples(index=False):
        q=pd.read_parquet(out/'point_predictions'/(row.seg_id+'.parquet'));assert pd.DatetimeIndex(q.time).equals(grid)
        r,alarm,valid=independent_exposure(q,'estimated_temperature');np.testing.assert_array_equal(q.valid,valid);np.testing.assert_array_equal(q.cold_moist,alarm)
        for k,v in r.items():close(getattr(row,k),v)
        fractions=[];diff=np.zeros(len(q),dtype=bool)
        for i in range(4):
            a,p,v=independent_exposure(q,f'sensitivity_temperature_{i}');np.testing.assert_array_equal(valid,v);fractions.append(a['cold_moist_fraction']);diff|=alarm!=p
        close(row.sensitivity_fraction_min,min(fractions));close(row.sensitivity_fraction_max,max(fractions));close(row.model_disagreement_fraction,float(diff[valid].mean()));query_rows+=len(q)
        stat_cols=list(r)+['sensitivity_fraction_min','sensitivity_fraction_max','model_disagreement_fraction','aws_distance_km_max','asos_distance_km']
        if row.seg_id in replays:
            if builder is not None:x,_=builder.build(dict(station='99999',lat=row.point_lat,lon=row.point_lon,route=row.route_nm),grid)
            else:x=weather_matrix(row.point_lat,row.point_lon,grid)
            pd.testing.assert_frame_equal(q[['aws_dewpoint','rain15_max_3h','asos_snow_cm']],x[['aws_dewpoint','rain15_max_3h','asos_snow_cm']],rtol=0,atol=0)
            for i,model in enumerate(temperature_models):
                with threadpool_limits(limits=2):t=np.where(x.asos_air_temp.notna(),model.predict(x[FEATURES]),np.nan)
                col='estimated_temperature' if i==0 else f'sensitivity_temperature_{i-1}';np.testing.assert_allclose(q[col],t,rtol=0,atol=0,equal_nan=True);full_replay_rows+=len(q)
    for row in frames[1000].itertuples(index=False):
        part=frames[500][frames[500].chain_id.eq(row.chain_id)&frames[500].m0.ge(row.m0)&frames[500].m0.lt(row.m1)]
        assert abs(part.len_m.sum()-row.len_m)<1e-5
        for col in stat_cols:close(getattr(row,col),float(np.sum(part[col]*part.len_m)/part.len_m.sum()))
    original,reserved=old_freezes();result=dict(status='passed',checked_at_utc=datetime.now(timezone.utc).isoformat(),geometry_and_environment_segments=geometry_count,temperature_exposure_rows=query_rows,representative_replay_segments=len(replays),representative_temperature_predictions=full_replay_rows,weighted_1km_segments=len(frames[1000]),original_frozen_files=original,reserved_frozen_files=reserved,summary_sha256=sha(out/'summary.json'),source_sha256=sha(__file__))
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8');print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
