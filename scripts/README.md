# 실행 스크립트 안내

이 문서는 실행 목적에 맞는 스크립트를 찾는 입구입니다. `evaluate_*`는 비교 실험, `audit_*`는 저장 결과의 별도 검산, `check_*`는 코드·문서 검사를 뜻합니다. 학습·검산에는 `outputs/private/`의 허용 자료가 필요하며 GitHub만 내려받으면 해당 자료가 생기지 않습니다. [용어와 버전](../docs/START_HERE.md)

## 10월 25일 기온 기준선 차이와 추가 기상 연구

[원인·전체 결과](../docs/research/ICING_GAP_AND_SYNOPTIC_20261025.md)에서 점수 해석과 실제 비공개 경로를 확인합니다. 아래 과정은 제출 모델을 바꾸지 않는 개발 실험입니다.

| 스크립트 | 역할 |
| --- | --- |
| `diagnose_icing_baseline_gap.py` | 현재 판정과 기온 기준선의 미탐 조건·지점별 F1·날짜 분모 효과 분해 |
| `review_additional_icing_sources.py` | 제설 자료·RSCD 원 저자와 복제본의 공개 원문·접근 결과 보존 |
| `prepare_synoptic_icing.py` | 제공 ASOS의 미사용 8관측을 과거 관측 규칙으로 연결하고 별도 검산 |
| `evaluate_synoptic_icing.py` | 50개 모델·수분 이력 규칙·중첩 선택 비교. 완료 모델은 해시 확인 후 재사용 |
| `audit_synoptic_icing.py` | 50모델 재추론·학습 가중치·수분 상태·지표·선택·원인 분해를 별도로 대조 |
| `summarize_synoptic_icing.py` | 감사 영수증에 맞는 전체 후보표와 비교 그림 생성 |

학습 재개 시 저장 전후 DataFrame의 내부 index가 달라도 실제 지점·시각·순서가 일치하면 이어서 실행합니다. 키가 달라진 경우에는 중단합니다. 원본 데이터·설정·학습 코드 변경을 허용하는 기능은 아닙니다. 이미 `summary.json`이 있는 완료 폴더는 덮어쓰지 않습니다.

## 앞선 10월 25일 결빙 전이 연구

| 스크립트 | 역할 |
| --- | --- |
| `review_official_updates.py` | 공식 원문·질문·답변·빈 참가서약을 이전 보존본과 대조 |
| `evaluate_icing_transition.py` | 기상 조건부 상태 전이 모델 30개를 지역 이중 제외로 학습·비교 |
| `refine_icing_thresholds.py` | 새 학습 없이 내부 지역의 모든 서로 다른 점수에서 임계값 선택 |
| `audit_icing_transition.py` | 저장 모델·상태 재귀·지역 분리·날짜별 지표·결빙 사건·선택 결과 검산 |
| `summarize_icing_transition.py` | 검산된 44행 후보표와 F1·정밀도·재현율 그림 생성 |
| `package_icing_review_candidate.py` | v4 실행 자산을 보존하고 v5 준비·실행 검증·ZIP 검산 수행 |

계획은 [전이 학습 설정](../config/icing_transition_20261025.json)과 [임계값 설정](../config/icing_threshold_refinement_20261025.json), 결과·정확한 실행 명령은 [연구 보고서](../docs/research/ICING_TRANSITION_REVIEW_20261025.md)에서 확인합니다. 완료된 실험 출력은 덮어쓰지 않고 새 비공개 경로를 사용합니다.

## v3 이후 후속 연구

[후속 비교·구간 탐색 기록](../docs/delivery/FOLLOWUP_UPGRADE_20261024.md)에서 실제 완료 상태를 확인합니다. `evaluate_followup_temperature.py`는 고정한 시간 이력·손실·알고리즘 대조를 기존 실행기에 연결하고, `extend_followup_capacity.py`는 사전 기준을 통과한 600회 모델만 연장합니다. `evaluate_followup_offset.py`는 평가 지역을 보정에서도 제외한 6개 적합을 수행합니다. 대응하는 `audit_followup_temperature.py`·`audit_followup_offset.py`가 저장 모델·분리·출력·보정 계산을 확인합니다.

`evaluate_icing_state_memory.py`·`audit_icing_state_memory.py`는 결빙 시간 상태 정책과 별도 벡터 재계산, `audit_long_memory.py`는 긴 기상 이력의 정규 격자 재계산을 담당합니다. `compare_followup_results.py`는 완료·감사된 후보만 현재 v3와 같은 여섯 기준으로 비교합니다. 원 실행 보고서의 이전 v2 대비 통과 여부를 v3 개선으로 읽지 않습니다.

`audit_followup_failure_diagnostics.py`는 결빙의 지점·겨울 집중, 관측 온도와의 관계, 오경보 날짜의 진단표를 별도 집계합니다. 원인을 센서 오류로 확정하거나 정답을 바꾸는 도구가 아닙니다.

