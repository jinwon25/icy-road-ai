# 결빙 실행 프로필: F1 우선 후보와 기존 v2

F1 우선으로 검토할 수 있도록 이미 알려진 `ASOS 기온 ≤ 0°C` 기준선을 명시적 실행 후보로 제공합니다. 기존 v2의 모델·파일·예측도 보존합니다. **새로운 모델 개선이나 보호 지점의 성능 확인은 아닙니다.** 같은 개발 자료에서 더 높은 F1을 확인한 선택과 겨울·정밀도에 대한 손해를 함께 제시합니다.

| 같은 개발 9곳·두 겨울 | 기존 v2 | F1 우선 검토: 기온 0°C |
| --- | ---: | ---: |
| 일별 지점 F1 | 0.026554 | 0.036601 |
| 정밀도 | 0.040055 | 0.033386 |
| 재현율 | 0.739628 | 0.966799 |
| 2024/25 F1 | 0.030187 | 0.071179 |
| 2025/26 F1 | 0.009466 | 0.001444 |
| 386개 관측 사건 중 탐지 | 178 | 330 |

기존의 모든 겨울·정밀도·사건 비악화 조건은 연구자의 자체 기준이며 공식 배점과 같지 않습니다. F1 우선 후보는 통합 F1·재현율이 높지만 정밀도와 둘째 겨울 F1은 낮습니다. 이 단순 규칙의 높은 평균을 새로운 독립 일반화나 현장 안전성으로 설명하지 않습니다. 지역 제외 검증과 반복 선택의 한계는 [통합 보고서](ANALYSIS_REPORT_V11_20261101.md)를 참고합니다.

## 실행

모델자료 루트에서 아래 두 경로를 명시적으로 선택합니다. 기존 출력이 있으면 새 이름을 사용합니다. 기본 `code/predict.py`는 보존된 기존 v2 동작입니다.

```powershell
python scripts/predict_competition_profile.py --bundle . --input data/weather_example.csv --output local_review/score_priority.csv --icing-profile score_priority_asos_zero --output-start 2024-12-15 --output-end 2024-12-16
python scripts/predict_competition_profile.py --bundle . --input data/weather_example.csv --output local_review/preserved_v2.csv --icing-profile preserved_v2 --output-start 2024-12-15 --output-end 2024-12-16
```

원 작업 저장소에서는 `--bundle outputs/private/submission_candidate_20261101_v10`으로 지정합니다. 입력은 원 기상만 허용하며 노면온도·Ice 정답 열을 거부합니다. 과거 온도 특성을 먼저 계산하고 마지막에 출력일을 선택합니다. 설치 후 외부 API·인증정보가 필요하지 않습니다.

## CSV와 보호 예측

| 열 | 뜻 |
| --- | --- |
| `predicted_ice` | 명시한 프로필의 0/1/NA. 결빙확률이 아님 |
| `icing_policy` | F1 후보는 `score_priority_asos_zero_v1` |
| `icing_reference_temperature_c` | 이 프로필이 실제 사용한 ASOS 기온 |
| `icing_reference_component_spread_c` | 단일 ASOS 입력이므로 유효할 때 0. 예측오차 0을 뜻하지 않음 |
| `preserved_v2_predicted_ice` | 보존한 기존 v2 판단 |
| `preserved_v2_condition_evidence` | 기존 온도·수분 근거 |
| `preserved_v2_reference_temperature_c` | 기존 v2의 기준 노면온도 |
| `preserved_v2_reference_component_spread_c` | 기존 v2 구성 모형 차이 |

추정 노면온도 v3·현재 습도·기온·풍속 모형은 바꾸지 않습니다. 원 v2 판단이 결측인 행은 단순 규칙에서도 결측으로 유지합니다. 보호 3곳·두 겨울의 **103,680행에서 온도·행키와 18NA를 정확히 보존**했습니다. 보호 실측 정답을 읽거나 보호 점수를 계산하지 않았습니다.

모델자료의 `research/latest/competition_profile_review_20261101_v1/protected_score_priority_predictions.csv.gz`가 별도 후보입니다. `exports/protected_predictions_10min.csv`는 보존된 기존 v2입니다. 두 결과를 정책 식별자 없이 섞지 않습니다. 공식 고정 CSV 양식으로 주장하지 않으며 실제 업로드를 뜻하지 않습니다.

실제 CLI 두 경로의 예제 144행을 각각 정확히 대조했습니다. 근거는 `competition_profile_review_20261101_v1/summary.json`, `notebooks/followup_review_v11.ipynb`에서 검토합니다. 전체 최종 모형의 재학습은 기존 포함 자료와 노트북을 그대로 사용할 수 있습니다.
