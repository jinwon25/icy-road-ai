# 도로 기상 보완을 통합한 v9 검토 묶음

v9는 기온·습도·풍속의 별도 추정 모델과 두 겨울 500m 구간 결과를 기존 v8에 추가합니다. 기존 노면온도 v3·결빙 판정 v2·완료 평가·v7/v8 ZIP은 보존합니다. 대회에 실제 업로드한 결과물은 아닙니다.

## 제출 칸별 경로

| 제출 칸 | 단일 폴더 ZIP |
| --- | --- |
| 문서자료 | `outputs/private/submission_channels_20261031_v9/icy_road_documents.zip` |
| 모델자료 | `outputs/private/submission_channels_20261031_v9/icy_road_model.zip` |

두 ZIP의 최종 파일 수·바이트·SHA-256·검증 상태는 같은 폴더의 `submission_receipt.json`에서 확인합니다. 상태가 `two_channel_archives_verified`이고 실제 ZIP의 해시가 일치하는 파일을 기준으로 사용합니다. 과거 v8 ZIP과 혼용하지 않습니다. 접수 개시는 확인했지만 제공 공지 본문에는 마감 날짜가 없습니다.

## 확인한 개선

| 목표 | 비교 기준 MAE | 새 모형 MAE | 변화 |
| --- | ---: | ---: | ---: |
| 노면온도 °C | 1.326890 | 1.145698 | 13.66% 감소, 기존 v3 유지 |
| 도로 기온 °C | 1.699319 | 1.323764 | 22.10% 감소 |
| 도로 상대습도 %p | 6.530284 | 5.875898 | 10.02% 감소 |
| 도로 1분 풍속 m/s | 0.982751 | 0.563455 | 42.67% 감소 |

노면온도는 개발 9곳, 세 기상 목표는 기상 정답이 있는 개발 4곳에서 해당 지역 전체를 학습에서 제외하고 두 겨울을 비교했습니다. 세 기상 목표의 기준은 신선한 AWS를 우선하고 ASOS로 대체한 값입니다. 같은 지역을 여러 번 검토한 개발 결과로 공식 점수·새 독립 성능이 아닙니다.

세 목표는 두 겨울 각각과 학습 중앙값·잔차 상수 기준선에도 개선했습니다. 일부 지역·지표의 악화와 풍속 R² 0.268789를 함께 기록했습니다. 개선된 기온의 0°C 결빙 정책은 F1 하락·기존 38사건 손실로 미채택했습니다. 현재 결빙 F1 0.026554는 기온 기준선 0.036601보다 낮아 별도 과제로 남습니다.

## 새 결과물과 실행

- `reports/analysis_report_v9.pdf`: 17쪽 통합 보고서. 도로 기상 개선·단순 대조·실패한 결빙 전이·기상 지도와 한계를 포함합니다.
- `research/weather_observation_supplement/`: 세 저장 모델·448,298행 학습 자료·환경·재학습 및 추론 노트북. 각 목표의 유효 학습 행 수는 다릅니다.
- `research/latest/road_weather_review_20261031_v1/`: BIAS·MAE·RMSE·상관 126행 CSV와 기상 검증 4곳의 10분 예측.
- `research/latest/weather_segment_projection_20261031_v1/`: 843구간·두 겨울 1,686행 요약, 202,320행 일별 평균·유효 수, GeoPackage 두 레이어.
- `notebooks/weather_review_v9.ipynb`: 포함 집계·지도·해시를 검토하는 노트북.
- 기존 실행 노트북·공식 목록 오프라인 화면·실제 데모영상·CSV·Shapefile도 유지합니다.

기상 모형은 별도 위치로 복제해 실제 CLI 144행 일치와 Jupyter 3코드 셀·전체 세 모델 재학습 일치를 확인했습니다. 최종 통합 묶음의 실행 검증은 `validation/v9_delivery.json`을 기준으로 확인합니다. 새 예제 144행은 독립 성능 평가가 아닙니다.

모델자료 ZIP을 해제하고 최상위 README의 순서로 실행합니다. Windows·Python 3.11.2·CPU에서 검증하며 GPU·외부 AI API·인증정보가 필요하지 않습니다. 새 보완 모형의 기본 명령은 해당 보완 폴더 안에서 다음과 같습니다.

```powershell
python -m pip install -r requirements.txt
python scripts/predict_weather_supplement.py --model model --input data/inference_example.csv --output my_prediction.csv
python scripts/retrain_weather_supplement.py --bundle . --output my_refit
```

## 지도와 해석 범위

구간 기상 29,134,080개 10분 행은 원 비공개 작업 공간에 보존하고, ZIP에는 일별·겨울별 통계와 GIS를 넣습니다. 전체 구간 입력을 다시 구축하려면 원 작업 공간이 필요하지만 최종 세 기상 모형의 재학습·예제 추론은 포함 자료로 가능합니다.

학습에 등장하지 않은 ASOS 172 출처와 학습 입력 범위 이탈을 표시합니다. 같은 변수의 두 겨울은 동일 색 범위로 비교합니다. 기존 노면온도·저온 수분 노출을 정확히 보존하며 새 위험등급이나 결빙확률을 만들지 않았습니다. 추정값끼리의 상관·지도 해상도를 실제 결빙의 인과효과나 독립 관측으로 해석하지 않습니다.

원 연구는 [기상 모형 연구 기록](../research/ROAD_WEATHER_TRANSFER_20261031.md), 실행은 [보완 묶음 안내](WEATHER_SUPPLEMENT_20261031.md)를 참고합니다. AI의 작업·검산과 참가자의 직접 판단은 [AI 활용 기록](../../AI_USAGE.md)에 구별해 기록합니다.
