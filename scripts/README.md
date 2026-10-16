# 실행 스크립트 안내

모든 명령은 저장소 루트에서 실행합니다. 단계 간 import·작업 루트 계산·봉인 기록을 보존하기 위해 기존 Python 파일 위치와 명령은 유지합니다.

[현재 현황](../docs/STATUS.md) · [실행 안내](../docs/delivery/RUNBOOK.md) · [설정 안내](../config/README.md)

## 자주 찾는 진입점

| 목적 | 파일 |
| --- | --- |
| 코드·노트북 출력·인증정보 검사 | [check_repository.py](check_repository.py) |
| GFM 렌더·링크·앵커 검사 | [check_markdown.py](check_markdown.py) |
| 현재 후보 보고서 작성 | [build_revised_submission_report.py](build_revised_submission_report.py) |
| 최신 보고서 후보 묶기 | [package_model_report_upgrade.py](package_model_report_upgrade.py) |
| 현재 2모델 평균 후보의 CSV·Parquet 추론 | [submission_runtime.py](../src/submission_runtime.py) |
| 제출 ZIP 해시 검증·새 폴더 복원 | [submission_archive.py](../src/submission_archive.py) |
| 과거 Ridge·HGB 기준선 데모 | [demo_inference.py](demo_inference.py) |
| 데이터 버전별 작업 복사본 | [prepare_release_workspace.py](prepare_release_workspace.py) |

학습·공식 사이트 수집·패키징은 출력 경로와 선행 조건을 확인한 뒤 실행합니다. 현재 후보 묶음과 이미 완료한 평가를 덮어쓰지 않습니다. 수정본 연구는 별도 작업 루트의 실행 안내를 따릅니다.

현재 후보를 저장소에서 실행하려면 ZIP의 해시 목록을 확인해 새 폴더로 복원한 뒤 그 폴더의 모델을 명시합니다. 원본 저장소에는 모델이 포함되지 않습니다.

```powershell
python -m src.submission_archive --archive outputs/private/submission_candidate_20261016_v1.zip --output outputs/private/candidate_work_20261016
python -m src.submission_runtime --input outputs/private/candidate_work_20261016/data/weather_example.csv --models outputs/private/candidate_work_20261016/model --output outputs/private/new_candidate_prediction.csv
```

복원 경로·예측 경로가 이미 존재하면 중단합니다. 예제는 현재 학습 모델의 실행 확인용이며 새 지점 성능 평가가 아닙니다. [기준선·재현성 후속 검토](../docs/delivery/REVIEW_RESPONSE_20261016.md)

## 전체 스크립트 목록

파일명의 기능을 기준으로 찾기 쉽게 묶었습니다. 현재 후보에서 직접 쓰는 파일과 과거 실험 파일을 모두 포함합니다.

<details>
<summary>검증 · 13개</summary>

- [check_blending_quality.py](check_blending_quality.py)
- [check_ice_methodology_quality.py](check_ice_methodology_quality.py)
- [check_markdown.py](check_markdown.py)
- [check_model_report_quality.py](check_model_report_quality.py)
- [check_notebook.py](check_notebook.py)
- [check_official_updates_20261013.py](check_official_updates_20261013.py)
- [check_qa633_quality.py](check_qa633_quality.py)
- [check_repository.py](check_repository.py)
- [check_submission_candidate_quality.py](check_submission_candidate_quality.py)
- [check_weather_memory_control_quality.py](check_weather_memory_control_quality.py)
- [check_weather_memory_quality.py](check_weather_memory_quality.py)
- [verify_offline_inference_20261013.py](verify_offline_inference_20261013.py)
- [verify_submission_candidate_demo.py](verify_submission_candidate_demo.py)

</details>

<details>
<summary>제출 · 22개</summary>

