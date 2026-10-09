"""467개 중점의 10분 온도·조건 노출 초안을 생성한다. Ice·사고 위험 등급과 구별한다."""
import argparse
import json
import sys
from pathlib import Path
import geopandas as gpd
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.point_inputs import PointInputBuilder
from src.condition_exposure import cold_moisture_condition
from src.data_source import sha256_file


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int);args=parser.parse_args()
    private=ROOT/'outputs/private';out=private/('smoke_segment_inference' if args.limit else 'segment_inference_v1');out.mkdir(parents=True,exist_ok=True)
    parity=json.loads((private/'point_sources/parity_verification.json').read_text(encoding='utf-8'))
    if parity['stations']!=14 or parity['feature_count']!=55:raise ValueError('Input parity has not passed')
    segments=gpd.read_file(private/'spatial/segment_scaffold/segments.gpkg')
    points=gpd.GeoSeries(segments.geometry.interpolate(.5,normalized=True),crs=segments.crs).to_crs(4326)
    segments['lon']=points.x;segments['lat']=points.y
    card_path=private/'model_candidates/temperature_v1/model_card.json';card=json.loads(card_path.read_text(encoding='utf-8'))
    model=joblib.load(private/'model_candidates/temperature_v1/weather_ridge.joblib')
    periods=json.loads((ROOT/'config/evaluation.json').read_text(encoding='utf-8'))['evaluation_periods']
    times=pd.DatetimeIndex([])
    for start,end in periods:times=times.append(pd.date_range(start,pd.Timestamp(end)+pd.Timedelta(hours=23,minutes=50),freq='10min'))
    signature={'model_card':sha256_file(card_path),'point_inputs':sha256_file(ROOT/'src/point_inputs.py'),
               'runner':sha256_file(Path(__file__)),'condition_code':sha256_file(ROOT/'src/condition_exposure.py'),
               'source_manifest':sha256_file(private/'point_sources/summary.json'),'segment_geometry':sha256_file(private/'spatial/segment_scaffold/segments.gpkg')}
    manifest=out/'input_signature.json'
    if manifest.exists() and json.loads(manifest.read_text(encoding='utf-8'))!=signature:raise ValueError('Changed inference signature; preserve previous outputs')
    manifest.write_text(json.dumps(signature,indent=2),encoding='utf-8')
    builder=PointInputBuilder.from_root(ROOT);summaries=[]
    if args.limit:segments=segments.iloc[:args.limit]
    # 대규모 실행 전에 도로 파일/RWIS 노선 표기의 대응과 참조를 전수 확인한다.
    for row in segments.itertuples():
        point={'station':row.seg_id,'route':row.route_nm,'lat':row.lat,'lon':row.lon}
        near,distance=builder._reference(point,set())
        if near is None or not np.isfinite(distance):raise ValueError(f'No same-route RWIS reference for segment {row.seg_id}')
    radius=card['absolute_error_p90_reference_c']
    with threadpool_limits(limits=2):
        for index,row in enumerate(segments.itertuples(),1):
            folder=out/row.seg_id;folder.mkdir(exist_ok=True);done=folder/'summary.json'
            if done.exists():summaries.append(json.loads(done.read_text(encoding='utf-8')));continue
            point={'station':row.seg_id,'route':row.route_nm,'lat':row.lat,'lon':row.lon}
            features,mapping=builder.build(point,times)
            if mapping['near_source'] is None:raise AssertionError('Expected route reference disappeared')
            weather=model.predict(features[card['feature_names']])
            blended=np.where(features.neighbor_road_temp.notna(),.5*(weather+features.neighbor_road_temp),weather)
            blended=np.where(features.asos_air_temp.notna(),blended,np.nan)
            result=features[['station','time','aws_air_temp','aws_dewpoint','aws_humidity','aws_rain_15m','rain15_max_24h','rain_coverage_24h','aws_distance_km','aws_age_minutes','asos_distance_km','asos_age_minutes','near_distance_km','neighbor_age_minutes']].copy()
            result=result.rename(columns={'station':'segment_id'});result['estimated_road_temp_c']=blended
            result['temp_sensitivity_low_c']=blended-radius;result['temp_sensitivity_high_c']=blended+radius
            for name,temperature in [('condition_exposure',blended),('condition_exposure_low',blended+radius),('condition_exposure_high',blended-radius)]:
                result[name]=cold_moisture_condition(temperature,features.aws_dewpoint,features.rain15_max_24h)
            if not (result.condition_exposure_low.fillna(0)<=result.condition_exposure_high.fillna(1)).all():raise AssertionError('Sensitivity order failure')
            features.to_parquet(folder/'features.parquet',index=False,compression='zstd')
            result.to_parquet(folder/'predictions.parquet',index=False,compression='zstd')
            # 제출 검토용 CSV. 원본 상태 또는 가짜 Ice 정답을 추가하지 않는다.
            result.to_csv(folder/'temperature_10min.csv.gz',index=False,encoding='utf-8-sig',compression='gzip')
            def exposure(name):
                valid=result[name].notna();return {'valid_slots':int(valid.sum()),'exposure_slots':int(result[name].eq(1).sum()),'sample_equivalent_hours':float(result[name].eq(1).sum()/6)}
            record={'segment_id':row.seg_id,'route':row.route_nm,'lat':row.lat,'lon':row.lon,'length_m':row.length_m,'rows':len(result),
                    'temperature_available':int(np.isfinite(blended).sum()),'estimated_temperature_min_c':float(np.nanmin(blended)),
                    'neighbor_temperature_available':int(features.neighbor_road_temp.notna().sum()),
                    'weather_only_temperature_slots':int((np.isfinite(blended)&features.neighbor_road_temp.isna()).sum()),
                    'estimated_temperature_mean_c':float(np.nanmean(blended)),'subzero_sample_equivalent_hours':float(np.sum(blended<=0)/6),
                    'conditions':{name:exposure(name) for name in ['condition_exposure','condition_exposure_low','condition_exposure_high']},
                    'mapping':mapping,'near_rwis_distance_km':float(features.near_distance_km.iloc[0]),
                    'feature_sha256':sha256_file(folder/'features.parquet'),'predictions_sha256':sha256_file(folder/'predictions.parquet')}
            done.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');summaries.append(record)
            if index%20==0 or index==len(segments):print(f'Segments {index}/{len(segments)} complete',flush=True)
    flat=[]
    for s in summaries:
        row={k:v for k,v in s.items() if not isinstance(v,dict)}
        for name,values in s['conditions'].items():row.update({name+'_'+k:v for k,v in values.items()})
        row.update({k:v for k,v in s['mapping'].items() if not isinstance(v,list)});flat.append(row)
    pd.DataFrame(flat).to_csv(out/'segment_temperature_summary.csv',index=False,encoding='utf-8-sig')
    summary={'status':'draft_segment_temperature_and_condition_exposure','segments':len(summaries),'rows':sum(r['rows'] for r in summaries),
             'temperature_available':sum(r['temperature_available'] for r in summaries),'source_length_m':sum(r['length_m'] for r in summaries),
             'absolute_error_sensitivity_radius_c':radius,'signature':signature,'official_holdout_used':False,
             'limitations':['Midpoint estimates for geometric fragments, not verified official chainage or directions.',
                            'Condition exposure is estimated temperature<=0 with prior rain24h or estimated temperature<=AWS dewpoint; it is not an Ice probability, observed event or accident risk.',
                            'Hours are ten-minute sample equivalents; dependence and missing intervals prevent independent-event interpretation.',
                            'Sensitivity uses an empirical developmental residual radius, not a guaranteed confidence interval.',
                            'Static facilities/terrain and classification are joined in separate deliverables; this is not the final competition risk map.']}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:summary[k] for k in ['status','segments','rows','temperature_available']}),flush=True)


if __name__=='__main__':main()