`build_review_dashboard.py`·`audit_review_dashboard.py`는 검증된 CSV·공간 도형으로 통신 없는 탐색 화면을 만들고 숫자·필터·다운로드·모바일 표시를 검사합니다. `package_followup_candidate.py`는 후속 비교가 기존 모델 유지로 끝난 경우에만 새 v4를 만들도록 제한합니다. 기존 v3를 덮어쓰지 않으며 `prepare`·`assets`·`verify`·`package` 순서와 완료 영수증을 따릅니다.

`record_review_dashboard.py`는 실제 Chromium 조작을 WebM으로 녹화하고 다운로드·재생·전체 프레임 디코딩을 검사합니다. 별도 Playwright와 Chromium이 필요한 검수 도구이며 제출 모델 추론에는 필요하지 않습니다. 실제 영상 프레임의 시각 검토 여부는 녹화 영수증에 기록합니다.

## 10월 24일 기상·열 이력 확장

[확장 통합 기록](../docs/delivery/EXTENDED_UPGRADE_20261024.md)을 먼저 확인합니다. `compare_extended_completion.py`는 완료 설정과 고정 평균을 모으고, `audit_advanced_models.py`·`audit_extended_classification.py`는 저장 모델과 지역 제외·임계값 선택을 검산합니다. `seal_extended_selection.py`는 감사 영수증을 연결한 선택안만 제출 준비에 넘깁니다.

`build_extended_candidate.py`가 새 폴더·포함 학습 입력·전체 공간 추론을 구성합니다. `train_extended_submission.py`·`predict_extended_submission.py`가 현재 독립 실행 코드이며 새 후보의 `code/train.py`·`code/predict.py`에 복사됩니다. `export_extended_delivery_tables.py`, `complete_extended_delivery.py`, `render_extended_review.py`, `finalize_extended_candidate.py`는 CSV·지도·실제 출력 데모·노트북·보고서와 검증 ZIP을 만듭니다. 현재 준비·완료 상태는 검증 영수증을 확인하며 기존 v2에 이 생성기를 적용하지 않습니다.

## 이전 v2: 10월 24일 두 겨울 모델 고도화

당시 진입점은 [실험·결과·실행 안내](../docs/delivery/AWARD_UPGRADE_20261024.md)입니다. `evaluate_award_ice.py`·`audit_award_ice.py`는 첫 겨울 중첩 분류 선택, `prepare_two_winter_development.py`·`evaluate_two_winter.py`·`audit_two_winter.py`는 비보호 두 겨울 비교, `upgrade_two_winter_candidate.py`는 최종 적합·전체 추론, `complete_two_winter_delivery.py`는 지도·실행 예제·노트북을 생성합니다. `render_award_review.py`는 이전 6쪽 보고서의 생성기입니다. 아래 이전 패키징 진입점은 당시 후보용이며 보존된 v2를 덮어쓰는 용도로 사용하지 않습니다.

## 10월 24일 CSV 산출·새 후보 통합

`export_delivery_tables.py`는 후보 manifest에 고정된 예측·허용 개발표만 읽고 CSV 11종과 파일별 키·자료형·결측·해시 목록을 새 폴더에 생성합니다. CSV 숫자 재독해·일별/겨울 합계·기존 24개 지표를 검산합니다. `package_delivery_tables.py`는 원 ZIP과 검증한 CSV를 새 ZIP에 통합하며 기존 모델·데이터·보고서·데모 해시를 보존합니다. [실행 명령·검증](../docs/delivery/DELIVERY_UPGRADE_20261024.md) · [CSV 규약](../docs/delivery/CSV_CONTRACT.md)

모든 명령은 저장소 루트에서 실행합니다. 단계 간 import·작업 루트 계산·봉인 기록을 보존하기 위해 기존 Python 파일 위치와 명령은 유지합니다.

[현재 현황](../docs/STATUS.md) · [실행 안내](../docs/delivery/RUNBOOK.md) · [설정 안내](../config/README.md)

## 자주 찾는 진입점

| 목적 | 파일 |
| --- | --- |
| 코드·노트북 출력·인증정보 검사 | [check_repository.py](check_repository.py) |
| GFM 렌더·링크·앵커 검사 | [check_markdown.py](check_markdown.py) |
| 현재 v3 보고서 작성 | [render_extended_review.py](render_extended_review.py) |
| 현재 v3 검산·ZIP 생성 | [finalize_extended_candidate.py](finalize_extended_candidate.py) |
| 현재 온도·별도 결빙 기준 추론 | [extended_runtime.py](../src/extended_runtime.py) |
| 제출 ZIP 해시 검증·새 폴더 복원 | [submission_archive.py](../src/submission_archive.py) |
| 현재 지도·화면·영상·노트북 생성 | [complete_extended_delivery.py](complete_extended_delivery.py) |
| 10월 19일 누수·지표·노트북 감사와 새 후보 | [review_delivery_20261019.py](review_delivery_20261019.py) |
| 새 출력 폴더에 공식 목록·본문·첨부 표시 대조 | [review_official_updates.py](review_official_updates.py) |
| 과거 Ridge·HGB 기준선 데모 | [demo_inference.py](demo_inference.py) |
| 데이터 버전별 작업 복사본 | [prepare_release_workspace.py](prepare_release_workspace.py) |

