# 설정 파일 안내

설정은 데이터 버전·분할·실험 조건의 재현 근거입니다. 비슷한 이름의 설정도 서로 다른 비교를 기록하므로 삭제하거나 최신 설정으로 덮어쓰지 않습니다.

[프로젝트 소개](../README.md) · [실행 스크립트](../scripts/README.md) · [검증 규약](../docs/validation/VALIDATION_PROTOCOL.md)

## 먼저 확인할 설정

| 파일 | 역할 |
| --- | --- |
| [data_source.json](data_source.json) | 루트 기본 20260915 ZIP의 이름·SHA256과 20261007 별도 작업 위치 |
| [evaluation.json](evaluation.json) | 보호 지점과 평가 규칙 |
| [notebook_workflow.json](notebook_workflow.json) | 노트북 실행 단계와 산출물 |
| [official_requirements_20261016.json](official_requirements_20261016.json) | 오늘 공식 공개 원문과 양식을 대조한 요구사항 |
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
