"""검증된 세 기상 추정기를 500m 구간 중점에 적용한다. 기존 위험 판정은 유지한다."""
from pathlib import Path
from datetime import datetime,timezone
import sys
import time

import geopandas as gpd
import joblib
import numpy as np
import pandas as pd
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


def statistics(frame):
    result=dict(planned_slots=len(frame),input_range_outside_fraction=float(frame.outside_training_input_range.mean()))
    for target,column in OUTPUT_COLUMNS.items():
        values=frame[column].dropna().to_numpy()
        result[target+'_valid_slots']=len(values)
        for name,value in [('mean',np.mean(values) if len(values) else None),
            ('p10',np.quantile(values,.1) if len(values) else None),
            ('p50',np.median(values) if len(values) else None),
            ('p90',np.quantile(values,.9) if len(values) else None)]:
            result[target+'_'+name]=float(value) if value is not None else None
    for a,b in [('air_temperature','relative_humidity'),('air_temperature','wind_speed'),('relative_humidity','wind_speed')]:
        q=frame[[OUTPUT_COLUMNS[a],OUTPUT_COLUMNS[b]]].dropna()
        result[a+'__'+b+'_paired_slots']=len(q)
        result[a+'__'+b+'_correlation']=float(q.corr().iloc[0,1]) if len(q)>1 and (q.std()>0).all() else None
    return result


