# 개발용 기상 결합 기준 실험 — 2026-09-23

공식 보호 RWIS 12410·33411·23402는 모든 특징·학습·평가에서 제외했다. 개발용 14개 RWIS의 노면온도를 추정하는 **공간 일반화** 실험이며, 미래 시점 조기예보 성능이나 공식 최종 점수가 아니다.

## 입력과 실행

`scripts/build_weather_features.py`는 각 RWIS에서 가장 가까운 AWS와 ASOS 한 곳을 고른다. 관측값은 목표 시각보다 **엄격히 이전**, 최대 60분 전 자료만 후방 결합한다. 제공 AWS 파일은 파일명 날짜의 KST 행만 유지하고 원본을 수정하지 않는다. AWS 기온·습도·풍속·이슬점·직전 15분 강수, ASOS 기온, 관측 경과시간·거리, 시간대·연중 주기만 사용한다. 노면온도 실측·지연값, RWIS 지점 ID, 도로·지형 특징은 입력이 아니다.

[기상청 AWS 설명](https://www.weather.go.kr/wnuri_help/html/observation/aws-table.jsp)은 15분 강수가 해당 시각 이전 15분 누적량이고 일강수는 00:01에 초기화된다고 설명한다. 따라서 초기 실험은 일 누적량을 차분하지 않는다. [기상청 ASOS 설명](https://data.kma.go.kr/data/grnd/selectAsosRltmList.do?pgmN=)과 제공 자료를 대조했지만, 제공 ASOS CSV의 시간대와 실제 발표 지연은 아직 확정하지 못했다. **동일 시각 자료를 쓰지 않는 10~60분 후방 결합은 잠정 보수적 설정**이다.

이틀 작은 실행에서 흐름을 확인한 뒤 전체 개발 자료로 특징을 한 번 생성했다. 전체 목표 483,777시점 중 과거 AWS 기온 340,453시점(70.38%), 과거 ASOS 기온 483,095시점(99.86%), 둘 다 339,816시점에서 확보됐다. AWS 연결률은 지점별 약 52~82%다. 원천별 거리와 지점별 연결률은 Git 제외 경로 `outputs/private/weather_features/station_coverage.csv`에 있다.

고정된 Ridge(α=100) 한 개를 비교 모델로 사용했다. 결측 중앙값·결측 표시자·표준화는 **각 LOSO 회차의 13개 학습 지점에서만** 적합했다. 분류나 임계값 탐색은 하지 않았다. 비교 기준은 같은 학습 지점의 노면온도−ASOS 기온 중앙값으로 보정한 기존 ASOS 모델이다. 두 방법 모두 ASOS가 유효한 동일한 483,095시점에서 평가했다. BIAS는 예측−관측이다.

| 지점 평균 지표 | ASOS 보정 기준 | 기상 융합 Ridge |
| --- | ---: | ---: |
| MAE (°C) | 2.174 | 1.771 |
| 개선폭 | 기준 | 0.403°C, 18.54% |
| 관측 노면온도 −2~2°C 구간 MAE (°C) | 1.639 | 1.471 |

전체 MAE는 14곳 중 13곳에서 개선됐지만 **12209에서는 2.262→2.460°C로 악화**됐다. −2~2°C 진단 구간은 111,763시점이며 지점 4곳(12103·12209·23204·23403)에서 MAE가 악화됐다. 이 구간은 관측 타깃으로 사후 선택한 실패 분석 범위이지 모델 입력 또는 공식 결빙 지표가 아니다. 지점별 표와 OOF 예측은 `outputs/private/weather_ridge/`에만 있다.

## 겨울 간 시간 일반화 보조 검증

`outputs/private/validation/splits.json`의 기간대로 첫 겨울(2024-11-01~2025-02-28)에만 적합하고 둘째 겨울(2025-11-01~2026-02-28) 241,201시점을 평가했다. 같은 14개 RWIS가 두 겨울에 모두 있으므로 **새 관측소 일반화 성능과 합치지 않는다**. 둘째 겨울의 지점 평균 MAE는 ASOS 보정 2.215°C, 기상 Ridge 1.766°C였고 14곳 모두에서 Ridge가 낮았다. 실험 코드는 `scripts/evaluate_weather_temporal.py`, 지점별 결과는 `outputs/private/weather_temporal/`에 있다. 이 결과는 관측소 고정 조건의 겨울 간 이전 가능성만 보인다.

## 해석과 다음 결정

OOF 예측을 재학습 없이 겨울·AWS 연결 여부로 나누면 12209의 2025~26 겨울 AWS 누락 5,851시점에서 MAE가 ASOS 2.457°C, 기상 Ridge 2.924°C다. AWS 연결 11,422시점에서도 2.377→2.564°C로 악화돼 누락만이 원인은 아니다. 전체 진단표는 `outputs/private/weather_ridge/winter_availability_diagnostic.csv`에 있다. 개발용 RWIS 14곳은 해당 도로 중심선에서 중앙값 16.3m, 최대 22.3m로 정합했다.

AWS·ASOS 기상정보를 함께 쓰면 단순 ASOS 보정보다 노면온도 추정이 좋아졌다는 개발용 근거는 얻었다. 다만 가까운 AWS가 누락될 때 정적 최인접 하나만 고르는 방식은 취약하며, 결빙 전환에 중요한 0°C 부근의 일부 지점이 악화됐다. 다음 단계는 **같은 LOSO와 같은 분모**를 유지하며 (1) 다른 AWS로의 가용성 기반 대체, (2) 교량·터널·고도 등 배포 가능한 정적 특징의 추가 효과를 순서대로 검증한다. 특징 중요도를 위험도 배점으로 직접 바꾸지 않는다.

재실행:

```powershell
python scripts/build_weather_features.py --limit-days 2
python scripts/baseline_weather_ridge.py --smoke
python scripts/build_weather_features.py
python scripts/baseline_weather_ridge.py
python scripts/diagnose_weather_ridge.py
python scripts/evaluate_weather_temporal.py
python scripts/audit_station_road_alignment.py
python scripts/check_notebook.py
```

Python 3.11.2, pandas 2.2.3, NumPy 2.2.6, scikit-learn 1.6.1, pyarrow 20.0.0. 외부 관측 데이터는 수집하지 않았다. 자세한 선행근거는 [외부 자료 목록](REFERENCES.md)에 있다.

추가로 상위 3개 AWS의 과거 유효 관측 가용성을 감사했다. 483,777시각 중 434,253시각이 연결 가능했으며 실제 모델 정확도는 아직 재평가하지 않았다. 사례별 우선순위, 공식 문헌과 다음 비교 조건은 [후속 실험 근거](FOLLOWUP_EVIDENCE.md)에 있다.


## 대체 AWS 입력의 개발용 비교

동일한 개발 RWIS 14개소·동일한 483,095시각·동일한 Ridge 설정에서 최근접 AWS와 상위 3개 중 과거 가용 AWS를 비교했다. 지점 평균 MAE는 1.771→1.738°C, RMSE는 2.319→2.280°C였다. 14개 지점 모두 전체 MAE가 낮아졌지만 12209는 2.460→2.406°C로 개선 후에도 ASOS 보정 기준 2.262°C보다 나빴다. 12209의 예측−관측 BIAS는 +2.084→+1.995°C이며, −2~2°C 구간의 23202는 1.004→1.016°C로 악화했다. 상세한 공식 문헌 연결과 실험 결정은 [후속 사례·근거](FOLLOWUP_EVIDENCE.md)에 있다. 이는 개발용 노면온도 비교로 Ice 판정 점수나 공식 최종 평가가 아니다.

