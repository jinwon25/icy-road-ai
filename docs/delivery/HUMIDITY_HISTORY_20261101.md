# 과거 이력 습도 모형의 실행·전체 재학습

**새 습도 모형은 두 검증과 별도 위치 실행을 통과했습니다.** 현재 묶음은 `outputs/private/weather_history_supplement_20261101_v2/`입니다. 초기 v1은 문맥에 따른 부동소수점 차이가 발견되어 채택하지 않았습니다. [설계·실패·최종 수치](../research/WEATHER_SPACE_TIME_20261101.md) · [v10 구성](REVIEW_BUNDLE_V10_20261101.md)

| 검증 | 기존 MAE | 새 MAE | 개선 |
| --- | ---: | ---: | ---: |
| 지역 제외, %p | 5.875898 | 5.686973 | 3.22% |
| 지역·겨울 동시 제외, %p | 6.008156 | 5.834129 | 2.90% |

개발 4지역·두 겨울·공통 유효 137,450쌍의 반복 개발 결과입니다. 새로운 독립 지역이나 공식 보호 지점 성적이 아닙니다. 서천 MAE는 1.15% 악화했고 서상의 양의 편향도 남습니다. 개선된 습도를 결빙 F1 개선으로 해석하지 않습니다.

## 실행

묶음 안을 작업 디렉터리로 사용합니다. Python 3.11·CPU 환경이며 GPU·인증정보·외부 AI API가 필요하지 않습니다.

```powershell
python -m pip install -r requirements.txt
python scripts/predict_weather_history.py --input data/weather_context_example.csv --output my_prediction.csv --output-start 2024-12-15 --output-end 2024-12-16
python scripts/retrain_weather_history.py --bundle . --output my_history_model
```

예제는 세 지점의 48시간 기상 864행을 입력해 12월 15일 432행을 산출합니다. 출력 이름이 이미 있으면 새 이름을 사용합니다. `data/expected_predictions.csv`와 비교할 수 있습니다. 전체 적합 모형의 학습 범위 내 재현 예제이므로 이 자료로 정확도를 평가하지 않습니다.

`notebooks/weather_history_supplement.ipynb`의 기본 3코드 셀은 학습 자료·제외 지표·실제 추론을 확인합니다. `RUN_REFIT=True`로 바꾸면 포함된 유효 447,794행으로 전체 습도 모형을 재학습하고 같은 예측과 정확히 대조합니다. 기존 모형은 덮어쓰지 않습니다.

## 과거 입력을 제공하는 방법

출력일 앞의 최소 24시간 기상을 포함합니다. 추론 전에 출력 날짜로 입력을 자르면 과거 이력을 잃습니다. 함수와 CLI는 전체 문맥에서 계산한 뒤 출력 구간을 선택합니다. 같은 창 앞에 더 오래된 자료를 붙여도 최종 예측은 일치하도록 독립 창 합산을 사용합니다.

| 출력 | 뜻 |
| --- | --- |
| `estimated_humidity_pct` | 0–100%로 제한한 습도 추정값. 현재 입력 부족은 NA |
| `humidity_history_input_slots_24h` | 같은 도로의 직전 24시간에 제공된 10분 입력 행 수 |
| `humidity_history_status` | `complete_24h` 또는 `partial_24h`. 기상 독립 관측 수·정확도 아님 |
| `humidity_history_outside_training_range` | 학습 82특성의 최솟값·최댓값 범위 이탈. 오차·신뢰구간 아님 |

ASOS는 0분 초과 60분 이하, AWS는 0분 초과 15분 이하의 과거 관측입니다. 실제 서비스의 공개 지연까지 검증한 실시간 예보는 아닙니다. 실제 습도·노면온도·결빙 정답을 입력하면 거부합니다. 기온·풍속은 보존한 기존 모형으로 산출하며 습도만 교체합니다.

## 확인한 재현 범위

별도 폴더로 복제한 실제 CLI 432행, Jupyter 3코드 셀과 습도 전체 재학습이 일치했습니다. 48시간과 더 긴 전체 과거를 준 경우의 선택일 습도 차이는 0입니다. 원 묶음 파일과 기존 기온·풍속 모형 바이트도 보존했습니다. 실행 영수증은 `outputs/private/weather_history_supplement_validation_20261101_v2/receipt.json`입니다.

제출 ZIP에서는 `research/weather_history_supplement/`에 포함합니다. 원 68개 비교 모형 전체를 재실험하려면 원 작업 공간이 필요하지만, 최종 습도의 전체 재학습과 예제 추론은 포함 자료로 가능합니다. 대회 자료·모형의 공개 재배포 허용을 가정하지 않습니다.