def main():
    cfg=ROOT/'config/weather_segment_projection_20261031.json';settings=read(cfg);out=ROOT/settings['output']
    supplement=ROOT/settings['supplement'];verified=read(ROOT/settings['supplement_verification'])
    assert verified['status']=='weather_supplement_verified' and verified['source_receipt_sha256']==sha(supplement/'receipt.json')
    receipt=read(supplement/'receipt.json')
    for p,h in receipt['files'].items():assert sha(supplement/p)==h,p
    prepared=ROOT/settings['input_preparation'];input_receipt=read(prepared/'receipt.json')
    assert input_receipt['status']=='weather_mapping_inputs_verified' and input_receipt['maximum_absolute_difference']==0
    for p,h in input_receipt['source_signatures'].items():assert sha(ROOT/p)==h,p
    source=ROOT/settings['weather_sources'];extra_path=prepared/'asos_supplementary.parquet'
    assert sha(extra_path)==input_receipt['supplementary_sha256']
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in [cfg,Path(__file__),ROOT/settings['point_geometry'],
        ROOT/settings['geometry'],ROOT/settings['archived_segment_estimates'],supplement/'receipt.json',
        ROOT/settings['supplement_verification'],prepared/'receipt.json',extra_path,ROOT/'src/road_weather_points.py',
        ROOT/'src/road_weather_transfer.py',ROOT/'src/road_weather_runtime.py']}
    frozen=verify_preserved()
    if out.exists():assert read(out/'plan.json')['signatures']==signatures
    else:
        out.mkdir(parents=True);(out/'points').mkdir()
        write(out/'plan.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),settings=settings,signatures=signatures,preservation=frozen))
    if (out/'summary.json').exists():raise FileExistsError('Preserve completed weather projection')
    points=pd.read_csv(ROOT/settings['point_geometry'],dtype={'seg_id':str})
    assert len(points)==843 and points.seg_id.is_unique
    weather=WeatherOnlySources(pd.read_parquet(source/'aws.parquet'),pd.read_parquet(source/'asos.parquet'),
        pd.read_csv(source/'weather_coordinates.csv',dtype={'station_id':str}))
    times=pd.DatetimeIndex(np.concatenate([pd.date_range(a,b,freq='10min',inclusive='left').values for a,b in settings['winters']]))
    builder=RoadWeatherPoints(weather,pd.read_parquet(extra_path),times)
    training=pd.read_parquet(supplement/'data/training.parquet',columns=INPUT_COLUMNS)
    low=training.min();high=training.max();metadata=read(supplement/'model/metadata.json')
    models={t:joblib.load(supplement/'model'/record['file']) for t,record in metadata['targets'].items()}
    assert set(models)==set(OUTPUT_COLUMNS)
    summaries=[];days=[];records=[];started=time.perf_counter()
    for number,point in enumerate(points.itertuples(),1):
        predpath=out/'points'/(point.seg_id+'.parquet');recordpath=out/'points'/(point.seg_id+'.json')
        if recordpath.exists():
            record=read(recordpath);assert sha(predpath)==record['prediction_sha256']
            prediction=pd.read_parquet(predpath)
        else:
            if predpath.exists():raise FileExistsError('Unrecorded point output; inspect before resuming')
            with deny_network() as attempts,threadpool_limits(limits=2):
                frame,mapping=builder.build(point.point_lat,point.point_lon);x=features(frame)
                prediction=frame[['time']].copy()
                for target,model in models.items():
                    a,b=baselines(frame,target);valid=np.isfinite(a)&np.isfinite(b)
                    values=np.full(len(frame),np.nan)
                    values[valid]=constrain(model.predict(x.loc[valid])+b[valid],target)
                    prediction[OUTPUT_COLUMNS[target]]=values
                values=frame[INPUT_COLUMNS]
                prediction['outside_training_input_range']=((values.lt(low))|(values.gt(high))).any(axis=1)
            assert not attempts
            prediction.to_parquet(predpath,index=False,compression='zstd')
            record=dict(seg_id=point.seg_id,point_lat=point.point_lat,point_lon=point.point_lon,
                new_asos_source_domain=str(mapping['asos_station'])=='172',mapping=mapping,
                prediction_sha256=sha(predpath),rows=len(prediction))
            write(recordpath,record)
        records.append(record)
        assert len(prediction)==34560 and pd.DatetimeIndex(prediction.time).equals(times)
        for year,q in prediction.groupby(np.where(prediction.time.dt.month>=11,prediction.time.dt.year,prediction.time.dt.year-1)):
            summaries.append(dict(seg_id=point.seg_id,winter=int(year),route_nm=point.route_nm,flow_lbl=point.flow_lbl,
                len_m=point.len_m,point_lat=point.point_lat,point_lon=point.point_lon,
                asos_station=record['mapping']['asos_station'],new_asos_source_domain=record['new_asos_source_domain'],**statistics(q)))
        daily=prediction.assign(date=prediction.time.dt.normalize()).groupby('date').agg(
            **{target+'_mean':(column,'mean') for target,column in OUTPUT_COLUMNS.items()},
            **{target+'_valid_slots':(column,'count') for target,column in OUTPUT_COLUMNS.items()},
            outside_training_input_range_slots=('outside_training_input_range','sum')).reset_index()
        daily.insert(0,'seg_id',point.seg_id);days.append(daily)
        if number%20==0 or number==843:
            print('PROJECT',number,'/843',round(time.perf_counter()-started,1),'seconds',flush=True)
    summary=pd.DataFrame(summaries);summary.to_csv(out/'weather_segments_500m.csv',index=False,encoding='utf-8-sig')
    daily=pd.concat(days,ignore_index=True);daily.to_parquet(out/'weather_segment_daily.parquet',index=False,compression='zstd')
    daily.to_csv(out/'weather_segment_daily.csv.gz',index=False,encoding='utf-8',compression='gzip')
    previous=pd.read_csv(ROOT/settings['archived_segment_estimates'],dtype={'seg_id':str})
    previous=previous.loc[previous.scale_m.eq(500),['seg_id','winter','prediction_group','estimated_temp_mean_c','cold_wet_fraction']]
    combined=summary.merge(previous,on=['seg_id','winter'],how='left',validate='one_to_one')
    assert combined.prediction_group.notna().all()
    combined.to_csv(out/'weather_and_preserved_road_estimates.csv',index=False,encoding='utf-8-sig')
    geometry=gpd.read_file(ROOT/settings['geometry'],columns=['seg_id','geometry'])
    for year,q in combined.groupby('winter'):
        g=geometry.merge(q,on='seg_id',validate='one_to_one')
        g.to_file(out/'weather_segments.gpkg',layer=f'winter_{year}',driver='GPKG')
    assert verify_preserved()==frozen
    write(out/'summary.json',dict(status='weather_segment_projection_complete',segment_count=843,winters=2,
        ten_minute_rows=sum(r['rows'] for r in records),daily_rows=len(daily),summary_rows=len(summary),
        new_asos_source_segments=sum(r['new_asos_source_domain'] for r in records),
        source_candidate_sets=len({(r['mapping']['asos_station'],tuple(v['station'] for v in r['mapping']['aws_candidates'])) for r in records}),
        classification_changed=False,risk_threshold_changed=False,new_independent_assessment=False,
        seconds=time.perf_counter()-started,preservation=frozen,point_records=records,
        files={p.relative_to(out).as_posix():sha(p) for p in out.iterdir() if p.is_file()}))
    print('PROJECTION COMPLETE',len(summary),len(daily),flush=True)


if __name__=='__main__':main()
