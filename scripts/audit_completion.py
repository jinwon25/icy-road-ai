"""요청 범위의 완료 여부를 실제 결과와 대조한다. 산출물 존재만으로 완료를 주장하지 않는다."""
import json
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd
import geopandas as gpd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file
from src.frozen_assessment import verify_freeze


def main():
    private=ROOT/'outputs/private';frozen=verify_freeze(ROOT)
    paths={
        'baseline':'ice_fallback_logistic/summary.json',
        'development':'physical_ice_comparison/summary.json',
        'final':'frozen_assessment_v1/summary.json',
        'inference':'segment_inference_v1/audit.json',
        'map':'segment_condition_proposal/manifest.json',
        'chainage':'spatial/chainage_reference/summary.json',
        'anchors':'spatial/official_chainage_anchors/summary.json',
        'regularized':'regularized_forward/summary.json',
        'regularized_audit':'regularized_forward/audit.json',
        'surface_state':'surface_state_forward/summary.json',
        'surface_state_audit':'surface_state_forward/audit.json',
        'ensemble':'surface_state_ensemble/summary.json',
        'ensemble_audit':'surface_state_ensemble/audit.json',
        'estimated_temperature':'estimated_temperature_forward/summary.json',
        'estimated_temperature_audit':'estimated_temperature_forward/audit.json',
        'estimated_temperature_verification':'estimated_temperature_forward/verification.json',
        'state_v2':'surface_state_v2_forward/summary.json',
        'state_v2_audit':'surface_state_v2_forward/audit.json',
        'ensemble_v2':'surface_state_v2_ensemble/summary.json',
        'ensemble_v2_audit':'surface_state_v2_ensemble/audit.json',
        'ensemble_v2_verification':'surface_state_v2_ensemble/verification.json',
        'independent_catalog':'external/kma_rwis_reference/catalog_summary.json',
        'package':'submission_draft_v1/verification.json',
        'package_manifest':'submission_draft_v1/submission_manifest.json'}
    evidence={k:json.loads((private/p).read_text(encoding='utf-8')) for k,p in paths.items()}
    baseline=evidence['baseline']['slot_micro']
    candidate=evidence['development']['variants']['thermal_w20_daily']['slot_micro']
    columns=['station','time','ice']
    baseline_targets=pd.read_parquet(private/'ice_fallback_features/features.parquet',columns=columns).sort_values(['station','time']).reset_index(drop=True)
    candidate_targets=pd.read_parquet(private/'physical_features/features.parquet',columns=columns).sort_values(['station','time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(baseline_targets,candidate_targets,check_dtype=False)
    paired=baseline['n']==candidate['n']==int(baseline_targets.ice.notna().sum())==483629
    improved=paired and candidate['fp']<baseline['fp'] and candidate['fn']<baseline['fn']
    final=evidence['final'];inference=evidence['inference'];package=evidence['package']
    confirmation_path=private/'participant_confirmation_20261009.json'
    confirmation=json.loads(confirmation_path.read_text(encoding='utf-8')) if confirmation_path.exists() else {}
    participant_confirmed=(confirmation.get('personal_project_owner_confirmed') is True
        and bool(confirmation.get('confirmed_actions')) and confirmation.get('ai_support_retained') is True)
    external_path=private/'external/kma_rwis_development_v1/summary.json'
    external_development=json.loads(external_path.read_text(encoding='utf-8')) if external_path.exists() else None
    table=pd.read_csv(private/'segment_condition_proposal/segment_estimates_and_environment.csv')
    needed={'segment_id','temperature_cutoff_c','rain_history_hours','temperature_error_sensitivity_radius_c','bridge_overlap_2d_m','tunnel_overlap_2d_m','dsm_elevation_m','near_rwis_distance_km'}
    shapefile=gpd.read_file(private/'segment_condition_proposal/segment_conditions.shp')
    notebook=json.loads((ROOT/'notebooks/analysis_review.ipynb').read_text(encoding='utf-8'))
    receipt_path=private/'frozen_assessment_v1/predictions_receipt.json'
    receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
    started=json.loads((private/'frozen_assessment_v1/assessment_started.json').read_text(encoding='utf-8'))
    freeze_hash=sha256_file(private/'frozen_assessment_v1/freeze.json')
    prediction_hash=sha256_file(private/'frozen_assessment_v1/predictions.parquet')
    prediction_precedes_assessment=(receipt['protected_outcomes_loaded'] is False
        and receipt['freeze_sha256']==started['freeze_sha256']==final['freeze_sha256']==freeze_hash
        and receipt['predictions_sha256']==final['predictions_sha256']==prediction_hash
        and receipt_path.stat().st_mtime<=datetime.fromisoformat(started['opened_at_utc']).timestamp())
    requirements=[
        {'id':'official_rules','status':'partial','evidence':'Official problem/data/Q&A snapshots reviewed; unidentified daily-metric edges and final CSV schema remain.'},
        {'id':'corrected_release','status':'complete','evidence':{'release':'20261007','archive_sha256':frozen['archive_sha256']}},
        {'id':'development_fp_fn_improvement','status':'complete' if improved else 'unproven','evidence':{'same_valid_rows':paired,'baseline':baseline,'candidate_daily_policy':candidate,'scope':'14 development station LOSO, not final transfer performance'}},
        {'id':'protected_station_isolation','status':'complete' if prediction_precedes_assessment else 'unproven','evidence':{'frozen_files_verified':len(frozen['files']),'saved_prediction_hash_and_receipt_time_verified':prediction_precedes_assessment,'frozen_threshold':frozen['ice_threshold'],'no_post_assessment_retuning':final['threshold_changed_after_opening'] is False}},
        {'id':'temperature_assessment','status':'complete','evidence':final['temperature_station_macro']},
        {'id':'reliable_ice_detection','status':'contradicted' if final['ice_slot_micro']['tp']==0 else 'requires_quality_review','evidence':final['ice_slot_micro']},
        {'id':'segment_estimates_and_environment','status':'complete' if len(table)==467 and needed<=set(table) and inference['rows']==16139520 else 'unproven','evidence':{'segments':len(table),'rows':inference['rows'],'temperature_available':inference['temperature_available'],'scope':'geometric midpoint estimates, not official uniform chainage bins'}},
        {'id':'official_segment_geometry','status':'incomplete','evidence':{'official_chainage_confirmed':False,'direction_confirmed':False,'research_geometry_passes':evidence['chainage']['passes_geometry_checks'],'manual_review':evidence['chainage']['requires_manual_review'],'official_point_candidates':evidence['anchors']['unique_exact_name_candidates'],'official_point_qa_passes':evidence['anchors']['passes_anchor_qa']}},
        {'id':'risk_criteria_and_spatial_outputs','status':'partial','evidence':{'shapefile_segments':len(shapefile),'crs':str(shapefile.crs),'risk_grade_assigned':evidence['map']['risk_grade_assigned'],'criteria':'Temperature/moisture/facility/terrain proxies with sensitivity; validated Ice risk grades not achieved.'}},
        {'id':'reproducible_package','status':'complete','evidence':{'portable_demo_rows':package['portable_demo_rows'],'portable_notebook_cells':package['portable_notebook_code_cells'],'files_in_manifest':len(evidence['package_manifest']['files']),'saved_notebook_outputs':sum(bool(c.get('outputs')) for c in notebook['cells'])}},
        {'id':'participant_direct_contribution','status':'complete' if participant_confirmed else 'missing','evidence':{'confirmed':participant_confirmed,'participant_confirmation_record':confirmation,'old_package_confirmation_state':package['participant_contribution_confirmed'],'scope':'Personal project ownership and participant-reported actions; AI support remains attributed. This does not prove final model selection or submission review.'}},
        {'id':'award_or_operational_readiness','status':'not_achieved','evidence':'Frozen Ice F1=0; reference alignment and submission conditions incomplete.'}]
    report={'status':'goal_not_complete','client_review_date':'2026-10-09','requirements':requirements,
            'latest_development_comparison':{'scope':'repeated development space/winter transfer, not new independent final test',
                'metrics':evidence['ensemble_v2']['metrics'],
                'adoption_decision':evidence['ensemble_v2_verification']['adoption_decision'],
                'official_state_v2_metrics':evidence['state_v2']['metrics'],
                'previous_estimated_temperature_metrics':evidence['estimated_temperature']['metrics'],
                'previous_equal_weight_ensemble_metrics':evidence['ensemble']['metrics'],
                'prior_surface_state_metrics':evidence['surface_state']['metrics'],
                'models_reloaded':evidence['state_v2_audit']['models_reloaded'],
                'score_rows_recomputed':evidence['ensemble_v2_audit']['score_rows_recomputed'],
                'threshold_choices_reselected':evidence['ensemble_v2_audit']['threshold_choices_reselected']},
            'additional_independent_data':evidence['independent_catalog'],
            'external_first_winter_development':external_development,
            'participant_confirmation_sha256':sha256_file(confirmation_path) if confirmation_path.exists() else None,
            'evidence_sha256':{key:sha256_file(private/path) for key,path in paths.items()},
            'missing_or_contradicted':[r['id'] for r in requirements if r['status']!='complete'],
            'protected_outcomes_available_for_future_independent_tuning':False,
            'next_actions':['Confirm official chainage/direction reference and geometry anomalies.',
                            'Confirm unresolved organizer evaluation/submission definitions.',
                            'Reflect confirmed participant actions and AI support in the future reviewed submission package.',
                            'Any additional model claim requires new independent validation; do not tune to the opened three protected stations.']}
    out=private/'completion_audit_v1';out.mkdir(exist_ok=True)
    (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'requirements':len(requirements),'complete':sum(r['status']=='complete' for r in requirements),'remaining':report['missing_or_contradicted']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