- [analyze_submission_failure_modes.py](analyze_submission_failure_modes.py)
- [audit_submission_candidate.py](audit_submission_candidate.py)
- [audit_submission_diagnostics.py](audit_submission_diagnostics.py)
- [build_demo_video.py](build_demo_video.py)
- [build_research_delivery.py](build_research_delivery.py)
- [build_revised_submission_report.py](build_revised_submission_report.py)
- [build_submission_candidate_demo.py](build_submission_candidate_demo.py)
- [build_submission_draft.py](build_submission_draft.py)
- [complete_submission_candidate_materials.py](complete_submission_candidate_materials.py)
- [demo_inference.py](demo_inference.py)
- [finalize_submission_candidate.py](finalize_submission_candidate.py)
- [fix_submission_candidate_csv_io.py](fix_submission_candidate_csv_io.py)
- [infer_submission_candidate_spatial.py](infer_submission_candidate_spatial.py)
- [package_current_candidate_review_20261014.py](package_current_candidate_review_20261014.py)
- [package_model_report_upgrade.py](package_model_report_upgrade.py)
- [prepare_submission_candidate.py](prepare_submission_candidate.py)
- [record_submission_candidate_demo.py](record_submission_candidate_demo.py)
- [render_submission_candidate_report.py](render_submission_candidate_report.py)
- [repair_submission_candidate_delivery.py](repair_submission_candidate_delivery.py)
- [reproduce_freezing_delivery.py](reproduce_freezing_delivery.py)
- [reproduce_research_delivery.py](reproduce_research_delivery.py)
- [research_report_upgrade_20261014.py](research_report_upgrade_20261014.py)

</details>

<details>
<summary>공식정보 · 18개</summary>

- [audit_official_chainage_anchors.py](audit_official_chainage_anchors.py)
- [audit_official_nodelink_geometry.py](audit_official_nodelink_geometry.py)
- [audit_qa633_development.py](audit_qa633_development.py)
- [build_official_directed_segment_candidates.py](build_official_directed_segment_candidates.py)
- [build_official_requirements_20261013.py](build_official_requirements_20261013.py)
- [compare_official_answers_20261013.py](compare_official_answers_20261013.py)
- [complete_official_qna_review.py](complete_official_qna_review.py)
- [complete_official_requirements_20261014.py](complete_official_requirements_20261014.py)
- [evaluate_qa633_development.py](evaluate_qa633_development.py)
- [fetch_official_details_20261013.py](fetch_official_details_20261013.py)
- [inspect_official_changes_20261014.py](inspect_official_changes_20261014.py)
- [inspect_official_updates_20261013.py](inspect_official_updates_20261013.py)
- [inspect_qa633_followup_inputs.py](inspect_qa633_followup_inputs.py)
- [inspect_qa633_results.py](inspect_qa633_results.py)
- [plot_qa633_review.py](plot_qa633_review.py)
- [review_official_answers_20261013.py](review_official_answers_20261013.py)
- [review_official_updates_20261013.py](review_official_updates_20261013.py)
- [review_official_updates_20261014.py](review_official_updates_20261014.py)

</details>

<details>
<summary>데이터준비 · 29개</summary>

- [build_aws_fallback_features.py](build_aws_fallback_features.py)
- [build_environment_features.py](build_environment_features.py)
- [build_fog_features.py](build_fog_features.py)
- [build_ice_features.py](build_ice_features.py)
- [build_kma_external_development_features.py](build_kma_external_development_features.py)
- [build_moisture_memory.py](build_moisture_memory.py)
- [build_offline_review_bundle_20261013.py](build_offline_review_bundle_20261013.py)
- [build_physical_features.py](build_physical_features.py)
- [build_road_segment_scaffold.py](build_road_segment_scaffold.py)
- [build_route_facility_features.py](build_route_facility_features.py)
- [build_segment_environment_inventory.py](build_segment_environment_inventory.py)
- [build_segment_exposure.py](build_segment_exposure.py)
- [build_solar_terrain_features.py](build_solar_terrain_features.py)
- [build_static_station_features.py](build_static_station_features.py)
- [build_weather_control_bundle.py](build_weather_control_bundle.py)
- [build_weather_features.py](build_weather_features.py)
- [build_weather_memory_bundle.py](build_weather_memory_bundle.py)
- [build_weather_memory_stable_bundle.py](build_weather_memory_stable_bundle.py)
- [cache_point_sources.py](cache_point_sources.py)
- [download_kma_external_development.py](download_kma_external_development.py)
- [download_kma_external_reserved.py](download_kma_external_reserved.py)
- [fetch_copernicus_dem.py](fetch_copernicus_dem.py)
- [fetch_ice_practice_references.py](fetch_ice_practice_references.py)
- [fetch_power_radiation.py](fetch_power_radiation.py)
- [fetch_spatial_blending_reference.py](fetch_spatial_blending_reference.py)
- [make_splits.py](make_splits.py)
- [make_variable_dictionary.py](make_variable_dictionary.py)
- [precompute_external_development_inputs.py](precompute_external_development_inputs.py)
- [prepare_release_workspace.py](prepare_release_workspace.py)

