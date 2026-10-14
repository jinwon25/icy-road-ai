"""새 후보의 재적합·기상 시각·전수 추론·보호 위치 색인을 정답 없이 검산한다."""
from datetime import datetime,timezone
from pathlib import Path
import subprocess
import sys
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write,preservation
from src.data_source import sha256_file as sha
from src.submission_runtime import FEATURES,WATER
from src.offline_runtime import deny_network
from scripts.baseline_ice_logistic import add_time_features

OUT=ROOT/'outputs/private/submission_candidate_20261013_v1'
CACHE=ROOT/'outputs/private/releases/20261007/outputs/private/point_sources'


def prior(source,times,columns):
    source=source.sort_values('source_time');st=source.source_time.to_numpy(dtype='datetime64[ns]');query=times.to_numpy(dtype='datetime64[ns]')
    ids=np.searchsorted(st,query,side='left')-1
    safe=np.maximum(ids,0);age=(query-st[safe])/np.timedelta64(1,'m');valid=(ids>=0)&(age>0)&(age<=60)
    result=source[columns].to_numpy(float)[safe].copy();result[~valid]=np.nan;age[~valid]=np.nan
    return result,age


def main():
    target=OUT/'validation/independent_verification.json'
    if target.exists():raise FileExistsError('Preserve completed package audit')
    frozen=preservation();manifest=read(OUT/'data/prediction_group_manifest.json');spatial=read(OUT/'spatial_receipt.json')
    for rel,h in read(OUT/'spatial_input_signatures.json').items():assert sha(ROOT/rel)==h
    training=pd.read_parquet(OUT/'data/training_weather_temperature.parquet');plan=read(OUT/'training_plan.json')
    assert set(training.station)==set(plan['allowed_stations']) and training.time.lt('2025-03-01').all()
    assert not {'ice','state_raw','state','label'}.intersection(training.columns)
    refit=OUT/'validation/refit_models'
    if refit.exists():raise FileExistsError('Preserve earlier model audit')
    result=subprocess.run([sys.executable,'-X','utf8',str(OUT/'code/train.py'),'--output',str(refit)],cwd=OUT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    (OUT/'validation/training_replay.log').write_bytes(result.stdout);assert result.returncode==0
    names=['weather12_mse300','weather12_mae300'];models=[joblib.load(OUT/'model'/(n+'.joblib')) for n in names]
    refitted=[joblib.load(refit/(n+'.joblib')) for n in names]
    aws=pd.read_parquet(CACHE/'aws.parquet',columns=['station','source_time','air_temp','humidity','wind_speed','rain_15m','dewpoint','rain15_max_3h'])
    asos=pd.read_parquet(CACHE/'asos.parquet',columns=['station','source_time','air_temp','snow_cm'])
    aws={str(s):f.loc[f.air_temp.notna()] for s,f in aws.groupby('station')};asos={str(s):f for s,f in asos.groupby('station')}
    values_verified=0;features_verified=0;refit_verified=0
    with deny_network() as attempts,threadpool_limits(limits=2):
        for i,(key,info) in enumerate(sorted(manifest.items())):
            w=pd.read_parquet(OUT/'data/weather_groups'/(key+'.parquet'));p=pd.read_parquet(OUT/'data/prediction_groups'/(key+'.parquet'))
            assert sha(OUT/'data/weather_groups'/(key+'.parquet'))==info['weather_sha256']
            assert sha(OUT/'data/prediction_groups'/(key+'.parquet'))==info['predictions_sha256']
            assert not {'road_temp','ice','state_raw'}.intersection(w.columns)
            assert len(w)==17280 and w[['station','time']].equals(p[['station','time']])
            times=w.time;cols=['air_temp','humidity','wind_speed','rain_15m','dewpoint','rain15_max_3h']
            a=np.full((len(w),len(cols)),np.nan);age=np.full(len(w),np.nan)
            for sid in info['aws_candidates']:
                joined,ja=prior(aws[sid],times,cols);take=np.isnan(a[:,0])&np.isfinite(joined[:,0]);a[take]=joined[take];age[take]=ja[take]
            b,ba=prior(asos[info['asos_station']],times,['air_temp','snow_cm'])
            expected=add_time_features(pd.DataFrame({'time':times}))
            for c,v in zip(['aws_air_temp','aws_humidity','aws_wind_speed','aws_rain_15m','aws_dewpoint','rain15_max_3h'],a.T):expected[c]=v
            expected['aws_age_minutes']=age;expected['asos_air_temp']=b[:,0];expected['asos_snow_cm']=b[:,1];expected['asos_age_minutes']=ba
            keys=[*FEATURES,*[c for c in WATER if c not in FEATURES]]
            np.testing.assert_allclose(expected[keys],w[keys],rtol=0,atol=1e-12);features_verified+=len(w)*len(keys)
            components=[m.predict(w[list(FEATURES)]) for m in models];mean=(components[0]+components[1])/2
            valid_t=np.isfinite(w.asos_air_temp)&w.asos_age_minutes.between(0,60);mean[~valid_t]=np.nan
            np.testing.assert_allclose(mean,p.estimated_road_temp_c,rtol=0,atol=1e-10)
            np.testing.assert_allclose(np.abs(components[0]-components[1]),p.temperature_component_spread_c,rtol=0,atol=1e-10)
            water=w[list(WATER)].to_numpy();valid=valid_t&~np.isnan(water).all(axis=1)
            wet=(water[:,0]>=mean)|(water[:,1]>0)|(water[:,2]>0)
            classification=np.where(valid,((mean<=0)&wet).astype(float),np.nan)
            np.testing.assert_array_equal(classification,p.predicted_ice.to_numpy(float,na_value=np.nan))
            values_verified+=len(w)*3
            if i in [0,len(manifest)//2,len(manifest)-1]:
                for m,new in zip(models,refitted):np.testing.assert_allclose(m.predict(w[list(FEATURES)]),new.predict(w[list(FEATURES)]),rtol=0,atol=1e-10);refit_verified+=len(w)
            if (i+1)%40==0:print('검산 그룹',i+1,len(manifest),flush=True)
    assert attempts==[]
    index=pd.read_csv(OUT/'data/point_prediction_index.csv',dtype={'id':str,'winter':str,'prediction_group':str})
    target_predictions=pd.read_csv(OUT/'data/protected_predictions_10min.csv.gz',dtype={'station':str,'winter':str},parse_dates=['time'])
    for row in index.loc[index.kind.eq('protected')].itertuples():
        reference=pd.read_parquet(OUT/'data/prediction_groups'/(row.prediction_group+'.parquet'))
        saved=target_predictions.loc[target_predictions.station.eq(row.id)&target_predictions.winter.eq(row.winter)].reset_index(drop=True)
        assert saved.time.equals(reference.time)
        for c in ['estimated_road_temp_c','temperature_component_spread_c','predicted_ice']:
            np.testing.assert_allclose(saved[c].astype(float),reference[c].to_numpy(float,na_value=np.nan),rtol=0,atol=1e-10)
    assert len(target_predictions)==103680 and not target_predictions.duplicated(['station','time']).any()
    assert preservation()==frozen
    write(target,dict(status='submission_candidate_independent_audit_passed',verified_at_utc=datetime.now(timezone.utc).isoformat(),
        group_count=len(manifest),weather_feature_values_verified=features_verified,prediction_values_verified=values_verified,
        training_reproduction_fits=2,refitted_prediction_values_verified=refit_verified,target_rows_verified=len(target_predictions),
        input_time_join='independent_numpy_searchsorted_strictly_previous_60_minutes',
        protected_or_opened_assessment_labels_used=False,second_winter_weather_only=True,network_attempts=0,
        official_score_computed=False,model_promoted=False,submitted=False,old_frozen_files=frozen[0],reserved_frozen_files=frozen[1]))
    print(read(target))


if __name__=='__main__':main()
