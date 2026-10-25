"""선택·감사가 끝난 확장 모델의 새 제출 폴더를 구성한다. v2는 보존한다."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import sys
import joblib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.submission_runtime import FEATURES
from src.thermal_runtime import EXTRA
from src.extended_runtime import infer
from src.solar_thermal_runtime import temperature_predictors
from src.offline_runtime import deny_network
from scripts.evaluate_method_blending import preservation

PRIVATE=ROOT/'outputs/private';OLD=PRIVATE/'submission_candidate_20261024_v2';OUT=PRIVATE/'submission_candidate_20261024_v3'


def read(p):return json.loads(p.read_text('utf-8'))
def write(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
def copy(source,target):target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)


def manifest():
    files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in OUT.rglob('*')
        if p.is_file() and p!=OUT/'manifest.json' and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    write(OUT/'manifest.json',dict(version=7,status='private_extended_candidate',development_scope='extended_two_winter',
        created_at_utc=datetime.now(timezone.utc).isoformat(),files=files,independent_performance_qualified=False,competition_submitted=False))


def prepare(selection_path):
    if OUT.exists():raise FileExistsError('New candidate directory required')
    selected=read(selection_path)
    assert selected['status']=='audited_final_selection' and selected['icing_policy']=='preserve_v2'
    assert all(selected['temperature_report']['gates'].values())
    frozen=preservation();oldmanifest=read(OLD/'manifest.json')['files'];OUT.mkdir()
    def old(name):
        source=OLD/name;assert sha(source)==oldmanifest[name]['sha256'];copy(source,OUT/name)
    for name in ['requirements.txt','requirements-notebook.txt','code/export_predictions.py','data/point_prediction_index.csv',
                 'data/segment_candidate_summary.csv','data/condition_evidence_criteria.csv','data/training_weather_temperature.parquet']:
        old(name)
    for name in oldmanifest:
        if name.startswith('figures/'):old(name)
    for source in (ROOT/'src').glob('*.py'):copy(source,OUT/'src'/source.name)
    copy(ROOT/'pytest.ini',OUT/'pytest.ini')
    for source in ROOT.glob('requirements*.txt'):copy(source,OUT/'research/environment'/source.name)
    for directory,pattern in [('scripts','*.py'),('config','*.json'),('tests','*.py')]:
        for source in (ROOT/directory).glob(pattern):copy(source,OUT/directory/source.name)
    for source in (ROOT/'docs').rglob('*.md'):copy(source,OUT/source.relative_to(ROOT))
    for name in ['check_notebook.py','export_extended_delivery_tables.py']:
        copy(ROOT/'scripts'/name,OUT/'scripts'/name)
    copy(ROOT/'scripts/train_extended_submission.py',OUT/'code/train.py')
    copy(ROOT/'scripts/predict_extended_submission.py',OUT/'code/predict.py')
    for name in ['AI_USAGE.md','docs/research/OPEN_SOURCE_REVIEW_20261024.md','docs/research/EXTENDED_SEARCH_20261024.md',
                 'docs/delivery/CSV_CONTRACT.md','docs/validation/VALIDATION_PROTOCOL.md','config/extended_final_selection_20261024.json']:
        copy(ROOT/name,OUT/name)
    for source in (PRIVATE/'research_license_inventory_20261024_v1').rglob('*'):
        if source.is_file():copy(source,OUT/'licenses'/source.relative_to(PRIVATE/'research_license_inventory_20261024_v1'))
    runtime_licenses=PRIVATE/'runtime_license_inventory_20261024_v1'
    for source in runtime_licenses.rglob('*'):
        if source.is_file():copy(source,OUT/'licenses/runtime'/source.relative_to(runtime_licenses))
    copy(PRIVATE/'terrain_thermal_data_20261024_v1/COPERNICUS_NOTICE.txt',OUT/'licenses/COPERNICUS_NOTICE.txt')
    copy(PRIVATE/'releases/20261007/outputs/private/external/copernicus_dem/eula_F.pdf',OUT/'licenses/Copernicus_GLO30_EULA.pdf')
    source=PRIVATE/'solar_memory_data_20261024_v1/development.parquet'
    sourceplan=read(PRIVATE/'solar_memory_search_20261024_v1/plan.json');assert sha(source)==sourceplan['signatures']['data']
    columns=list(dict.fromkeys(['station','time','road_temp',*FEATURES,*EXTRA,'asos_solar_altitude_deg','asos_solar_sine_positive']))
    raw=pd.read_parquet(source,columns=columns).sort_values(['station','time']).reset_index(drop=True)
    assert len(raw)==794545 and not set(raw.station)&{'12410','33411','23402'}
    x,valid,_=temperature_predictors(raw.drop(columns='road_temp'),'combined_asos_solar')
    assert int((valid&raw.road_temp.notna()).sum())==793149
    target=OUT/'data/training_extended_temperature.parquet';raw.to_parquet(target,index=False,compression='zstd')
    models=[]
    for component in selected['components']:
        folder=ROOT/component['folder'];report=read(folder/'report.json');fit=report['fits'][0]
        assert sha(folder/'predictions.parquet')==component['predictions_sha256']
        params=dict(fit['parameters']);params['warm_start']=False
        models.append(dict(name=component['name'],role='temperature',parameters=params,features=fit['features'],training_rows=793149))
        copy(folder/'report.json',OUT/'research/extended/components'/(component['name']+'_report.json'))
        copy(folder/'predictions.parquet',OUT/'research/extended/components'/(component['name']+'_predictions.parquet'))
    for fit in read(OLD/'model/fit_receipts.json'):
        models.append(dict(name=fit['name'],role='icing_reference',parameters=fit['parameters'],features=fit['features'],training_rows=793149,
            reference_model_sha256=fit['model_sha256']))
    plan=dict(allowed_stations=sorted(raw.station.unique()),periods=[['2024-11-01','2025-03-01'],['2025-11-01','2026-03-01']],
        training_sources=dict(temperature=dict(file='data/training_extended_temperature.parquet',sha256=sha(target)),
            icing_reference=dict(file='data/training_weather_temperature.parquet',sha256=sha(OUT/'data/training_weather_temperature.parquet'))),
        raw_temperature_rows=len(raw),valid_training_pairs=793149,temperature_input_available_rows=int(valid.sum()),
        temperature_feature_kind='combined_asos_solar',temperature_weights=selected['weights'],models=models,
        second_winter_training=True,protected_outcomes_used=False,new_independent_assessment=False,selection_sha256=sha(selection_path))
    write(OUT/'extended_training_plan.json',plan);copy(selection_path,OUT/'research/extended/selection.json')
    basepath=PRIVATE/'two_winter_models_20261024_v1/runtime_predictions.parquet';audit=read(basepath.parent/'audit_runtime.json')
    assert sha(basepath)==audit['runtime_prediction_sha256'];f=pd.read_parquet(basepath)
    predictions=[]
    for component in selected['components']:
        candidate=pd.read_parquet(ROOT/component['folder']/'predictions.parquet')
        pd.testing.assert_frame_equal(candidate[['station','time']],f[['station','time']]);predictions.append(candidate.prediction.to_numpy())
    f['temperature_v2']=f.temperature_both;f['temperature_both']=np.asarray(selected['weights'])@np.stack(predictions)
    f.to_parquet(OUT/'research/extended/audited_predictions.parquet',index=False,compression='zstd')
    audit=dict(status='extended_temperature_and_preserved_v2_icing',physical=audit['physical'],temperature=selected['temperature_report'],
        runtime_prediction_sha256=sha(OUT/'research/extended/audited_predictions.parquet'),baseline_sha256=sha(basepath),protected_outcomes_used=False,new_independent_assessment=False)
    write(OUT/'research/extended/audit.json',audit)
    weather=PRIVATE/'solar_delivery_inputs_20261024_v1';inputs=read(weather/'receipt.json');groups=read(OLD/'data/prediction_group_manifest.json')
    for group,record in inputs['groups'].items():
        source=weather/'weather_groups'/(group+'.parquet');assert sha(source)==record['weather_sha256']
        copy(source,OUT/'data/weather_groups'/source.name);groups[group]=dict(groups[group],**record)
        groups[group].pop('predictions_sha256',None)
    write(OUT/'data/prediction_group_manifest.json',groups);copy(weather/'receipt.json',OUT/'validation/weather_input_receipt.json')
    example=raw.loc[raw.station.eq('12207')&raw.time.ge('2024-12-14T12:00:00')&raw.time.lt('2024-12-16')].drop(columns='road_temp')
    assert len(example)==216;example.to_csv(OUT/'data/weather_example.csv',index=False,encoding='utf-8-sig')
    for name in ['thermal_runtime_feature_audit_20261024_v1','combined_runtime_feature_audit_20261024_v1','solar_runtime_feature_audit_20261024_v1',
                 'canonical_thermal_input_audit_20261024_v1','extended_ice_rules_audit_20261024_v1']:
        for source in (PRIVATE/name).glob('*.json'):copy(source,OUT/'validation/research_audits'/name/source.name)
    assert preservation()==frozen
    write(OUT/'validation/preparation.json',dict(status='new_extended_bundle_prepared',raw_rows=len(raw),valid_training_pairs=793149,
        input_available_rows=int(valid.sum()),source_zip_sha256=sha(OLD.with_suffix('.zip')),protected_outcomes_read=False,old_frozen_files=frozen[0],reserved_frozen_files=frozen[1]))
    manifest();print('새 제출 후보 입력·코드 준비 완료',len(models),flush=True)


def predict():
    marker=OUT/'validation/extended_inference.json'
    if marker.exists():raise FileExistsError('Preserve completed inference')
    frozen=preservation();plan=read(OUT/'extended_training_plan.json');receipts=read(OUT/'model/refit_receipt.json');hashes={r['name']:r['sha256'] for r in receipts['models']}
    models={'temperature':[],'icing_reference':[]}
    for spec in plan['models']:
        path=OUT/'model'/(spec['name']+'.joblib');assert sha(path)==hashes[spec['name']]
        if spec['role']=='icing_reference':assert sha(path)==spec['reference_model_sha256']
        models[spec['role']].append(joblib.load(path))
    groups=read(OUT/'data/prediction_group_manifest.json');index=pd.read_csv(OUT/'data/point_prediction_index.csv',dtype={'id':str,'prediction_group':str})
    summary=pd.read_csv(OUT/'data/segment_candidate_summary.csv',dtype={'seg_id':str,'prediction_group':str},float_precision='round_trip');protected=[];total=0
    (OUT/'data/prediction_groups').mkdir(exist_ok=True)
    with deny_network() as attempts:
        for group,record in groups.items():
            path=OUT/'data/weather_groups'/(group+'.parquet');assert sha(path)==record['weather_sha256']
            weather=pd.read_parquet(path);result=infer(weather,models['temperature'],models['icing_reference'],plan['temperature_feature_kind'],plan['temperature_weights'])
            old=pd.read_parquet(OLD/'data/prediction_groups'/(group+'.parquet'))
            pd.testing.assert_series_equal(result.predicted_ice,old.predicted_ice,check_exact=True)
            pd.testing.assert_series_equal(result.icing_reference_temperature_c,old.estimated_road_temp_c,check_names=False,check_exact=True)
            for c in ['condition_evidence','temperature_status','moisture_status','aws_status']:pd.testing.assert_series_equal(result[c],old[c],check_exact=True)
            predpath=OUT/'data/prediction_groups'/(group+'.parquet');result.to_parquet(predpath,index=False,compression='zstd');record['predictions_sha256']=sha(predpath)
            for point in index.loc[index.kind.eq('protected')&index.prediction_group.eq(group)].itertuples():
                p=result.copy();p.station=point.id;p['winter']=point.winter;protected.append(p)
            good=result.predicted_ice.notna();positive=result.predicted_ice.eq(1).fillna(False)
            updates=dict(temperature_valid_slots=int(result.estimated_road_temp_c.notna().sum()),ice_valid_slots=int(good.sum()),
                cold_wet_slots=int(positive.sum()),cold_wet_hours=float(positive.sum()/6),cold_wet_fraction=float(positive.sum()/good.sum()),
                consensus_slots=int(result.condition_evidence.eq('cold_wet_consensus').sum()),disagreement_slots=int(result.condition_evidence.eq('cold_wet_disagreement').sum()),
                estimated_temp_mean_c=float(result.estimated_road_temp_c.mean()))
            for key,value in updates.items():summary.loc[summary.prediction_group.eq(group),key]=value
            total+=len(result)
            if total%(17280*20)==0:print('확장 모델 전체 추론',total,flush=True)
    assert not attempts
    p=pd.concat(protected,ignore_index=True).sort_values(['station','time']);assert len(p)==103680 and not p.duplicated(['station','time']).any()
    assert p.predicted_ice.isna().sum()==18;p.to_csv(OUT/'data/protected_predictions_10min.csv.gz',index=False,encoding='utf-8-sig',compression='gzip')
    summary.to_csv(OUT/'data/segment_candidate_summary.csv',index=False,encoding='utf-8-sig');write(OUT/'data/prediction_group_manifest.json',groups)
    assert preservation()==frozen
    write(marker,dict(status='extended_inference_verified',groups=len(groups),group_rows=total,protected_rows=len(p),protected_missing=18,
        icing_predictions_and_reference_temperatures_exactly_preserved=True,protected_outcomes_read=False,network_attempts=0))
    manifest()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True,choices=['prepare','predict','manifest']);p.add_argument('--selection',type=Path)
    a=p.parse_args()
    if a.stage=='prepare':prepare(a.selection)
    else:globals()[a.stage]()
