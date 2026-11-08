"""새 성능 주장 없이 F1 우선·기존 v2의 차이와 명시적 실행 후보를 준비한다."""
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.competition_icing_profiles import apply_icing_profile
from src.submission_io import read_weather
from src.data_source import sha256_file as sha
from scripts.review_submission_bundle import verify_directory
from scripts.evaluate_objective_icing import read,write,now,verify_preserved,report,block_sensitivity

OUT=ROOT/'outputs/private/competition_profile_review_20261101_v1'
BUNDLE=ROOT/'outputs/private/submission_candidate_20261101_v10'


def main():
    if OUT.exists():raise FileExistsError('Preserve profile review')
    frozen=verify_preserved();verify_directory(BUNDLE)
    source=ROOT/'outputs/private/two_winter_models_20261024_v1/runtime_predictions.parquet'
    metadata=pd.read_parquet(source,columns=['station','group'])
    stations=sorted(metadata.loc[metadata.group.ne('competition'),'station'].unique())
    blocked={'12410','33411','23402','33402','33406','12213','23411'}
    assert len(stations)==9 and not set(stations)&blocked
    OUT.mkdir();plan=dict(winters=[['2024-11-01','2025-03-01'],['2025-11-01','2026-03-01']])
    write(OUT/'plan.json',dict(at_utc=now(),purpose='선택 목적의 명시. 이미 알려진 기준선의 실행 후보이며 신규 검증 성능 향상으로 주장하지 않음',
        source_sha256=sha(source),source_bundle_manifest_sha256=sha(BUNDLE/'manifest.json'),development_stations=stations,
        policy='ASOS air <= 0.0; preserve original v2 null mask; no fitted parameters',
        official_metric_priority_alternative=True,automatic_production_replacement=False,preservation=frozen,
        source_signatures={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'src/competition_icing_profiles.py',ROOT/'scripts/predict_competition_profile.py']}))
    frame=pd.read_parquet(source,columns=['station','time','group','winter','ice','asos_air_temp','physical_both'],filters=[('station','in',stations)]).sort_values(['station','time']).reset_index(drop=True)
    assert set(frame.station)==set(stations)
    frame['available']=frame.physical_both.notna()&frame.asos_air_temp.notna()
    frame['preserved_v2']=frame.physical_both.where(frame.available)
    frame['asos_zero']=np.where(frame.available,frame.asos_air_temp<=0,np.nan)
    frame.to_parquet(OUT/'development_comparison.parquet',index=False,compression='zstd')
    reports={};days={}
    for name in ['preserved_v2','asos_zero']:
        reports[name],days[name],events=report(frame,name,plan)
        days[name].to_csv(OUT/(name+'_daily.csv'),index=False,encoding='utf-8-sig')
        events.to_csv(OUT/(name+'_events.csv'),index=False,encoding='utf-8-sig')
    delta=block_sensitivity(days['asos_zero'],days['preserved_v2'],20261101)
    original=pd.read_csv(BUNDLE/'exports/protected_predictions_10min.csv',dtype={'station':str,'predicted_ice':'Int64'},parse_dates=['time'],float_precision='round_trip').sort_values(['station','time']).reset_index(drop=True)
    index=pd.read_csv(BUNDLE/'data/point_prediction_index.csv',dtype={'id':str,'prediction_group':str})
    records=read(BUNDLE/'data/prediction_group_manifest.json');parts=[];inputs={}
    for row in index.loc[index.kind.eq('protected')].itertuples():
        path=BUNDLE/'data/weather_groups'/(row.prediction_group+'.parquet')
        assert sha(path)==records[row.prediction_group]['weather_sha256']
        weather=pd.read_parquet(path);weather['station']=row.id;parts.append(weather);inputs[path.relative_to(BUNDLE).as_posix()]=sha(path)
    weather=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    assert len(weather)==len(original)==103680 and not {'ice','road_temp','state_raw'}&set(weather)
    score=apply_icing_profile(weather,original,'score_priority_asos_zero')
    assert int(score.predicted_ice.isna().sum())==int(original.predicted_ice.isna().sum())==18
    pd.testing.assert_series_equal(score.estimated_road_temp_c,original.estimated_road_temp_c,check_exact=True)
    pd.testing.assert_frame_equal(score[['station','time']],original[['station','time']],check_exact=True)
    score.to_csv(OUT/'protected_score_priority_predictions.csv.gz',index=False,encoding='utf-8-sig',compression={'method':'gzip','mtime':0})
    env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
    cli={}
    for profile in ['preserved_v2','score_priority_asos_zero']:
        output=OUT/(profile+'_example.csv')
        run=subprocess.run([sys.executable,'scripts/predict_competition_profile.py','--bundle',str(BUNDLE),
            '--input',str(BUNDLE/'data/weather_example.csv'),'--output',str(output),'--icing-profile',profile,
            '--output-start','2024-12-15','--output-end','2024-12-16'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600)
        (OUT/(profile+'_cli.log')).write_bytes(run.stdout);assert run.returncode==0,profile
        result=pd.read_csv(output,dtype={'station':str,'predicted_ice':'Int64'},parse_dates=['time'],float_precision='round_trip')
        expected=pd.read_csv(BUNDLE/'data/example_predictions.csv',dtype={'station':str,'predicted_ice':'Int64'},parse_dates=['time'],float_precision='round_trip')
        if profile=='preserved_v2':pd.testing.assert_frame_equal(result,expected,check_exact=True)
        else:
            example=read_weather(BUNDLE/'data/weather_example.csv');example['time']=pd.to_datetime(example.time)
            example=example.loc[example.time.ge('2024-12-15')&example.time.lt('2024-12-16')].reset_index(drop=True)
            expected=apply_icing_profile(example,expected,profile)
            for col in ['preserved_v2_predicted_ice']:result[col]=result[col].astype('Int64')
            pd.testing.assert_frame_equal(result,expected,check_exact=True)
        assert len(result)==144;cli[profile]=dict(rows_identical=len(result),sha256=sha(output))
    assert verify_preserved()==frozen;verify_directory(BUNDLE)
    write(OUT/'summary.json',dict(status='explicit_competition_profiles_verified',reports=reports,date_sensitivity=delta,
        cli=cli,protected_rows=len(score),protected_missing_rows_preserved=18,protected_labels_read=False,
        temperature_predictions_preserved=True,profile_changes_competition_prediction=True,production_default_changed=False,
        full_fit_or_threshold_search=False,new_independent_assessment=False,interpretation='이미 알려진 기준선의 선택 목적을 명시하며 신규 모델 개선과 구별',
        source_weather=inputs,preservation=frozen,files={p.name:sha(p) for p in OUT.iterdir() if p.is_file()}))
    print('PROFILES VERIFIED',{name:r['all']['f1_fixed_population'] for name,r in reports.items()},cli,flush=True)


if __name__=='__main__':main()
