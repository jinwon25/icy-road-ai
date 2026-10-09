"""SGIS 경계로 자른 방향별 500m·1km 구간의 기상 노출과 환경 근거를 만든다."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,shutil,sys
import joblib,geopandas as gpd,numpy as np,pandas as pd,pyogrio
from shapely.geometry import shape
from shapely.ops import substring
from pyproj import Transformer
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.audit_joint_surface import sha,read
from scripts.fresh_station_validation import SOURCE,PRIVATE,DEFAULT_OUT,old_freezes,verify_seal
from src.point_inputs import PointInputBuilder
from src.segment_exposure import WeatherOnlySources,CachedWeatherPoints,exposure,weighted_summary
from scripts.baseline_ice_logistic import FEATURES

PLAN=dict(period_kst=['2024-11-01','2025-02-28'],boundary='SGIS public map: 2024 adm_cd35 low_search0; EPSG5179, API representation, not surveyed legal boundary.',
          sampling='One geometric arc midpoint per clipped500m candidate; 1km length-weighted aggregation of its500m children.',
          exposure='Predicted weather-only road temperature <=0 and dewpoint>=temperature or prior3h rain>0 or ASOS snow>0. Denominator requires finite temperature and any observed moisture evidence. No Ice probability, accident probability, new threshold search or road-risk grade.',
          sensitivity='Range of the four preexisting external-group-excluded temperature models; descriptive model sensitivity, not a confidence or prediction interval.',
          environment='Length of archived official link ROAD_TYPE003/004 and archived LANES/MAX_SPD after clipping. Physical facility extents and current speed limits unverified.',
          boundary_sensitivity='Analyst-chosen +/-100m polygon buffer; positional QA, not an uncertainty confidence bound.',
          official_chainage_verified=False,final_submission_approved=False,protected_or_opened_future_outcomes_used=False)


def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),'utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);parser.add_argument('--winter',choices=['first','second'],default='first');args=parser.parse_args()
    out=(args.output or PRIVATE/('segment_exposure_20261009_v1' if args.winter=='first' else 'segment_exposure_second_winter_20261009_v1')).resolve()
    if not out.is_relative_to(PRIVATE.resolve()):parser.error('Private outputs required')
    if out.exists():raise FileExistsError('Preserve existing output')
    verify_seal(DEFAULT_OUT);assert read(DEFAULT_OUT/'prediction_audit.json')['status']=='passed'
    boundary_folder=PRIVATE/'sgis_boundary_2024_v1';boundary_path=boundary_folder/'response.geojson';receipt=read(boundary_folder/'source_receipt.json')
    assert sha(boundary_path)==receipt['sha256'];data=read(boundary_path);assert data['errCd']==0 and len(data['features'])==1
    assert data['features'][0]['properties']['adm_cd']=='35' and data['features'][0]['properties']['adm_nm']=='전북특별자치도'
    boundary=shape(data['features'][0]['geometry']);assert boundary.is_valid and boundary.area>8e9
    source=SOURCE/'spatial/official_directed_environment_review_v1';candidate=SOURCE/'spatial/official_directed_segment_candidates_v1'
    archive=SOURCE/'external/official_nodelink_20240325/NODELINKDATA.zip';base='/vsizip/'+archive.resolve().as_posix()
    links=pyogrio.read_dataframe(base+'/MOCT_LINK.shp',where="ROAD_RANK='101' AND ROAD_NO IN ('15','25','35')",encoding='CP949').to_crs(5179).set_index('LINK_ID')
    pieces=pd.read_csv(source/'segment_piece_environment.csv',dtype={'LINK_ID':str,'ROAD_TYPE':str,'seg_id':str})
    start,end=('2024-11-01','2025-02-28') if args.winter=='first' else ('2025-11-01','2026-02-28')
    plan=dict(PLAN,period_kst=[start,end],model_training_period_kst=['2024-11-01','2025-02-28'],second_winter_validation_scored=False,weather_only_inference=True)
    out.mkdir(parents=True);write(out/'analysis_plan.json',plan);shutil.copy2(__file__,out/'analysis_source.py');shutil.copy2(ROOT/'src/segment_exposure.py',out/'exposure_source.py')
    gpd.GeoDataFrame({'adm_cd':['35'],'year':[2024]},geometry=[boundary],crs=5179).to_file(out/'boundary.gpkg',driver='GPKG')
    paths=[boundary_path,boundary_folder/'source_receipt.json',archive,source/'segment_piece_environment.csv',DEFAULT_OUT/'weather_hgb23.joblib',DEFAULT_OUT/'fit_receipt.json']
    # 두 번째 겨울 경로는 RWIS 파일을 읽지 않는다. 서명 대상도 기상 파일로 한정한다.
    paths += [SOURCE/'point_sources'/name for name in ['aws.parquet','asos.parquet','weather_coordinates.csv']]
    sensitivity=[]
    for group in ['honam_baekyang','seohaean_seocheon','tongyeong_geumsan','tongyeong_seosang']:
        p=PRIVATE/'weather_fallback_20261009_v1'/group/'outer_models/augmented_hgb/model.joblib';paths.append(p);sensitivity.append(joblib.load(p))
    clipped={};piece_rows=[];boundary_qa=[]
    for size in [500,1000]:
        path=source/f'candidate_environment_{size}m.gpkg';paths.append(path);original=gpd.read_file(path);assert original.crs.to_epsg()==5179
        rows=[]
        for offset in [-100,0,100]:
            polygon=boundary.buffer(offset) if offset else boundary
            lengths=np.array([geom.intersection(polygon).length for geom in original.geometry]);boundary_qa.append(dict(size_m=size,buffer_m=offset,segments=int((lengths>1e-6).sum()),directional_length_m=float(lengths.sum())))
        for row in original.itertuples(index=False):
            geom=row.geometry.intersection(boundary)
            if geom.length<=1e-6:continue
            selected=pieces[pieces.size_m.eq(size)&pieces.seg_id.eq(row.seg_id)];env=[]
            for p in selected.itertuples(index=False):
                part=substring(links.loc[p.LINK_ID,'geometry'],p.link_m0,p.link_m1).intersection(boundary)
                if part.length>1e-6:
                    env.append(dict(LINK_ID=p.LINK_ID,length_m=float(part.length),ROAD_TYPE=str(p.ROAD_TYPE).zfill(3),LANES=int(p.LANES),MAX_SPD=int(p.MAX_SPD),UPDATEDATE=str(p.UPDATEDATE)))
                    piece_rows.append(dict(seg_id=row.seg_id,size_m=size,**env[-1]))
            total=sum(e['length_m'] for e in env);assert abs(total-geom.length)<1e-5
            record=dict(seg_id=row.seg_id,route_nm=row.route_nm,flow_lbl=row.flow_lbl,chain_id=row.chain_id,m0=row.m0,m1=row.m1,
                        len_m=float(geom.length),original_length_m=float(row.len_m),boundary_edge=abs(geom.length-row.len_m)>1e-6,
                        official_km_start=None,official_km_end=None,official_chainage_verified=False,sgis_boundary_clipped=True,
                        bridge_code_fraction=sum(e['length_m'] for e in env if e['ROAD_TYPE']=='003')/total,
                        tunnel_code_fraction=sum(e['length_m'] for e in env if e['ROAD_TYPE']=='004')/total,
                        lanes_min=min(e['LANES'] for e in env),lanes_max=max(e['LANES'] for e in env),max_spd_min=min(e['MAX_SPD'] for e in env),max_spd_max=max(e['MAX_SPD'] for e in env),
                        source_date='20230519',physical_structure_extent_verified=False,geometry=geom)
            rows.append(record)
        clipped[size]=gpd.GeoDataFrame(rows,crs=5179);print('Boundary clipped:',size,len(rows),flush=True)
    pd.DataFrame(piece_rows).to_csv(out/'clipped_piece_environment.csv',index=False,encoding='utf-8-sig');pd.DataFrame(boundary_qa).to_csv(out/'boundary_sensitivity.csv',index=False)
    write(out/'input_signature.json',{str(i):dict(path=str(p),sha256=sha(p)) for i,p in enumerate(paths) if p.is_file()})
    cutoff=pd.Timestamp(end)+pd.Timedelta(days=1);point_source=SOURCE/'point_sources';aws=pd.read_parquet(point_source/'aws.parquet');asos=pd.read_parquet(point_source/'asos.parquet')
    assert not {'ice','state_raw','road_temp','SFS','TR1'}&(set(aws)|set(asos))
    builder=WeatherOnlySources(aws.loc[aws.source_time.lt(cutoff)],asos.loc[asos.source_time.lt(cutoff)],pd.read_csv(point_source/'weather_coordinates.csv',dtype={'station_id':str}))
    if args.winter=='second':
        available_aws=set(aws.loc[aws.source_time.lt('2025-03-01')&aws.air_temp.notna(),'station']);available_asos=set(asos.loc[asos.source_time.lt('2025-03-01'),'station'])
        builder.aws={s:d for s,d in builder.aws.items() if s in available_aws};builder.asos={s:d for s,d in builder.asos.items() if s in available_asos}
    times=pd.date_range(start,cutoff,freq='10min',inclusive='left');cached=CachedWeatherPoints(builder,times);project=Transformer.from_crs(5179,4326,always_xy=True)
    model=joblib.load(DEFAULT_OUT/'weather_hgb23.joblib');rows=[];references=[];checks=[];prediction_dir=out/'point_predictions';prediction_dir.mkdir()
    for n,row in enumerate(clipped[500].itertuples(index=False),1):
        middle=row.geometry.interpolate(.5,normalized=True);lon,lat=project.transform(middle.x,middle.y);x,mapping=cached.build(lat,lon)
        if args.winter=='first' and n in [1,len(clipped[500])//2,len(clipped[500])]:
            # 첫 겨울 회귀 입력의 동일성 점검에만 허용된 14지점의 첫 겨울 행을 읽는다.
            rwis=pd.read_parquet(point_source/'rwis.parquet',filters=[('time','<',pd.Timestamp('2025-03-01'))])
            meta=pd.read_csv(SOURCE/'sensor_availability/metadata.csv',dtype={'station':str});meta=meta.loc[meta.kind.eq('RWIS'),['station','route','lat','lon']]
            full_builder=PointInputBuilder(aws.loc[aws.source_time.lt(cutoff)],asos.loc[asos.source_time.lt(cutoff)],rwis,pd.read_csv(point_source/'weather_coordinates.csv',dtype={'station_id':str}),meta)
            full,_=full_builder.build(dict(station='99999',lat=lat,lon=lon,route=row.route_nm),times)
            pd.testing.assert_frame_equal(x[FEATURES+['rain15_max_3h','asos_snow_cm']],full[FEATURES+['rain15_max_3h','asos_snow_cm']],check_dtype=False,rtol=0,atol=0)
            checks.append(row.seg_id)
        with threadpool_limits(limits=2):
            t=np.where(x.asos_air_temp.notna(),model.predict(x[FEATURES]),np.nan)
            other=[np.where(x.asos_air_temp.notna(),m.predict(x[FEATURES]),np.nan) for m in sensitivity]
        result,alarm,valid=exposure(t,x);fractions=[];disagreement=np.zeros(len(x),dtype=bool)
        for v in other:
            r,a,vd=exposure(v,x);assert np.array_equal(valid,vd);fractions.append(r['cold_moist_fraction']);disagreement|=a!=alarm
        result.update(seg_id=row.seg_id,point_lon=float(lon),point_lat=float(lat),sampling='clipped_arc_midpoint',
                      sensitivity_fraction_min=min(fractions),sensitivity_fraction_max=max(fractions),model_disagreement_fraction=float(disagreement[valid].mean()),
                      aws_distance_km_max=float(x.aws_distance_km.max()),asos_distance_km=float(x.asos_distance_km.iloc[0]),
                      verified_ice_probability=False,risk_grade=None)
        rows.append(result);references.append(dict(seg_id=row.seg_id,**mapping))
        q=x[['time','aws_dewpoint','rain15_max_3h','asos_snow_cm']].copy();q['estimated_temperature']=t;q['valid']=valid;q['cold_moist']=alarm
        for i,v in enumerate(other):q[f'sensitivity_temperature_{i}']=v
        q.to_parquet(prediction_dir/(row.seg_id+'.parquet'),index=False,compression='zstd')
        if n%50==0:print('Segment exposure:',n,'/',len(clipped[500]),flush=True)
    table=pd.DataFrame(rows);clipped[500]=clipped[500].merge(table,on='seg_id',validate='one_to_one')
    aggregate=[]
    columns=[c for c in table if c not in ['seg_id','sampling','point_lon','point_lat','verified_ice_probability','risk_grade']]
    for row in clipped[1000].itertuples(index=False):
        child=clipped[500][clipped[500].chain_id.eq(row.chain_id)&clipped[500].m0.ge(row.m0)&clipped[500].m0.lt(row.m1)]
        assert abs(child.len_m.sum()-row.len_m)<1e-5
        r=weighted_summary(child,child.len_m,columns);r.update(seg_id=row.seg_id,sampling='length_weighted_500m_midpoints',verified_ice_probability=False,risk_grade=None);aggregate.append(r)
    clipped[1000]=clipped[1000].merge(pd.DataFrame(aggregate),on='seg_id',validate='one_to_one')
    for size,g in clipped.items():
        assert g.seg_id.is_unique and g.geometry.is_valid.all() and g.len_m.le(size+1e-5).all()
        g.to_file(out/f'segments_{size}m.gpkg',driver='GPKG');g.drop(columns='geometry').to_csv(out/f'segment_exposure_{size}m.csv',index=False,encoding='utf-8-sig')
        # Shapefile의 열 이름 10자 제한과 필드 타입을 명시적으로 처리한다. 전체 스키마는 CSV/GPKG에 보존한다.
        compact=g[['seg_id','route_nm','flow_lbl','len_m','cold_moist_fraction','cold_moist_hours','valid_fraction','bridge_code_fraction','tunnel_code_fraction','model_disagreement_fraction','geometry']].rename(columns={'route_nm':'route','flow_lbl':'direction','cold_moist_fraction':'cm_frac','cold_moist_hours':'cm_hours','valid_fraction':'coverage','bridge_code_fraction':'bridge_fr','tunnel_code_fraction':'tunnel_fr','model_disagreement_fraction':'model_diff'})
        compact.to_file(out/f'segments_{size}m.shp',driver='ESRI Shapefile',encoding='UTF-8')
        for suffix in ['gpkg','shp']:
            reread=gpd.read_file(out/f'segments_{size}m.{suffix}');assert len(reread)==len(g) and list(reread.seg_id)==list(g.seg_id)
            np.testing.assert_allclose(reread.geometry.length,g.geometry.length,rtol=0,atol=1e-6)
    write(out/'point_references.json',references);original,reserved=old_freezes()
    summary=dict(status='completed_research_segment_exposure_not_validated_risk_grade',created_at_utc=datetime.now(timezone.utc).isoformat(),sizes={str(size):dict(segments=len(g),directional_length_m=float(g.len_m.sum()),boundary_edge_segments=int(g.boundary_edge.sum()),minimum_coverage=float(g.valid_fraction.min())) for size,g in clipped.items()},cached_weather_replay_segments=checks,
                 inference_period_kst=[start,end],model_training_period_kst=['2024-11-01','2025-02-28'],second_winter_validation_scored=False,weather_only_inference=True,
                 official_chainage_verified=False,physical_structure_extent_verified=False,source_geometry_preserved=True,source_gaps_filled=False,boundary_scope='2024 SGIS API polygon only',final_submission_approved=False,original_frozen_files=original,reserved_frozen_files=reserved,
                 signatures={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()})
    write(out/'summary.json',summary);print(json.dumps({k:v for k,v in summary.items() if k!='signatures'},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
