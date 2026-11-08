"""843구간 습도만 수정 모형으로 재추정하고 기존 기온·풍속·노면 결과를 보존한다."""
from pathlib import Path
import sys
import time

import geopandas as gpd
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,now,verify_preserved
from scripts.project_weather_segments import statistics
from src.data_source import sha256_file as sha
from src.segment_exposure import WeatherOnlySources
from src.road_weather_points import RoadWeatherPoints
from src.road_weather_runtime import OUTPUT_COLUMNS
from src.weather_history_runtime import predict_humidity_history
from src.offline_runtime import deny_network


def main():
    cfg=ROOT/'config/weather_segment_projection_20261031.json';settings=read(cfg)
    old=ROOT/'outputs/private/weather_segment_projection_20261031_v1'
    supplement=ROOT/'outputs/private/weather_history_supplement_20261101_v2'
    verification=ROOT/'outputs/private/weather_history_supplement_validation_20261101_v2/receipt.json'
    checked=read(verification);assert checked['status']=='weather_history_supplement_verified'
    assert checked['source_receipt_sha256']==sha(supplement/'receipt.json')
    old_summary=read(old/'summary.json');old_audit=read(old/'independent_verification.json')
    assert old_audit['status']=='passed' and old_audit['summary_sha256']==sha(old/'summary.json')
    for path,digest in read(supplement/'receipt.json')['files'].items():assert sha(supplement/path)==digest,path
    source=ROOT/settings['weather_sources'];prepared=ROOT/settings['input_preparation']
    input_receipt=read(prepared/'receipt.json')
    for path,digest in input_receipt['source_signatures'].items():assert sha(ROOT/path)==digest,path
    assert sha(prepared/'asos_supplementary.parquet')==input_receipt['supplementary_sha256']
    out=ROOT/'outputs/private/weather_history_segment_projection_20261101_v1'
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in [cfg,Path(__file__),verification,
        supplement/'receipt.json',old/'summary.json',ROOT/settings['point_geometry'],ROOT/settings['geometry'],
        ROOT/'src/weather_history_runtime.py',ROOT/'src/weather_history_stable.py',ROOT/'src/road_weather_points.py']}
    if out.exists():
        assert read(out/'plan.json')['signatures']==signatures
        if (out/'summary.json').exists():raise FileExistsError('Preserve completed history projection')
    else:
        out.mkdir(parents=True);(out/'points').mkdir()
        write(out/'plan.json',dict(at_utc=now(),signatures=signatures,settings=settings,
            source=old.relative_to(ROOT).as_posix(),preservation=checked['preservation']))
    points=pd.read_csv(ROOT/settings['point_geometry'],dtype={'seg_id':str});assert len(points)==843
    times=pd.DatetimeIndex(np.concatenate([pd.date_range(a,b,freq='10min',inclusive='left').values for a,b in settings['winters']]))
    weather=WeatherOnlySources(pd.read_parquet(source/'aws.parquet'),pd.read_parquet(source/'asos.parquet'),
        pd.read_csv(source/'weather_coordinates.csv',dtype={'station_id':str}))
    builder=RoadWeatherPoints(weather,pd.read_parquet(prepared/'asos_supplementary.parquet'),times)
    originals={r['seg_id']:r for r in old_summary['point_records']}
    records=[];summaries=[];days=[];start=time.perf_counter()
    for number,point in enumerate(points.itertuples(),1):
        path=out/'points'/(point.seg_id+'.parquet');metadata=path.with_suffix('.json')
        original_path=old/'points'/path.name;prior=originals[point.seg_id]
        assert sha(original_path)==prior['prediction_sha256']
        if metadata.exists():
            record=read(metadata);assert sha(path)==record['prediction_sha256'];prediction=pd.read_parquet(path)
        else:
            if path.exists():raise FileExistsError('Unrecorded segment history output')
            with deny_network() as attempts,threadpool_limits(limits=2):
                frame,mapping=builder.build(point.point_lat,point.point_lon)
                assert mapping==prior['mapping']
                frame=frame.assign(station=point.seg_id)
                humidity=predict_humidity_history(frame,supplement/'model/humidity_history_v1')
            assert not attempts and pd.DatetimeIndex(humidity.time).equals(times)
            prediction=pd.read_parquet(original_path)
            prediction['estimated_humidity_pct']=humidity.estimated_humidity_pct.to_numpy()
            for column in ['humidity_history_input_slots_24h','humidity_history_status','humidity_history_outside_training_range']:
                prediction[column]=humidity[column].to_numpy()
            prediction.to_parquet(path,index=False,compression='zstd')
            record=dict(prior)
            record.update(prediction_sha256=sha(path),original_prediction_sha256=prior['prediction_sha256'])
            write(metadata,record)
        records.append(record)
        assert len(prediction)==34560 and pd.DatetimeIndex(prediction.time).equals(times)
        winter=np.where(prediction.time.dt.month>=11,prediction.time.dt.year,prediction.time.dt.year-1)
        for year,q in prediction.groupby(winter):
            summaries.append(dict(seg_id=point.seg_id,winter=int(year),route_nm=point.route_nm,flow_lbl=point.flow_lbl,
                len_m=point.len_m,point_lat=point.point_lat,point_lon=point.point_lon,
                asos_station=record['mapping']['asos_station'],new_asos_source_domain=record['new_asos_source_domain'],
                humidity_history_partial_fraction=float(q.humidity_history_status.ne('complete_24h').mean()),
                humidity_history_outside_fraction=float(q.humidity_history_outside_training_range.mean()),**statistics(q)))
        daily=prediction.assign(date=prediction.time.dt.normalize(),
            history_partial_flag=prediction.humidity_history_status.ne('complete_24h')).groupby('date').agg(
            **{target+'_mean':(column,'mean') for target,column in OUTPUT_COLUMNS.items()},
            **{target+'_valid_slots':(column,'count') for target,column in OUTPUT_COLUMNS.items()},
            outside_training_input_range_slots=('outside_training_input_range','sum'),
            humidity_history_outside_slots=('humidity_history_outside_training_range','sum'),
            humidity_history_partial_slots=('history_partial_flag','sum')).reset_index()
        daily.insert(0,'seg_id',point.seg_id);days.append(daily)
        if number%20==0 or number==843:print('PROJECT',number,'/843',round(time.perf_counter()-start,1),'seconds',flush=True)
    summary=pd.DataFrame(summaries);summary.to_csv(out/'weather_segments_500m.csv',index=False,encoding='utf-8-sig')
    daily=pd.concat(days,ignore_index=True);daily.to_parquet(out/'weather_segment_daily.parquet',index=False,compression='zstd')
    daily.to_csv(out/'weather_segment_daily.csv.gz',index=False,encoding='utf-8',compression='gzip')
    previous=pd.read_csv(old/'weather_and_preserved_road_estimates.csv',dtype={'seg_id':str},float_precision='round_trip')
    preserved=['seg_id','winter','prediction_group','estimated_temp_mean_c','cold_wet_fraction']
    combined=summary.merge(previous[preserved],on=['seg_id','winter'],how='left',validate='one_to_one')
    assert combined.prediction_group.notna().all()
    combined.to_csv(out/'weather_and_preserved_road_estimates.csv',index=False,encoding='utf-8-sig')
    geometry=gpd.read_file(ROOT/settings['geometry'],columns=['seg_id','geometry'])
    for year,q in combined.groupby('winter'):
        geometry.merge(q,on='seg_id',validate='one_to_one').to_file(out/'weather_segments.gpkg',layer=f'winter_{year}',driver='GPKG')
    assert verify_preserved()==checked['preservation']
    write(out/'summary.json',dict(status='weather_history_segment_projection_complete',segment_count=843,winters=2,
        ten_minute_rows=sum(r['rows'] for r in records),daily_rows=len(daily),summary_rows=len(summary),
        new_asos_source_segments=old_summary['new_asos_source_segments'],source_candidate_sets=old_summary['source_candidate_sets'],
        road_temperature_changed=False,air_temperature_changed=False,wind_changed=False,icing_changed=False,
        seconds=time.perf_counter()-start,point_records=records,preservation=checked['preservation'],
        files={p.relative_to(out).as_posix():sha(p) for p in out.iterdir() if p.is_file()}))
    print('HISTORY PROJECTION COMPLETE',len(summary),len(daily),flush=True)


if __name__=='__main__':main()