</details>

<details>
<summary>학습평가 · 51개</summary>

- [baseline_asos.py](baseline_asos.py)
- [baseline_ice_logistic.py](baseline_ice_logistic.py)
- [baseline_ice_nonlinear.py](baseline_ice_nonlinear.py)
- [baseline_neighbor_rwis.py](baseline_neighbor_rwis.py)
- [baseline_weather_ridge.py](baseline_weather_ridge.py)
- [evaluate_antecedent_forward.py](evaluate_antecedent_forward.py)
- [evaluate_catboost_forward.py](evaluate_catboost_forward.py)
- [evaluate_daily_rank_policy.py](evaluate_daily_rank_policy.py)
- [evaluate_daily_threshold_transfer.py](evaluate_daily_threshold_transfer.py)
- [evaluate_development_thermal_ice.py](evaluate_development_thermal_ice.py)
- [evaluate_dsm_consistent.py](evaluate_dsm_consistent.py)
- [evaluate_estimated_temperature_forward.py](evaluate_estimated_temperature_forward.py)
- [evaluate_external_augmentation.py](evaluate_external_augmentation.py)
- [evaluate_external_reserved.py](evaluate_external_reserved.py)
- [evaluate_external_temperature.py](evaluate_external_temperature.py)
- [evaluate_forward_physics.py](evaluate_forward_physics.py)
- [evaluate_freezing_weight.py](evaluate_freezing_weight.py)
- [evaluate_frozen_holdout.py](evaluate_frozen_holdout.py)
- [evaluate_height_transfer.py](evaluate_height_transfer.py)
- [evaluate_ice_methodology.py](evaluate_ice_methodology.py)
- [evaluate_joint_surface.py](evaluate_joint_surface.py)
- [evaluate_memory_forward.py](evaluate_memory_forward.py)
- [evaluate_method_blending.py](evaluate_method_blending.py)
- [evaluate_neighbor_transfer.py](evaluate_neighbor_transfer.py)
- [evaluate_physical_ice.py](evaluate_physical_ice.py)
- [evaluate_regularized_forward.py](evaluate_regularized_forward.py)
- [evaluate_score_blending.py](evaluate_score_blending.py)
- [evaluate_score_calibration.py](evaluate_score_calibration.py)
- [evaluate_surface_state_ensemble.py](evaluate_surface_state_ensemble.py)
- [evaluate_surface_state_forward.py](evaluate_surface_state_forward.py)
- [evaluate_surface_state_v2_ensemble.py](evaluate_surface_state_v2_ensemble.py)
- [evaluate_surface_state_v2_forward.py](evaluate_surface_state_v2_forward.py)
- [evaluate_temperature_mean.py](evaluate_temperature_mean.py)
- [evaluate_temperature_pairs.py](evaluate_temperature_pairs.py)
- [evaluate_temperature_physics.py](evaluate_temperature_physics.py)
- [evaluate_temperature_transfer.py](evaluate_temperature_transfer.py)
- [evaluate_temperature_uncertainty.py](evaluate_temperature_uncertainty.py)
- [evaluate_thermal_consensus.py](evaluate_thermal_consensus.py)
- [evaluate_weather_distance.py](evaluate_weather_distance.py)
- [evaluate_weather_memory_controls.py](evaluate_weather_memory_controls.py)
- [evaluate_weather_memory_temperature.py](evaluate_weather_memory_temperature.py)
- [evaluate_weather_memory_temperature_stable.py](evaluate_weather_memory_temperature_stable.py)
- [evaluate_weather_temporal.py](evaluate_weather_temporal.py)
- [predict_external_reserved.py](predict_external_reserved.py)
- [predict_frozen_holdout.py](predict_frozen_holdout.py)
- [research_ice_methodology.py](research_ice_methodology.py)
- [research_method_blending.py](research_method_blending.py)
- [research_temperature_uncertainty.py](research_temperature_uncertainty.py)
- [research_weather_memory_20261013.py](research_weather_memory_20261013.py)
- [train_ice_candidate.py](train_ice_candidate.py)
- [train_temperature_candidate.py](train_temperature_candidate.py)

