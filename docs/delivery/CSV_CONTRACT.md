# 제출 CSV 형식과 해석

고정 후보의 결과를 일반 CSV로 읽고 검산하기 위한 프로젝트 자체 규약입니다. 공식 고정 템플릿으로 주장하지 않습니다. 기존 생성기는 [export_delivery_tables.py](../../scripts/export_delivery_tables.py), 확장 후보 생성기는 [export_extended_delivery_tables.py](../../scripts/export_extended_delivery_tables.py), 집계 코드는 [delivery_tables.py](../../src/delivery_tables.py)입니다.

확장 v3의 규약은 `manifest.json`의 `development_scope=extended_two_winter`입니다. `estimated_road_temp_c`는 새 기상·열 이력 모델의 온도이고, `icing_reference_temperature_c`는 유지한 v2 결빙 판정에 실제 사용한 온도입니다. 따라서 `predicted_ice`를 새 온도 하나로 역산하지 않습니다. 결빙 채택 기준을 통과한 새 분류기가 없어 기존 결빙 판정을 유지한 경우의 계약입니다. 모델 간 차이를 감추지 않고 10분 CSV·데모에 두 온도를 함께 제공합니다. v3 최종 생성·검증 여부는 해당 폴더의 검증 영수증으로 확인합니다.

10월 24일 v2 후보는 두 겨울 온도 모델로 갱신했습니다. `manifest.json`의 `development_scope=two_winter`를 확인합니다. 개발 일별표는 51,840행이며 `current`는 새 고정 온도·수분 규칙, `previous_first_winter`는 동일 실험의 첫 겨울 재적합 대조군, `asos_air_temp_le_zero`는 기온 기준선, `learned_nested_selected`는 미채택 중첩 분류 선택, `always_one/always_zero`는 상수 기준선입니다. `f1_fixed_population`은 미정의 지점을 선택용 0으로 둔 전체 지점 평균이며 공식 미정의 지점 규약으로 주장하지 않습니다. 이전 v1의 first_winter 지표와 혼합하지 않습니다. [범위·결과·한계](AWARD_UPGRADE_20261024.md)

## 파일과 행키

모든 CSV는 UTF-8 BOM·쉼표 구분·헤더 1행이며 결측은 `NA`입니다. 지점·구간·그룹 식별자는 문자열로 읽습니다. 시간은 한국 시간이며 `2024-11-01T00:00:00` 형식입니다. `winter=2024`는 2024년 11월부터 2025년 2월, `2025`는 다음 겨울입니다. 분류값 0은 유효 음성, 1은 조건 충족, `NA`는 입력 부족입니다. 확률이 아닙니다.

| 파일 | 행키 | 내용 |
| --- | --- | --- |
| `protected_predictions_10min.csv` | station, time | 보호 3곳·두 겨울 103,680행의 추정 온도·결빙 조건·입력 상태 |
| `protected_missing_inputs.csv` | station, time | 위 결과의 온도 또는 결빙 판단이 누락된 행과 사유 |
| `prediction_groups_10min.csv.gz` | prediction_group, time | 공유 기상 그룹별 10분 추정. gzip을 지원하는 pandas 등으로 직접 읽기 |
| `point_prediction_index.csv` | kind, scale_m, id, winter | 위치·구간과 공유 기상 그룹의 연결. kind는 protected 또는 segment |
| `segment_estimates.csv` | scale_m, winter, seg_id | 500m·1km 구간의 겨울별 온도·저온 수분 조건 노출·시설 속성 |
| `prediction_group_daily.csv` | prediction_group, date_kst | 공유 그룹의 일별 온도·조건 노출·유효 슬롯 수 |
| `segment_environment_correlations.csv` | scale_m, winter, predictor, target, method | 구간 환경과 추정값의 Pearson·Spearman 기술통계 |
| `development_ice_daily.csv` | method, min_valid_slots, station, date_kst | 허용 개발 지점별 하루 혼동행렬·분모·포함 여부 |
| `development_ice_stations.csv` | method, min_valid_slots, station | 날짜 평균으로 계산한 지점별 지표와 지표별 날짜 수 |
| `development_ice_summary.csv` | method, min_valid_slots | 지점 평균·가용 지점 수·지표별 날짜 수. 공식 점수 아님 |
| `development_temperature_stations.csv` | station | 공간 제외 개발 예측의 BIAS·MAE·RMSE·유효 쌍 수 |

`manifest.json`은 파일별 SHA-256·바이트 수·행 수·키·열별 자료형·결측 개수 및 입력 파일 해시를 담습니다. 압축 CSV도 논리적으로 하나의 표입니다. gzip 멤버를 여러 개 이어 쓴 스트림이며 Python gzip과 pandas로 전체 행 수를 재확인합니다.

## 단위와 열 정의

