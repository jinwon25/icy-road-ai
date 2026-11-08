"""전 구간 집계·기존 성분 보존과 대표19구간의 새 습도 API 재추론을 검증한다."""
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,verify_preserved
from src.data_source import sha256_file as sha
from src.segment_exposure import WeatherOnlySources
from src.road_weather_points import RoadWeatherPoints
from src.weather_history_runtime import predict_humidity_history
from src.offline_runtime import deny_network


def main():
    out=ROOT/'outputs/private/weather_history_segment_projection_20261101_v1'
    old=ROOT/'outputs/private/weather_segment_projection_20261031_v1'
    summary=read(out/'summary.json');plan=read(out/'plan.json');settings=plan['settings']
    if (out/'independent_verification.json').exists():raise FileExistsError('Preserve completed history map audit')
    for path,digest in plan['signatures'].items():assert sha(ROOT/path)==digest,path
    for path,digest in summary['files'].items():assert sha(out/path)==digest,path
    prior=read(old/'summary.json');originals={r['seg_id']:r for r in prior['point_records']}
    options=dict(dtype={'seg_id':str},float_precision='round_trip')
    table=pd.read_csv(out/'weather_segments_500m.csv',**options).set_index(['seg_id','winter'])
    daily=pd.read_parquet(out/'weather_segment_daily.parquet').set_index(['seg_id','date'])
    csv_daily=pd.read_csv(out/'weather_segment_daily.csv.gz',dtype={'seg_id':str},parse_dates=['date'],float_precision='round_trip').set_index(['seg_id','date'])
    pd.testing.assert_frame_equal(daily,csv_daily,check_exact=True)
    assert len(table)==1686 and len(daily)==202320 and not table.index.duplicated().any() and not daily.index.duplicated().any()
    checks=0;preserved_values=0;changed=0;total_valid=0;absolute_delta=0.;maximum_delta=0.
    for record in summary['point_records']:
        segment=record['seg_id'];path=out/'points'/(segment+'.parquet');original=old/'points'/path.name
        assert sha(path)==record['prediction_sha256']
        assert sha(original)==record['original_prediction_sha256']==originals[segment]['prediction_sha256']
        assert record['mapping']==originals[segment]['mapping']
        f=pd.read_parquet(path);before=pd.read_parquet(original)
        for column in ['time','estimated_air_temperature_c','estimated_wind_speed_ms','outside_training_input_range']:
            np.testing.assert_array_equal(f[column],before[column]);preserved_values+=len(f)
        p=f.estimated_humidity_pct.to_numpy();b=before.estimated_humidity_pct.to_numpy()
        np.testing.assert_array_equal(np.isfinite(p),np.isfinite(b))
        good=np.isfinite(p);assert ((p[good]>=0)&(p[good]<=100)).all()
        delta=np.abs(p[good]-b[good]);changed+=int((delta!=0).sum());total_valid+=len(delta)
        absolute_delta+=float(delta.sum());maximum_delta=max(maximum_delta,float(delta.max()))
        expected_dates=pd.DatetimeIndex(f.time.iloc[::144]).normalize()
        day=daily.loc[segment].loc[expected_dates]
        for target,column in [('air_temperature','estimated_air_temperature_c'),
            ('relative_humidity','estimated_humidity_pct'),('wind_speed','estimated_wind_speed_ms')]:
            values=f[column].to_numpy().reshape(240,144);count=np.isfinite(values).sum(axis=1)
            mean=np.divide(np.nansum(values,axis=1),count,out=np.full(240,np.nan),where=count>0)
            np.testing.assert_allclose(mean,day[target+'_mean'],rtol=0,atol=1e-10,equal_nan=True)
            np.testing.assert_array_equal(count,day[target+'_valid_slots']);checks+=480
            for year,part in zip([2024,2025],np.split(f[column].to_numpy(),2)):
                values=part[np.isfinite(part)];r=table.loc[segment,year]
                assert int(r[target+'_valid_slots'])==len(values);checks+=1
                for suffix,value in [('mean',values.mean()),('p10',np.quantile(values,.1)),
                    ('p50',np.quantile(values,.5)),('p90',np.quantile(values,.9))]:
                    np.testing.assert_allclose(r[target+'_'+suffix],value,rtol=0,atol=1e-10);checks+=1
        for year,q in zip([2024,2025],np.split(np.arange(len(f)),2)):
            r=table.loc[segment,year]
            np.testing.assert_allclose(r.humidity_history_partial_fraction,
                f.humidity_history_status.iloc[q].ne('complete_24h').mean(),rtol=0,atol=1e-15)
            np.testing.assert_allclose(r.humidity_history_outside_fraction,
                f.humidity_history_outside_training_range.iloc[q].mean(),rtol=0,atol=1e-15);checks+=2
            for left,right in [('air_temperature','relative_humidity'),('air_temperature','wind_speed'),('relative_humidity','wind_speed')]:
                names={'air_temperature':'estimated_air_temperature_c','relative_humidity':'estimated_humidity_pct','wind_speed':'estimated_wind_speed_ms'}
                x=f[names[left]].iloc[q].to_numpy();y=f[names[right]].iloc[q].to_numpy()
                valid=np.isfinite(x)&np.isfinite(y);key=left+'__'+right
                assert int(r[key+'_paired_slots'])==int(valid.sum());checks+=1
                if valid.sum()>1 and np.ptp(x[valid])>0 and np.ptp(y[valid])>0:
                    np.testing.assert_allclose(r[key+'_correlation'],np.corrcoef(x[valid],y[valid])[0,1],atol=1e-10,rtol=0)
                else:assert pd.isna(r[key+'_correlation'])
                checks+=1
        np.testing.assert_array_equal(f.humidity_history_outside_training_range.to_numpy().reshape(240,144).sum(axis=1),
            day.humidity_history_outside_slots)
        np.testing.assert_array_equal(f.humidity_history_status.ne('complete_24h').to_numpy().reshape(240,144).sum(axis=1),
            day.humidity_history_partial_slots);checks+=480
    preserved=['prediction_group','estimated_temp_mean_c','cold_wet_fraction']
    a=pd.read_csv(old/'weather_and_preserved_road_estimates.csv',**options).set_index(['seg_id','winter'])
    b=pd.read_csv(out/'weather_and_preserved_road_estimates.csv',**options).set_index(['seg_id','winter'])
    pd.testing.assert_frame_equal(a[preserved].sort_index(),b[preserved].sort_index(),check_exact=True)
    old_daily=pd.read_parquet(old/'weather_segment_daily.parquet').set_index(['seg_id','date'])
    columns=['air_temperature_mean','air_temperature_valid_slots','wind_speed_mean','wind_speed_valid_slots','outside_training_input_range_slots']
    pd.testing.assert_frame_equal(daily[columns].sort_index(),old_daily[columns].sort_index(),check_exact=True)
    geometry=gpd.read_file(ROOT/settings['geometry'],columns=['seg_id','geometry']).set_index('seg_id')
    for year in [2024,2025]:
        layer=gpd.read_file(out/'weather_segments.gpkg',layer=f'winter_{year}').set_index('seg_id')
        assert len(layer)==843 and layer.crs==geometry.crs
        assert layer.geometry.sort_index().equals(geometry.geometry.sort_index())
        np.testing.assert_allclose(layer.relative_humidity_mean.sort_index(),
            table.xs(year,level='winter').relative_humidity_mean.sort_index(),rtol=0,atol=1e-10)
    points=pd.read_csv(ROOT/settings['point_geometry'],dtype={'seg_id':str})
    selected=set(points.iloc[np.linspace(0,len(points)-1,17,dtype=int)].seg_id)
    selected.add(next(r['seg_id'] for r in summary['point_records'] if r['new_asos_source_domain']))
    selected.add(table.humidity_history_outside_fraction.idxmax()[0])
    for segment in points.seg_id:
        if len(selected)>=19:break
        selected.add(segment)
    selected=sorted(selected)[:19]
    source=ROOT/settings['weather_sources'];prepared=ROOT/settings['input_preparation']
    times=pd.DatetimeIndex(np.concatenate([pd.date_range(a,b,freq='10min',inclusive='left').values for a,b in settings['winters']]))
    builder=RoadWeatherPoints(WeatherOnlySources(pd.read_parquet(source/'aws.parquet'),pd.read_parquet(source/'asos.parquet'),
        pd.read_csv(source/'weather_coordinates.csv',dtype={'station_id':str})),pd.read_parquet(prepared/'asos_supplementary.parquet'),times)
    model=ROOT/'outputs/private/weather_history_supplement_20261101_v2/model/humidity_history_v1';replayed=0
    for segment in selected:
        point=points.loc[points.seg_id.eq(segment)].iloc[0]
        with deny_network() as attempts,threadpool_limits(limits=2):
            frame,_=builder.build(point.point_lat,point.point_lon)
            actual=predict_humidity_history(frame.assign(station=segment),model)
        assert not attempts
        expected=pd.read_parquet(out/'points'/(segment+'.parquet'))
        for column in ['estimated_humidity_pct','humidity_history_input_slots_24h','humidity_history_status','humidity_history_outside_training_range']:
            np.testing.assert_array_equal(actual[column],expected[column]);replayed+=len(actual)
        print('REPLAY',segment,flush=True)
    assert verify_preserved()==summary['preservation']
    write(out/'independent_verification.json',dict(status='passed',summary_sha256=sha(out/'summary.json'),
        aggregate_checks=checks,preserved_point_values=preserved_values,replayed_values=replayed,replayed_segments=selected,
        valid_humidity_rows=total_valid,changed_estimate_rows=changed,mean_absolute_estimate_change=absolute_delta/total_valid,
        maximum_absolute_estimate_change=maximum_delta,interpretation='Estimate changes, not measured error or new segment validation',
        preserved_daily_rows=len(daily),preserved_road_estimate_rows=len(b),audit_source_sha256=sha(Path(__file__))))
    print('HISTORY MAP VERIFIED',checks,preserved_values,replayed,flush=True)


if __name__=='__main__':main()
