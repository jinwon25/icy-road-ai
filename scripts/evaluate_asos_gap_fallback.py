"""저장 ASOS 관측으로 공백을 보완하고 개발 인공 가림으로 입력 교체 영향을 검증한다."""
from datetime import datetime,timezone
from pathlib import Path
import sys
import joblib
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write,preservation
from src.data_source import sha256_file as sha
from src.method_blending import domain
from src.submission_runtime import FEATURES,WATER,infer
from src.asos_gap_fallback import AsosGapFallback,apply_weather_fallback

PRIVATE=ROOT/'outputs/private';SOURCE=PRIVATE/'releases/20261007/outputs/private'
OUT=PRIVATE/'asos_gap_fallback_20261016_v1';CANDIDATE=PRIVATE/'submission_candidate_20261016_v1'
MODEL_SOURCE=PRIVATE/'weather_memory_controls_20261013_v1'
CONFIG=ROOT/'config/asos_gap_fallback_experiment.json'
INPUT_COLUMNS=['station','time',*FEATURES,*[c for c in WATER if c not in FEATURES]]


def main():
    if OUT.exists():raise FileExistsError('Preserve completed gap experiment')
    frozen=preservation();plan=read(CONFIG);OUT.mkdir();write(OUT/'experiment_plan.json',plan|{'started_at_utc':datetime.now(timezone.utc).isoformat()})
    paths=[CONFIG,Path(__file__),ROOT/'src/asos_gap_fallback.py',SOURCE/'point_sources/asos.parquet',
        SOURCE/'point_sources/weather_coordinates.csv',SOURCE/'external/kma_rwis_reference/station_catalog.csv',
        PRIVATE/'weather_distance_20261010_v1/development_inputs.parquet',MODEL_SOURCE/'fit_receipts.json',
        PRIVATE/'candidate_coverage_review_20261014_v1/protected_prediction_missing_slots.csv',
        CANDIDATE/'data/point_prediction_index.csv',CANDIDATE/'data/prediction_group_manifest.json']
    observations=pd.read_parquet(paths[3],columns=['station','source_time','air_temp','snow_cm'])
    coordinates=pd.read_csv(paths[4],dtype={'station_id':str})
    coordinates=coordinates.loc[coordinates.kind.eq('ASOS'),['station_id','latitudes','longitudes']].rename(columns={'station_id':'station','latitudes':'lat','longitudes':'lon'})
    engine=AsosGapFallback(observations,coordinates,plan['maximum_distance_km'],plan['maximum_extra_distance_km'],plan['maximum_age_minutes'])
    groups=read(MODEL_SOURCE/'groups.json');population=set().union(*map(set,groups.values()))
    columns=[*INPUT_COLUMNS,'road_temp','asos_distance_km']
    master=domain(pd.read_parquet(paths[6],columns=columns));master=master.loc[master.station.isin(population)].copy()
    slot=master.time.dt.strftime('%H:%M').isin(plan['synthetic_mask_target_slots'])
    samples=master.loc[master.time.dt.day.isin(plan['synthetic_mask_days'])&slot].sort_values(['station','time']).reset_index(drop=True)
    catalogue=pd.read_csv(paths[5],dtype={'station':str},usecols=['station','lat','lon']).set_index('station')
    receipts=read(paths[7]);registry={(r['candidate'],tuple(r['excluded_groups'])):r for r in receipts}
    validation_parts=[];selections=[];statistics=[];cutoffs=plan['quality_gate']
    for station,part in samples.groupby('station'):
        part=part.reset_index(drop=True);point={'station':station,**catalogue.loc[station,['lat','lon']].to_dict()}
        primary=engine.select(point,part.time).primary_asos_station.iloc[0]
        selected=engine.select(point,part.time,exclude=[primary]);selected['excluded_primary']=True
        masked=part[INPUT_COLUMNS+['asos_distance_km']].copy()
        masked[['asos_air_temp','asos_age_minutes','asos_snow_cm']]=np.nan
        altered,replaced=apply_weather_fallback(masked,selected)
        group=next(g for g,ids in groups.items() if station in ids)
        models=[]
        for name in ['nohistory12_mse300','nohistory12_mae300']:
            record=registry[(name,(group,))];path=MODEL_SOURCE/record['model_path'];paths.append(path)
            assert sha(path)==record['model_sha256'] and station not in record['training_stations']
            models.append(joblib.load(path))
        original=infer(part[INPUT_COLUMNS],models);proposal=infer(altered[INPUT_COLUMNS],models)
        result=part[['station','time','road_temp']].copy()
        result['original_temperature']=original.estimated_road_temp_c
        result['fallback_temperature']=proposal.estimated_road_temp_c;result['weather_replaced']=replaced
        paired=np.isfinite(result.road_temp)&np.isfinite(result.original_temperature)&np.isfinite(result.fallback_temperature)
        n=int(paired.sum());coverage=float(replaced.mean())
        base_mae=float((result.loc[paired,'original_temperature']-result.loc[paired,'road_temp']).abs().mean()) if n else None
        fallback_mae=float((result.loc[paired,'fallback_temperature']-result.loc[paired,'road_temp']).abs().mean()) if n else None
        change=float((result.loc[paired,'fallback_temperature']-result.loc[paired,'original_temperature']).abs().mean()) if n else None
        gate=bool(n>=cutoffs['minimum_paired_temperature_rows_each_station'] and coverage>=cutoffs['minimum_available_fraction_each_station']
            and fallback_mae<=base_mae*(1+cutoffs['maximum_station_mae_relative_harm'])+1e-12
            and change<=cutoffs['maximum_station_mean_temperature_change_celsius'])
        statistics.append(dict(station=station,rows=len(part),available_fallback_rows=int(replaced.sum()),paired_temperature_rows=n,
            available_fraction=coverage,original_mae=base_mae,fallback_mae=fallback_mae,mean_absolute_temperature_change=change,quality_passed=gate))
        validation_parts.append(result);selections.append(selected)
        print(station,'available',int(replaced.sum()),'/',len(part),'MAE',base_mae,fallback_mae,'gate',gate,flush=True)
    pd.concat(validation_parts,ignore_index=True).to_parquet(OUT/'masked_validation_predictions.parquet',index=False)
    pd.concat(selections,ignore_index=True).to_parquet(OUT/'masked_weather_selections.parquet',index=False)
    pd.DataFrame(statistics).to_csv(OUT/'masked_station_metrics.csv',index=False)
    # 보호측은 예측 공백·위치·기상만 읽는다. 노면온도/상태 정답 파일은 접근하지 않는다.
    missing=pd.read_csv(paths[8],dtype={'station':str},parse_dates=['time'],usecols=['station','time'])
    index=pd.read_csv(paths[9],dtype={'id':str});manifest=read(paths[10]);point_rows=[];input_rows=[]
    for (station,winter),times in missing.assign(winter=np.where(missing.time.dt.month.ge(11),missing.time.dt.year,missing.time.dt.year-1)).groupby(['station','winter']):
        metadata=index.loc[index.kind.eq('protected')&index.id.eq(station)&index.winter.eq(winter)]
        assert len(metadata)==1;r=metadata.iloc[0];path=CANDIDATE/'data/weather_groups'/(r.prediction_group+'.parquet');paths.append(path)
        weather=pd.read_parquet(path,columns=INPUT_COLUMNS).loc[lambda f:f.time.isin(times.time)].sort_values('time').reset_index(drop=True)
        weather['station']=station;assert len(weather)==len(times)
        point={'station':station,'lat':float(r.point_lat),'lon':float(r.point_lon)}
        selected=engine.select(point,weather.time)
        assert selected.primary_asos_station.eq(str(manifest[r.prediction_group]['asos_station'])).all()
        proposal,replaced=apply_weather_fallback(weather,selected)
        selected['weather_replaced']=replaced;point_rows.append(selected);input_rows.append(proposal)
    inputs=pd.concat(input_rows,ignore_index=True);selected=pd.concat(point_rows,ignore_index=True)
    active_models=[]
    for name in ['weather12_mse300','weather12_mae300']:
        path=CANDIDATE/'model'/(name+'.joblib');paths.append(path);active_models.append(joblib.load(path))
    predictions=infer(inputs[INPUT_COLUMNS],active_models)
    assert len(predictions)==18
    predictions.to_csv(OUT/'protected_gap_reference_predictions.csv',index=False,encoding='utf-8-sig',na_rep='')
    inputs.to_parquet(OUT/'protected_gap_reference_inputs.parquet',index=False)
    selected.to_parquet(OUT/'protected_weather_selections.parquet',index=False)
    for table in selections+[selected]:
        have=table.selected_asos_station.notna()
        assert (table.loc[have,'source_time']<table.loc[have,'time']).all()
        assert table.loc[have,'age_minutes'].gt(0).all() and table.loc[have,'age_minutes'].le(60).all()
    paths=list(dict.fromkeys(paths));write(OUT/'input_signatures.json',{str(p.relative_to(ROOT)):sha(p) for p in paths})
    assert preservation()==frozen
    result=dict(status='asos_gap_fallback_study_complete',finished_at_utc=datetime.now(timezone.utc).isoformat(),
        masked_validation_rows=len(samples),masked_validation_stations=len(statistics),masked_station_results=statistics,
        all_station_quality_gates_passed=all(r['quality_passed'] for r in statistics),
        original_protected_missing_rows=18,reference_temperature_available=int(predictions.estimated_road_temp_c.notna().sum()),
        reference_binary_available=int(predictions.predicted_ice.notna().sum()),reference_still_missing=int(predictions.predicted_ice.isna().sum()),
        reference_predictions_only=True,execution_candidate_changed=False,protected_or_opened_outcomes_read=False,
        new_model_fits=0,network_requests=0,execution_candidate_archive_sha256=sha(CANDIDATE.with_suffix('.zip')),
        old_frozen_files=frozen[0],reserved_frozen_files=frozen[1],files={p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file()})
    write(OUT/'summary.json',result);print({k:v for k,v in result.items() if k not in ['masked_station_results','files']},flush=True)


if __name__=='__main__':main()
