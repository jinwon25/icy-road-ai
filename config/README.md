# 설정 파일 안내

## 11월 2일 공간·기상 이력의 반증 계획

[weather_network_history_20261102.json](weather_network_history_20261102.json)은 현재 69특성 풍속에 과거 이력을 더한 147특성 단일 후보, 지역 4회·지역/겨울 8회, 같은 HGB와 두 검증의 채택 조건을 고정합니다. 실제 실행 전 `plan.json`에 설정·입력·코드 해시를 보존했고, 두 검증 모두 악화해 미채택했습니다. [설계·참고자료](../docs/research/NETWORK_HISTORY_PLAN_20261102.md) · [완료 수치·검산](../docs/delivery/FOLLOWUP_REVIEW_20261102.md)

채택된 69특성 풍속의 구간 적용은 기존 [공간 적용 설정](weather_segment_projection_20261031.json)의 좌표·기상·두 겨울 달력을 재사용합니다. 새 스크립트는 기존 출력 경로를 사용하지 않고 별도 `wind_network_segment_projection_20261102_v1`에 저장하며 적용 모형·기존 자료의 해시를 고정합니다.

## 최신: 주변 관측망과 풍속 개선을 통합한 v12

[weather_network_20261101.json](weather_network_20261101.json)은 최대4AWS·50km·엄격한과거15분·35추가특성과36적합, 두 검증의 채택 기준을 실행 전에 고정했습니다. 풍속만 통과했고 기온·습도는 유지합니다. [수치·검산·출처](../docs/research/WEATHER_NETWORK_20261101.md)

[물리 입력](weather_thermodynamics_20261101.json)·[CatBoost와 고정 평균](weather_catboost_20261101.json)·[고정 서리 규칙](frost_icing_20261101.json)은 v10 이후의 반증 계획입니다. 결과 확인 뒤 문턱·가중치·채택 조건을 바꾸지 않았고 모두 미채택입니다. 현재 습도는 기존 안정화 이력 계획을 유지합니다. [결과·소스·이용조건](../docs/research/FOLLOWUP_METHODS_20261101.md)

최신 습도는 [weather_humidity_stable_20261101.json](weather_humidity_stable_20261101.json)의 고정 3h/24h·82입력·동일 HGB·5개 채택 기준을 사용합니다. [시간/공간 비교](weather_temporal_memory_20261101.json), [기온 공간 비교](weather_air_history_spatial_20261101.json), [초기 습도 공간 비교](weather_humidity_history_spatial_20261101.json)는 연구 이력입니다. 초기 rolling 결과를 최종 안정화 수치로 대체하지 않습니다. [수치·실패·현재 모델](../docs/research/WEATHER_SPACE_TIME_20261101.md)

[누적 기상 조건 비교](antecedent_forcing_20261031.json)는 40개 순간 입력·64개 이력 입력의 같은 학습 조건과 20적합·지역 이중 제외·선택 절차를 고정합니다. 외부 지표 계산 전 발견한 보고서 순서 오류의 수정과 v1 보존도 기록합니다. [완료 결과·검산](../docs/research/ANTECEDENT_FORCING_20261031.md)

[목적함수 비교](objective_icing_20261031.json)는 네 손실·40적합·지역 이중 제외·채택 조건을 고정합니다. [ERA5-Land 입력 확보](reanalysis_inputs_20261031.json)는 기존 23지점·두 겨울의 사후 열·수분·적설 자료만 요청합니다. [결과·문헌·검산](../docs/research/OBJECTIVE_ICING_20261031.md)

[재분석 온도 비교](reanalysis_temperature_20261031.json)는 v3 설정의 입력 추가 8모델, [재분석 결빙 비교](reanalysis_icing_20261031.json)는 동일 분류기·가중치의 30모델·내부 임계값 선택을 고정합니다. 두 실험 모두 [완료 검산과 미채택 근거](../docs/research/REANALYSIS_INPUTS_20261031.md)를 남겼습니다.

[10월 31일 공식 확인 설정](official_requirements_20261031.json)은 접수 개시·문서자료/모델자료 ZIP 형식과 근거의 확인 방법을 구분합니다. 마감 날짜는 미확인이며 과거 설정의 ‘별도 공지 예정’을 현재 사실로 사용하지 않습니다.

최신 [잔차 학습 설정](residual_icing_20261025.json)은 기온 시작값·가중치·30모델·49정책·지역 내부 선택을, [관측 지연 설정](causal_trend_20261025.json)은 과거 두 시간 관측만 사용하는 10정책을 고정합니다. 기존 개발 지역의 반복 비교이며 보호 지점·이미 개봉한 새 4곳은 사용하지 않습니다. 안정적 개선이 없어 모델을 유지했습니다. [설계·결과·입력 정보량 진단](../docs/research/RESIDUAL_AND_INFORMATION_20261025.md)

앞선 [추가 탐지 설정](additive_icing_20261025.json)은 기존 기온 경보를 보존하는 57정책·20모델과 지역 내부 선택 절차를 고정합니다. 새 4지역 정답을 사용하지 않는 반복 개발 실험이며, 기준선을 안정적으로 넘지 못해 제출 모델은 유지합니다. [방법·결과·원문 진단](../docs/research/RWIS_CAUSE_AND_ADDITIVE_20261025.md)

[새 4지역 평가 설정](blind_icing_20261025.json)은 허용 학습 범위·고정 4후보·주 후보·전체 두 겨울·지표 분모·성공 조건을 정답 수집 전에 확정한 계획입니다. 이미 조회한 새 지역을 다시 독립 평가로 봉인하는 기능은 없습니다. [입력 검증·봉인·결과 보고서](../docs/research/BLIND_ICING_20261025.md)를 함께 읽습니다.

앞선 [제한 보정 설정](icing_anchor_20261025.json)은 보정 폭·방향·내부 선택·기존 채택 기준을 고정합니다. [추가 지역 선별 설정](expanded_icing_validation_20261025.json)은 위치만으로 새 도로 후보를 골라 기상 입력을 준비하는 범위이며 노면 정답 수집을 수행하는 계획이 아닙니다. 결과는 [모델 연구](../docs/research/ANCHORED_ICING_20261025.md)·[자료 확보](../docs/research/ICING_ACQUISITION_20261025.md)에 연결합니다.

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
