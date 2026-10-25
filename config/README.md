# 설정 파일 안내

최신 [추가 탐지 설정](additive_icing_20261025.json)은 기존 기온 경보를 보존하는 57정책·20모델과 지역 내부 선택 절차를 고정합니다. 새 4지역 정답을 사용하지 않는 반복 개발 실험이며, 기준선을 안정적으로 넘지 못해 제출 모델은 유지합니다. [방법·결과·원문 진단](../docs/research/RWIS_CAUSE_AND_ADDITIVE_20261025.md)

[새 4지역 평가 설정](blind_icing_20261025.json)은 허용 학습 범위·고정 4후보·주 후보·전체 두 겨울·지표 분모·성공 조건을 정답 수집 전에 확정한 계획입니다. 이미 조회한 새 지역을 다시 독립 평가로 봉인하는 기능은 없습니다. [입력 검증·봉인·결과 보고서](../docs/research/BLIND_ICING_20261025.md)를 함께 읽습니다.

최신 [제한 보정 설정](icing_anchor_20261025.json)은 보정 폭·방향·내부 선택·기존 채택 기준을 고정합니다. [추가 지역 선별 설정](expanded_icing_validation_20261025.json)은 위치만으로 새 도로 후보를 골라 기상 입력을 준비하는 범위이며 노면 정답 수집을 수행하는 계획이 아닙니다. 결과는 [모델 연구](../docs/research/ANCHORED_ICING_20261025.md)·[자료 확보](../docs/research/ICING_ACQUISITION_20261025.md)에 연결합니다.

## 10월 25일 현재 확인할 설정

| 파일 | 읽는 목적 |
| --- | --- |
| [official_requirements_20261025.json](official_requirements_20261025.json) | 최신 상세 규정·빈 참가서약 확인 및 결과물 날짜 미공표 상태 |
| [icing_synoptic_20261025.json](icing_synoptic_20261025.json) | 추가 ASOS 8관측·날짜 균형·제한된 상호작용·50개 모델·수분 이력 6규칙의 사전 비교 계획 |
| [icing_transition_20261025.json](icing_transition_20261025.json) | 학습 지점·가상 직전 상태·결측 초기화·30개 적합·채택 기준 |
| [icing_threshold_refinement_20261025.json](icing_threshold_refinement_20261025.json) | 내부 검증에서 모든 서로 다른 임계값을 비교하는 추가 대조 |

기술 용어는 [처음 읽는 안내](../docs/START_HERE.md), 실제 결과는 [현재 상태](../docs/STATUS.md)를 참고합니다. 아래 날짜별 설정은 이전 실행을 재현하기 위한 기록입니다.

설정은 데이터 버전·분할·실험 조건의 재현 근거입니다. 비슷한 이름의 설정도 서로 다른 비교를 기록하므로 삭제하거나 최신 설정으로 덮어쓰지 않습니다.

[프로젝트 소개](../README.md) · [실행 스크립트](../scripts/README.md) · [검증 규약](../docs/validation/VALIDATION_PROTOCOL.md)

## 먼저 확인할 설정

| 파일 | 역할 |
| --- | --- |
| [official_requirements_20261024.json](official_requirements_20261024.json) | 10월 24일 공개 목록 확인과 10월 16일 마지막 상세 확인을 구분 |
| [followup_temperature_20261024.json](followup_temperature_20261024.json) | 24·48시간 이력·잔차·결빙점 가중 학습과 고정 연장 기준 |
| [followup_algorithm_20261024.json](followup_algorithm_20261024.json) | 최종 63개 입력의 LightGBM L1/L2와 세 고정 평균 |
| [followup_offset_20261024.json](followup_offset_20261024.json) | 두 지역 동시 제외 6개 적합과 두 상수 보정 정책 |
| [icing_state_memory_20261024.json](icing_state_memory_20261024.json) | 연속 확인·지속·해제의 새 결빙 상태 정책 14개 |
| [extended_final_selection_20261024.json](extended_final_selection_20261024.json) | 확장 온도 후보의 용량·시드·고정 평균·복잡성 선택 기준 |
| [solar_loss_pair_20261024.json](solar_loss_pair_20261024.json) | 유력 63개 입력에서 MAE·MSE의 고정 평균 후속 대조 |
| [extended_adoption_20261024.json](extended_adoption_20261024.json) | 회귀·결빙의 별도 채택 기준과 실용적 포화의 범위 |
| [two_winter_development_20261024.json](two_winter_development_20261024.json) | 비보호 두 겨울 개발 재분류·지역 제외·온도 대조 설정 |
| [temperature_adoption_20261024.json](temperature_adoption_20261024.json) | 결과 확인 전에 고정한 온도 후보 채택 기준 |
| [award_ice_experiment_20261024.json](award_ice_experiment_20261024.json) | 일별 F1 목적의 지역 이중 제외·임계값·평활화 비교 |
| [data_source.json](data_source.json) | 루트 기본 20260915 ZIP의 이름·SHA256과 20261007 별도 작업 위치 |
| [evaluation.json](evaluation.json) | 보호 지점과 평가 규칙 |
| [notebook_workflow.json](notebook_workflow.json) | 노트북 실행 단계와 산출물 |
| [official_requirements_20261016.json](official_requirements_20261016.json) | 마지막으로 상세 원문과 양식까지 대조한 요구사항 |
| [air_road_blending_experiment.json](air_road_blending_experiment.json) | 기온·노면 72개 고정 규칙과 두 선택 경로. 미채택 연구 |
| [asos_gap_fallback_experiment.json](asos_gap_fallback_experiment.json) | 대체 ASOS 거리·나이·648개 합성 공백·사전 품질 기준. 미채택 연구 |
| [weather_memory_temperature_stable_experiment.json](weather_memory_temperature_stable_experiment.json) | 현재 2종 평균 후보의 실험 조건 |
| [freezing_weight_experiment.json](freezing_weight_experiment.json) | 미채택 결빙점 가중 모델의 비교 조건 |