| 열 또는 열 묶음 | 정의·단위 |
| --- | --- |
| station, id, seg_id, prediction_group | 문자열 식별자. 같은 그룹은 같은 입력과 예측을 공유함 |
| time, date_kst | 한국 시간의 10분 시각 또는 날짜 시작 시각. UTC로 해석하지 않음 |
| scale_m, len_m | 구간 명목 규모와 실제 잘린 선 길이, m. 경계의 잔여 구간은 짧을 수 있음 |
| point_lat, point_lon | 구간 중간점 위도·경도, 도. 공식 이정이나 센서 실측 좌표를 뜻하지 않음 |
| route_nm, flow_lbl | 원 도로망의 노선명·방향 표기 |
| estimated_road_temp_c, estimated_temp_mean_c/min_c/max_c | 추정 노면온도 또는 유효 시점의 평균·최저·최고, °C |
| temperature_component_spread_c | 현재 온도 구성 모델의 최댓값−최솟값, °C. 모델이 하나면 0이며 오차가 0이라는 뜻이 아님. 보정된 오차구간이 아님 |
| icing_reference_temperature_c | v3에서 결빙 조건 판정에 사용한 별도 v2 온도, °C |
| icing_reference_component_spread_c | v2 결빙 기준 온도 구성 모델 두 개의 절대 차, °C |
| icing_policy | 실제 적용한 판정 정책 식별자. v2 유지 시 v2_weather12_temperature_moisture |
| temperature_model_kind, temperature_model_count | 현재 온도 모델의 입력 구성 식별자와 고정 평균에 사용한 모델 개수 |
| weather_history_available_features, weather_history_expected_features | 해당 시각에서 계산 가능한 과거 기상 특징 수와 선언한 전체 수 |
| weather_history_status | complete, partial_or_unavailable, not_used. 과거 특징 결측을 미래 값으로 채우지 않음 |
| predicted_ice | 고정된 온도·수분 조건에 따른 0/1. `NA`를 0으로 채우지 않음 |
| condition_evidence | cold_wet_consensus, cold_wet_disagreement, criterion_not_met, insufficient_input 등 기존 실행 코드의 상태 |
| temperature_status, moisture_status, aws_status | ASOS·수분 자료의 유효 여부와 AWS의 결측·오래된 입력 상태 |
| bridge_code_fraction, tunnel_code_fraction | 구간 길이 중 도로망 교량·터널 코드 비율, 0–1. 실제 시설 범위 검증 완료를 뜻하지 않음 |
| asos_distance_km, aws_distance_km_max | 기상 관측소까지 거리, km. 위치별 오차를 보정하는 변수가 아님 |
| nearest_aws_distance_km, third_aws_distance_km | 첫 번째·세 번째 AWS 후보까지 거리, km |
| planned_slots, expected_slots, present_slots | 예정 시각 수, 하루 예정 144개, 파일에 실제 존재하는 시각 수 |
| temperature_valid_slots, ice_valid_slots | 유효 온도·유효 조건 판단이 있는 10분 시각 수 |
| missing_ice_slots | 하루 144개에서 유효 판단 수를 뺀 값. 없는 행과 `NA` 모두 포함 |
| cold_wet_slots, consensus_slots, disagreement_slots | 고정 조건 충족 시각 수 및 그중 두 모델 합의·불일치 시각 수 |
| cold_wet_hours | 유효 조건 충족 슬롯 수÷6, 시간. 하루 판단 전체가 결측이면 `NA` |
| cold_wet_fraction | 충족 슬롯 수÷유효 판단 슬롯 수. 하루가 불완전해도 유효 슬롯을 분모로 사용 |
| complete_day | 유효 조건 판단이 144개인 날짜만 True |
| tp, fp, fn, tn | 유효 관측 정답에 대한 10분 혼동행렬 건수 |
| missing_prediction_rows, known_positive_rows_without_prediction | 개발 예측이 null인 행 수와 그중 관측 Ice=1인 행 수. 결측 쌍은 혼동행렬·유효 슬롯 수에서 제외 |
| min_valid_slots, coverage_accepted | 날짜를 포함할 최소 유효 관측 수와 통과 여부. 144·130·72·1은 잠정 민감도 조건 |
| valid_slots, actual_ice_slots, predicted_ice_slots, metric_active_slots | 관측 유효 수, 실제 양성 수, 예측 양성 수, TP+FP+FN |
| both_zero, miss_only, false_alarm_only | 실제·예측 양성 모두 없음, 미탐만 있음, 오경보만 있음 |
| precision, recall, f1 | 0–1. TP/(TP+FP), TP/(TP+FN), 2TP/(2TP+FP+FN). 분모 0은 `NA` |
| included_precision/recall/f1 | 날짜 관측량 조건과 해당 지표의 정의 여부를 모두 통과한 날짜 |
| precision_days/recall_days/f1_days | 각 지표 평균에 실제 포함된 날짜 수. 서로 다를 수 있음 |
| planned_days, coverage_days, active_days, both_zero_days | 예정 날짜, 관측량 통과 날짜, 통과 중 TP+FP+FN>0인 날짜, 통과 중 실제·예측 양성 모두 없는 날짜 수 |
| miss_only_days, false_alarm_only_days, excluded_ice_days | 통과한 미탐일·오경보일 수와 관측량 때문에 제외된 실제 결빙일 수 |
| population_stations, precision_stations/recall_stations/f1_stations | 선언한 지점 수와 해당 지표가 정의된 지점 수 |
| *_available_station_mean | 지표가 정의된 지점만의 평균. 가용 지점 수를 함께 표시 |
| *_all_population_station_mean | 선언한 모든 지점에서 지표가 정의된 경우에만 평균. 한 곳이라도 미정의이면 `NA` |
| planned_rows, valid_pairs, missing_pairs | 온도 비교 예정 행·실측과 예측 모두 유한한 행·누락 쌍 수. 상관표 missing_pairs는 해당 속성 쌍의 누락 수 |
| bias_c, mae_c, rmse_c | 추정−실측의 평균, 절대오차 평균, 제곱오차 평균의 제곱근, °C |
| predictor, target, method, correlation | 상관 입력·대상·계산 방법·계수. 분류표 method는 기존 여섯 방법 이름 |
| segment_pairs, unique_weather_groups | 상관 계산 구간 쌍 수와 서로 다른 공유 기상 그룹 수. 독립 표본 수로 간주하지 않음 |
| status, independent_samples, causal_effect | 상관 계산 가능 여부와 해석 한계. 상수·3쌍 미만은 `NA`, 독립성과 인과효과는 주장하지 않음 |
| sampling, official_chainage_verified | 잘린 선의 중간점 표집과 공식 이정 대조 여부 |
| verified_ice_probability, risk_grade | 검증된 결빙확률 여부 False, 최종 위험등급 미정 `NA` |
| official_score, official_competition_score | False. 개발 결과를 공식 점수로 표시하지 않음 |
| confirmed_missed_day_policy | 미탐일 Precision 제외·Recall/F1=0 규약 반영 여부 |
| minimum_coverage_officially_confirmed, false_alarm_only_recall_explicitly_answered | 부분 날짜 최소 관측량·오경보만인 날 Recall의 공식 확정 여부. 현재 False |

