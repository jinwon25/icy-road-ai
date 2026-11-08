"""고정된 두 프로필을 보존하고 현재 생산 v2를 기본으로 하는 최종 제출 자산을 구성한다."""
from pathlib import Path
from datetime import datetime,timezone
import json,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import read,write,copy,sha
P=ROOT/'outputs/private';OUT=P/'final_release_assets_20261106_v14'

def main():
    if OUT.exists():raise FileExistsError('Preserve existing final release assets')
    fixed=P/'official_submission_tables_20261106_v14';r=read(fixed/'receipt.json')
    assert r['status']=='fixed_submission_observation_tables_verified'
    OUT.mkdir();(OUT/'exports').mkdir()
    f=pd.read_csv(fixed/'protected_observed_predictions_10min.csv',dtype={'station_id':str,'observed_surface_state':str,'observed_ice':'Int64','predicted_ice':'Int64','predicted_ice_preserved_v2':'Int64'},float_precision='round_trip')
    f['predicted_ice_asos_zero']=f.predicted_ice.copy()
    f['predicted_ice']=f.predicted_ice_preserved_v2.copy();f['icing_policy']='preserved_v2'
    f.to_csv(OUT/'exports/final_observed_predictions_10min.csv',index=False,encoding='utf-8-sig')
    f.to_parquet(OUT/'exports/final_observed_predictions_10min.parquet',index=False,compression='zstd')
    for name in ['protected_daily_metrics.csv','protected_station_metrics.csv']:
        table=pd.read_csv(fixed/name,dtype={'station':str},float_precision='round_trip')
        table.loc[table.profile.eq('preserved_v2')].to_csv(OUT/'exports'/name.replace('protected_','final_'),index=False,encoding='utf-8-sig')
        copy(fixed/name,OUT/'exports/comparison'/name)
    temp=pd.read_csv(fixed/'protected_temperature_metrics.csv',dtype={'station':str},float_precision='round_trip')
    values=temp.loc[temp.station.ne('pooled'),['bias','mae','rmse']].mean().to_dict()
    temp=pd.concat([temp,pd.DataFrame([dict(station='station_macro',scope='three_station_equal_weight_mean; n is total paired count',n=int(temp.loc[temp.station.ne('pooled'),'n'].sum()),**values)])],ignore_index=True)
    temp.to_csv(OUT/'exports/final_temperature_metrics.csv',index=False,encoding='utf-8-sig')
    copy(fixed/'column_dictionary.csv',OUT/'exports/column_dictionary.csv')
    p=P/'submission_candidate_20261101_v12/research/latest/competition_profile_review_20261101_v1'
    copy(p/'preserved_v2_example.csv',OUT/'final_example_predictions.csv')
    copy(p/'score_priority_asos_zero_example.csv',OUT/'score_priority_example_predictions.csv')
    plan=dict(package_label='v14',at_utc=datetime.now(timezone.utc).isoformat(),default_icing_profile='preserved_v2',
        alternative_icing_profile='score_priority_asos_zero',temperature_model_version='v3',
        decision='Retain the original production v2; report both pre-fixed profiles and development/final ordering reversal. No fitted weights or thresholds redesigned using protected outcomes.',
        user_preference_question_answered=False,user_account_approved='confirmed by user in this conversation; not independently queried',
        classification_model_changed=False,temperature_model_changed=False,selection_seal_sha256=sha(P/'final_selection_20261106_v14/selection_seal.json'),
        fixed_comparison_receipt_sha256=sha(fixed/'receipt.json'),fixed_profiles_assessed_before_release_default_documentation=True,
        claim='Local final fixed-prediction assessment, not official server score or unseen generalization guarantee',
        current_observation_comparison='exports/final_observed_predictions_10min.csv',
        official_rule_version='official_qa_20261106',submission_deadline_kst='2026-11-06T23:59:00+09:00',
        core_entrypoint='code/predict_final.py',current_notebook='notebooks/final_submission_review_v14.ipynb')
    write(OUT/'final_release_plan.json',plan)
    write(OUT/'metrics_summary.json',dict(profile='preserved_v2',primary=r['reports']['preserved_v2']['1'],strict_144=r['reports']['preserved_v2']['144'],
        comparison=r['reports']['score_priority_asos_zero'],temperature_station_macro=values,temperature= r['regression'],
        missing_observation_rows=r['missing_observation_rows'],prediction_na_rows=18,assessment_scope='fixed comparison after models were frozen'))
    official=read(P/'official_curl_review_20261106_v1/summary.json')
    write(OUT/'official_review_receipt.json',dict(status=official['status'],responses=official['responses'],detail_count=len(official['detail_comparisons']),
        checked_at_utc=official['checked_at_utc'],source_summary_sha256=sha(P/'official_curl_review_20261106_v1/summary.json'),
        application=official['application'],problem_tabs=official['tabs'],missing_previous_details=official['missing_previous_details'],
        updated_rules=['693 observed/predicted columns, no contemporaneous other-road state, exact times, normalized DEM',
            '716 no-ice station exclusion, false-alarm-only Recall, criterion rescaling/new proposal, ten-winter climate definitions']))
    write(OUT/'receipt.json',dict(status='final_release_assets_prepared',rows=len(f),default_profile='preserved_v2',
        source_receipt_sha256=sha(fixed/'receipt.json'),files={q.relative_to(OUT).as_posix():sha(q) for q in OUT.rglob('*') if q.is_file()}))
    print('FINAL RELEASE ASSETS PREPARED',len(f),'rows; default preserved_v2',flush=True)

if __name__=='__main__':main()