학습·공식 사이트 수집·패키징은 출력 경로와 선행 조건을 확인한 뒤 실행합니다. 현재 후보 묶음과 이미 완료한 평가를 덮어쓰지 않습니다. 수정본 연구는 별도 작업 루트의 실행 안내를 따릅니다.

10월 19일 후보는 [제출용 노트북](../notebooks/submission_review.ipynb)을 압축 해제 폴더에서 실행합니다. 원 연구 공간이 필요한 기존 `analysis_review.ipynb`와 구별합니다. [단계별 실행·검증 결과](../docs/delivery/DELIVERY_REVIEW_20261019.md)

다음은 10월 16일 이전 후보의 실행 예입니다. 현재 v3는 압축 해제 폴더의 README와 `code/predict.py`를 따릅니다. 원본 저장소에는 모델이 포함되지 않습니다.

```powershell
python -m src.submission_archive --archive outputs/private/submission_candidate_20261016_v1.zip --output outputs/private/candidate_work_20261016
python -m src.submission_runtime --input outputs/private/candidate_work_20261016/data/weather_example.csv --models outputs/private/candidate_work_20261016/model --output outputs/private/new_candidate_prediction.csv
```

복원 경로·예측 경로가 이미 존재하면 중단합니다. 예제는 현재 학습 모델의 실행 확인용이며 새 지점 성능 평가가 아닙니다. [기준선·재현성 후속 검토](../docs/delivery/REVIEW_RESPONSE_20261016.md)

## 10월 16일 추가 연구

현재 실행 모델은 유지합니다. 다음 실험은 기존 개발 자료·공간 제외 저장 모델·감사 자료가 필요하며, 완료 폴더나 감사 영수증이 있으면 덮어쓰지 않고 중단합니다. 공개 코드만으로 연구 전체를 재현할 수 있다는 뜻이 아닙니다. [결과·선행연구·한계](../docs/research/AIR_ROAD_AND_INPUT_GAPS_20261016.md)

| 목적 | 실행 파일 |
| --- | --- |
| 같은 날 공식 원문·양식 재대조 | [review_official_followup_20261016.py](review_official_followup_20261016.py) |
| 72개 기온·노면 규칙과 두 내부 선택 경로 | [evaluate_air_road_blending.py](evaluate_air_road_blending.py) |
| 시간창·지표·사건·20모델 재추론 독립 검산 | [audit_air_road_blending.py](audit_air_road_blending.py) |
| ASOS 대체·개발 648개 합성 공백 | [evaluate_asos_gap_fallback.py](evaluate_asos_gap_fallback.py) |
| ASOS 행별 선택·온도·참고 출력 검산 | [audit_asos_gap_fallback.py](audit_asos_gap_fallback.py) |
| 원 ASOS 공백 1회 조회 | [probe_asos_gap_source.py](probe_asos_gap_source.py) |
| 정상 ASOS 대조군·첫 겨울 직전 원 관측 3회 조회 | [collect_asos_gap_controls.py](collect_asos_gap_controls.py) |
| 둘째 겨울 직전·장수 공백·AWS 접근 3회 조회 | [collect_weather_gap_followup.py](collect_weather_gap_followup.py) |
| 원 기상과 캐시·결측·최초 입력 대조 | [audit_weather_source_gaps.py](audit_weather_source_gaps.py) |
| 기존 위치 표와 현재 요청 이력만으로 미사용 지점 점검 | [audit_remaining_station_metadata.py](audit_remaining_station_metadata.py) |
| 후속 연구 4쪽 PDF 작성·렌더링 | [build_air_road_gap_report.py](build_air_road_gap_report.py) |
| 새 실험·문서·PDF·보존 해시 종합 검사 | [check_air_road_followup_quality.py](check_air_road_followup_quality.py) |

인증 조회 세 파일은 기존 `KMA_AUTH_KEY` 환경값 또는 로컬 `secret.env`가 필요합니다. 키·키 포함 URL을 출력하거나 저장하지 않습니다. API 요청량은 합계 7회이며 공식 원 기상만 읽습니다. 보호·이미 개봉한 도로 정답이나 외부 예측 서비스는 요청하지 않습니다. AWS 응답은 403이었으며 이를 접근 성공으로 표시하지 않습니다.

기존 결과가 없는 별도 작업 공간에서 실행할 때는 `python scripts/파일명.py`를 사용합니다. 실험 다음 해당 감사를 실행합니다. 원 기상 감사는 세 수집 파일이 모두 완료돼야 합니다. 보고서 작성은 모든 감사가 통과한 뒤 수행합니다. 현재 보존된 결과를 다시 생성하려고 삭제하지 않습니다.

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