## 구간별 10분 결과 읽기

같은 기상을 공유하는 구간을 10분마다 중복 저장하면 43,752,960행이 됩니다. 연결키를 보존한 두 CSV로 동일한 결과를 복원합니다. 전체 확장 전에 원하는 규모·겨울·노선을 선택합니다. 500m와 1km 결과를 합쳐 독립 구간으로 세지 않습니다.

```python
import pandas as pd
index = pd.read_csv('point_prediction_index.csv', dtype={'id': str, 'prediction_group': str})
groups = pd.read_csv('prediction_groups_10min.csv.gz', dtype={'prediction_group': str},
                     na_values=['NA'], float_precision='round_trip', parse_dates=['time'])
selected = index.query("kind == 'segment' and scale_m == 500 and winter == 2024").head(1)
result = selected.merge(groups, on=['prediction_group', 'winter'], validate='one_to_many')
assert len(result) == 17280
```

일별 결과는 index와 `prediction_group_daily.csv`를 같은 키로 결합합니다. `id`가 문자열이어야 숫자처럼 보이는 식별자도 보존됩니다. 보호 지점 실제 정답은 포함하지 않으며 CSV에서 보호 성능 지표를 새로 계산할 수 없습니다.

## 평가·상관 해석의 한계

무결빙·무예측일은 일별 F1에서 제외됩니다. 따라서 방법마다 F1 평균의 날짜 분모가 다릅니다. 지표값만 순위화하지 말고 포함 날짜 수·오경보·미탐을 같이 봅니다. 기존 기준선 표는 기상 결측 시 단순 규칙을 0으로 처리한 기존 비교 정책을 그대로 보존합니다. 예측 상태를 가진 제출 10분 CSV의 결측 정책과 혼동하지 않습니다.

상관표의 대상은 **모델이 추정한 겨울 평균 온도와 저온 수분 조건 노출률**입니다. 관측 Ice나 사고율이 아닙니다. 구간 중간점에 같은 기상 그룹 예측을 배정하므로 교량·터널 비율과의 상관으로 시설 효과를 입증할 수 없습니다. p값·유의성·사고 위험등급을 생성하지 않습니다. 시설 영향을 고도화하려면 시설 실측 범위·도로 물성·제설·교통량 자료와 별도 공간 검증이 필요합니다.
