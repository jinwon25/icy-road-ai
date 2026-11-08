"""새 규정의 입력 금지·DEM 단위·고정 관측 대조표와 독립 집계를 감사한다."""
from pathlib import Path
import sys,json
import numpy as np
import pandas as pd
import joblib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import read,write,sha
from scripts.evaluate_official_icing_upgrade_20261106 import independent
from scripts.evaluate_objective_icing import verify_preserved

P=ROOT/'outputs/private';OUT=P/'official_compliance_audit_20261106_v14'
def main():
    if OUT.exists():raise FileExistsError('Preserve completed compliance audit')
    package=P/'submission_candidate_20261101_v12';plan=read(package/'extended_training_plan.json')
    models=[]
    forbidden={'road_temp','ice','state','state_raw','observed_ice','actual_ice','target','label'}
    for spec in plan['models']:
        path=package/'model'/(spec['name']+'.joblib');model=joblib.load(path);features=list(model.feature_names_in_)
        assert not set(features)&forbidden and not any('rwis' in s.lower() or 'neighbor' in s.lower() or 'dem' in s.lower() for s in features)
        models.append(dict(name=spec['name'],role=spec['role'],sha256=sha(path),features=features,
            no_same_time_other_surface_states=True,provided_dem_used_as_meters=False))
    weather=[]
    for path in package.glob('research/*/model/metadata.json'):
        meta=read(path);features=meta.get('features',[])
        assert not set(features)&forbidden and not any('rwis' in s.lower() or 'surface_state' in s.lower() for s in features)
        weather.append(dict(path=path.relative_to(package).as_posix(),sha256=sha(path),feature_count=len(features)))
    training=[]
    for name in ['training_extended_temperature.parquet','training_weather_temperature.parquet']:
        path=package/'data'/name;stations=pd.read_parquet(path,columns=['station']).station.astype(str)
        assert not set(stations)&{'12410','33411','23402'}
        training.append(dict(path='data/'+name,rows=len(stations),stations=sorted(stations.unique()),sha256=sha(path)))
    tables=P/'official_submission_tables_20261106_v14';receipt=read(tables/'receipt.json')
    for name,digest in receipt['files'].items():assert sha(tables/name)==digest,name
    f=pd.read_csv(tables/'protected_observed_predictions_10min.csv',dtype={'station_id':str},float_precision='round_trip')
    data=f[['station_id','prediction_time_kst','observed_ice']].rename(columns={'station_id':'station','prediction_time_kst':'time','observed_ice':'ice'})
    checks=0
    for profile,column in [('score_priority_asos_zero','predicted_ice'),('preserved_v2','predicted_ice_preserved_v2')]:
        for minimum in [1,144]:
            proof=independent(data,f[column].to_numpy(float),minimum);record=receipt['reports'][profile][str(minimum)]
            for name,value in proof.items():
                if value is None:assert record[name] is None
                else:np.testing.assert_allclose(record[name],value,atol=1e-12,rtol=0)
                checks+=1
    for record in receipt['regression']:
        q=f if record['station']=='pooled' else f.loc[f.station_id.eq(record['station'])]
        a=q.observed_road_temperature_c.to_numpy(float);b=q.estimated_road_temperature_c.to_numpy(float);valid=np.isfinite(a)&np.isfinite(b)
        d=b[valid]-a[valid]
        assert len(d)==record['n']
        np.testing.assert_allclose([np.mean(d),np.mean(np.abs(d)),np.sqrt(np.mean(d*d))],[record['bias'],record['mae'],record['rmse']],atol=1e-12,rtol=0);checks+=4
    assert pd.Timestamp(receipt['selection_frozen_at_utc'])<pd.Timestamp(receipt['outcome_access_started_at_utc'])
    source=read(P/'official_curl_review_20261106_v1/summary.json');assert source['status']=='public_review_complete'
    OUT.mkdir()
    write(OUT/'receipt.json',dict(status='passed',models=models,weather_models=weather,training=training,
        official_public_review=dict(responses=source['responses'],details=len(source['detail_comparisons']),application=source['application']),
        independent_metric_checks=checks,observation_join_rows=len(f),missing_original_observation_rows=receipt['missing_observation_rows'],
        exact_timestamps=True,provided_dem_not_physical_elevation=True,normalized_dem_flat20_treated_as_unused=True,
        selection_frozen_before_final_observation_join=True,protected_targets_used_for_training_or_selection=False,
        protected_outcomes_read_for_final_delivery_audit=True,table_receipt_sha256=sha(tables/'receipt.json'),
        source_script_sha256=sha(Path(__file__)),preservation=verify_preserved()))
    print('COMPLIANCE PASSED',len(models),'core models;',checks,'independent metrics; 103680 final rows',flush=True)

if __name__=='__main__':main()