</details>

<details>
<summary>분석감사 · 90개</summary>

- [analyze_external_rwis_quality.py](analyze_external_rwis_quality.py)
- [audit_aws_boundaries.py](audit_aws_boundaries.py)
- [audit_aws_cleaning.py](audit_aws_cleaning.py)
- [audit_aws_fallback.py](audit_aws_fallback.py)
- [audit_candidate_prediction_coverage.py](audit_candidate_prediction_coverage.py)
- [audit_chainage_reference.py](audit_chainage_reference.py)
- [audit_completion.py](audit_completion.py)
- [audit_daily_threshold_transfer.py](audit_daily_threshold_transfer.py)
- [audit_data.py](audit_data.py)
- [audit_dem_units.py](audit_dem_units.py)
- [audit_estimated_temperature_forward.py](audit_estimated_temperature_forward.py)
- [audit_freezing_weight.py](audit_freezing_weight.py)
- [audit_fresh_station_validation.py](audit_fresh_station_validation.py)
- [audit_fresh_uncertainty.py](audit_fresh_uncertainty.py)
- [audit_ice_events.py](audit_ice_events.py)
- [audit_ice_methodology.py](audit_ice_methodology.py)
- [audit_ice_weather_history.py](audit_ice_weather_history.py)
- [audit_joint_surface.py](audit_joint_surface.py)
- [audit_kma_external_development.py](audit_kma_external_development.py)
- [audit_kma_rwis_catalog.py](audit_kma_rwis_catalog.py)
- [audit_method_blending.py](audit_method_blending.py)
- [audit_point_input_parity.py](audit_point_input_parity.py)
- [audit_regularized_forward.py](audit_regularized_forward.py)
- [audit_rwis_context.py](audit_rwis_context.py)
- [audit_score_blending.py](audit_score_blending.py)
- [audit_score_calibration.py](audit_score_calibration.py)
- [audit_segment_exposure.py](audit_segment_exposure.py)
- [audit_segment_inference.py](audit_segment_inference.py)
- [audit_sensor_availability.py](audit_sensor_availability.py)
- [audit_spatial.py](audit_spatial.py)
- [audit_station_road_alignment.py](audit_station_road_alignment.py)
- [audit_surface_state_ensemble.py](audit_surface_state_ensemble.py)
- [audit_surface_state_forward.py](audit_surface_state_forward.py)
- [audit_surface_state_v2_ensemble.py](audit_surface_state_v2_ensemble.py)
- [audit_surface_state_v2_forward.py](audit_surface_state_v2_forward.py)
- [audit_temperature_blind_validation.py](audit_temperature_blind_validation.py)
- [audit_temperature_mean.py](audit_temperature_mean.py)
- [audit_temperature_mean_blind.py](audit_temperature_mean_blind.py)
- [audit_temperature_pairs.py](audit_temperature_pairs.py)
- [audit_temperature_transfer.py](audit_temperature_transfer.py)
- [audit_temperature_uncertainty.py](audit_temperature_uncertainty.py)
- [audit_thermal_consensus.py](audit_thermal_consensus.py)
- [audit_timestamps.py](audit_timestamps.py)
- [audit_unresolved_evidence.py](audit_unresolved_evidence.py)
- [audit_weather_distance.py](audit_weather_distance.py)
- [audit_weather_memory_controls.py](audit_weather_memory_controls.py)
- [audit_weather_memory_temperature.py](audit_weather_memory_temperature.py)
- [audit_weather_memory_temperature_stable.py](audit_weather_memory_temperature_stable.py)
- [audit_weather_network_expansion.py](audit_weather_network_expansion.py)
- [compare_data_releases.py](compare_data_releases.py)
- [compare_facility_weather.py](compare_facility_weather.py)
- [compare_fog_ablation.py](compare_fog_ablation.py)
- [compare_ice_history.py](compare_ice_history.py)
- [compare_ice_nonlinear.py](compare_ice_nonlinear.py)
- [compare_ice_variants.py](compare_ice_variants.py)
- [compare_physical_ice.py](compare_physical_ice.py)
- [compare_weather_variants.py](compare_weather_variants.py)
- [diagnose_ice_baseline.py](diagnose_ice_baseline.py)
- [diagnose_ice_context.py](diagnose_ice_context.py)
- [diagnose_joint_surface.py](diagnose_joint_surface.py)
- [diagnose_neighbor_rwis.py](diagnose_neighbor_rwis.py)
- [diagnose_state_temperature.py](diagnose_state_temperature.py)
- [diagnose_weather_ridge.py](diagnose_weather_ridge.py)
- [inspect_blending_evidence.py](inspect_blending_evidence.py)
- [inspect_ice_methodology_evidence.py](inspect_ice_methodology_evidence.py)
- [inspect_ice_methodology_results.py](inspect_ice_methodology_results.py)
- [inspect_weather_memory_controls.py](inspect_weather_memory_controls.py)
- [inspect_weather_memory_inputs.py](inspect_weather_memory_inputs.py)
- [inspect_weather_memory_results.py](inspect_weather_memory_results.py)
- [plot_chainage_review.py](plot_chainage_review.py)
- [plot_fresh_validation.py](plot_fresh_validation.py)
- [plot_ice_methodology.py](plot_ice_methodology.py)
- [plot_joint_surface.py](plot_joint_surface.py)
- [plot_method_blending.py](plot_method_blending.py)
- [plot_physical_comparison.py](plot_physical_comparison.py)
- [plot_temperature_mean_review.py](plot_temperature_mean_review.py)
- [plot_temperature_transfer_review.py](plot_temperature_transfer_review.py)
- [plot_temperature_uncertainty.py](plot_temperature_uncertainty.py)
- [plot_terrain_evidence.py](plot_terrain_evidence.py)
- [plot_unresolved_evidence.py](plot_unresolved_evidence.py)
- [plot_weather_distance_review.py](plot_weather_distance_review.py)
- [plot_weather_memory_controls.py](plot_weather_memory_controls.py)
- [plot_weather_memory_temperature.py](plot_weather_memory_temperature.py)
- [plot_weather_memory_temperature_stable.py](plot_weather_memory_temperature_stable.py)
- [render_segment_review.py](render_segment_review.py)
- [review_temperature_mean_failure.py](review_temperature_mean_failure.py)
- [review_unresolved_evidence.py](review_unresolved_evidence.py)
- [review_weather_memory_events.py](review_weather_memory_events.py)
- [review_weather_memory_tradeoffs.py](review_weather_memory_tradeoffs.py)
- [summarize_fresh_uncertainty.py](summarize_fresh_uncertainty.py)

</details>

<details>
<summary>기타 · 13개</summary>

- [complete_report_reference_review.py](complete_report_reference_review.py)
- [eda_development.py](eda_development.py)
- [export_segment_condition_maps.py](export_segment_condition_maps.py)
- [freeze_assessment.py](freeze_assessment.py)
- [fresh_station_validation.py](fresh_station_validation.py)
- [infer_segment_ice_exploratory.py](infer_segment_ice_exploratory.py)
- [infer_segment_temperature.py](infer_segment_temperature.py)
- [plan_weather_network_expansion.py](plan_weather_network_expansion.py)
- [refresh_manifests.py](refresh_manifests.py)
- [reproduce_weather_fallback.py](reproduce_weather_fallback.py)
- [resume_fresh_collection.py](resume_fresh_collection.py)
- [temperature_blind_validation.py](temperature_blind_validation.py)
- [temperature_mean_blind_validation.py](temperature_mean_blind_validation.py)

</details>