## 전체 설정

- [air_road_blending_experiment.json](air_road_blending_experiment.json)
- [asos_gap_fallback_experiment.json](asos_gap_fallback_experiment.json)
- [antecedent_forward_experiment.json](antecedent_forward_experiment.json)
- [catboost_forward_experiment.json](catboost_forward_experiment.json)
- [daily_rank_experiment.json](daily_rank_experiment.json)
- [data_source.json](data_source.json)
- [dsm_consistent_experiment.json](dsm_consistent_experiment.json)
- [estimated_temperature_forward_experiment.json](estimated_temperature_forward_experiment.json)
- [evaluation.json](evaluation.json)
- [external_augmentation_experiment.json](external_augmentation_experiment.json)
- [external_temperature_experiment.json](external_temperature_experiment.json)
- [forward_physics_experiment.json](forward_physics_experiment.json)
- [freezing_weight_experiment.json](freezing_weight_experiment.json)
- [fresh_station_validation.json](fresh_station_validation.json)
- [ice_methodology_experiment.json](ice_methodology_experiment.json)
- [ice_nonlinear_experiment.json](ice_nonlinear_experiment.json)
- [kma_external_validation_plan.json](kma_external_validation_plan.json)
- [memory_forward_experiment.json](memory_forward_experiment.json)
- [method_blending_experiment.json](method_blending_experiment.json)
- [notebook_workflow.json](notebook_workflow.json)
- [official_requirements_20261013.json](official_requirements_20261013.json)
- [official_requirements_20261013_v2.json](official_requirements_20261013_v2.json)
- [official_requirements_20261014.json](official_requirements_20261014.json)
- [official_requirements_20261016.json](official_requirements_20261016.json)
- [physical_experiment.json](physical_experiment.json)
- [regularized_forward_experiment.json](regularized_forward_experiment.json)
- [surface_state_ensemble.json](surface_state_ensemble.json)
- [surface_state_forward_experiment.json](surface_state_forward_experiment.json)
- [surface_state_v2_ensemble.json](surface_state_v2_ensemble.json)
- [surface_state_v2_forward_experiment.json](surface_state_v2_forward_experiment.json)
- [temperature_blind_validation_20261010.json](temperature_blind_validation_20261010.json)
- [temperature_loss_experiment.json](temperature_loss_experiment.json)
- [temperature_mean_blind_validation_20261010.json](temperature_mean_blind_validation_20261010.json)
- [temperature_mean_experiment.json](temperature_mean_experiment.json)
- [temperature_pair_blending_experiment.json](temperature_pair_blending_experiment.json)
- [temperature_physics_experiment.json](temperature_physics_experiment.json)
- [temperature_transfer_experiment.json](temperature_transfer_experiment.json)
- [thermal_consensus_experiment.json](thermal_consensus_experiment.json)
- [weather_distance_experiment.json](weather_distance_experiment.json)
- [weather_memory_control_experiment.json](weather_memory_control_experiment.json)
- [weather_memory_temperature_experiment.json](weather_memory_temperature_experiment.json)
- [weather_memory_temperature_stable_experiment.json](weather_memory_temperature_stable_experiment.json)
