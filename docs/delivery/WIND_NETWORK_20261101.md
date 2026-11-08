# 주변 AWS를 이용한 풍속 추정 실행과 입력 계약

2026-11-01. 풍속 MAE를 지역 전체 제외에서 0.563455→0.499955m/s로 11.27%, 지역·겨울 동시 제외에서 0.567465→0.508379m/s로 10.41% 더 낮춘 69특성 모형입니다. AWS 우선 대비 감소는 49.13%입니다. 같은 개발 4지역·두 겨울 137,498쌍의 반복 검증이며 공식 성적이나 새로운 독립 표본이 아닙니다. [설계·전체 비교·출처](../research/WEATHER_NETWORK_20261101.md)

## 독립 실행 묶음

로컬 최종 폴더는 `outputs/private/wind_network_supplement_20261101_v2`이며, v12 모델자료 안에서는 `research/wind_network_supplement`입니다. 허용 기상 지점 13곳의 학습 447,628행, 69특성 모형, 예제, 소스, 환경과 노트북 3셀을 포함합니다. 학습 행·모형·예측은 GitHub에서 제외합니다. 저장소 복제만으로 전체 학습을 재현할 수 있다고 표현하지 않습니다.

```powershell
cd research/wind_network_supplement
python -m pip install -r requirements-notebook.txt
python scripts/predict_wind_network.py --bundle . --input data/weather_example.csv --aws-input data/aws_example.parquet --points data/points_example.csv --output my_wind.csv
python scripts/check_notebook.py notebooks/wind_network_review.ipynb --timeout 600
python scripts/retrain_wind_network.py --bundle . --output my_refit
```

노트북은 API·실제 CLI·전체 447,628행 재학습을 수행합니다. 세 경로의 예측 432행과 전체 과거/예제 원천 문맥의 결과가 정확히 일치했습니다. 연구의 36개 제외 모형을 모두 재학습하거나 원천 특성을 재구축하려면 원 작업 공간의 추가 자료가 필요합니다.

## 입력과 결측

| 입력 | 열·정의 |
| --- | --- |
| 기본 기상 CSV | station·time과 기존 28개 기상·시간·거리·태양 입력. 도로 정답 열 금지 |
| 도로 좌표 | station·lat·lon. 같은 지점 중복 금지, 유효 위경도 |
| AWS 관측 | station·source_time·air_temp·humidity·wind_speed·rain_15m·dewpoint |
| AWS 좌표 | 포함된 34지점 카탈로그. 관측이 없는 지점도 후보 자리 유지 |
| 시각 | KST의 정확한 10분 목표 시각. 시간대가 있으면 KST로 변환 |
| 원천 사용 | 목표보다 엄격히 과거 15분 이내. 같은 시각·미래·오래된 관측 제외 |
| 가용성 | ASOS 풍속이 없거나 유효기간 밖이면 NA. 기본 AWS가 15분을 넘으면 ASOS 기준으로 복귀 |

최대 4곳·50km·거리 하한 1km·거리 제곱 역수를 사용합니다. 변수별 결측을 제외해 가중치를 다시 합계 100%로 맞춥니다. 관측이 없는 지점은 빈 배열로 두며 먼 관측소를 대신 올리거나 가상의 시각·값을 만들지 않습니다. 카탈로그 밖 번호, 중복 시간, 무효 물리값과 모델 해시 변경은 거부합니다. 출력의 가중 거리·관측소 범위·유효 개수는 입력 진단이며 오차·예측구간·확률이 아닙니다.

기존 기온·안정화 습도·노면온도 v3·결빙 v2·F1 명시 프로필은 유지합니다. **기존 843구간 풍속 지도는 이전 모형이며 새 모형의 적용 지도로 표시하지 않습니다.** 보호 3곳과 이미 평가한 별도 4곳의 정답을 새 학습·선택·평가에 쓰지 않았습니다.
