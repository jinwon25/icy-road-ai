# 주변 RWIS를 이용한 미관측 지점 노면온도 추정 기준선

2026-09-23 개발용 실행. 공식 검증 RWIS **12410·33411·23402는 목표와 참조에서 모두 제외**했다. 아래는 개발용 14개 RWIS를 각각 보류한 공간 일반화 기준선이며, 공식 평가나 미래 조기예보 점수가 아니다.

## 입력과 검증

각 목표 RWIS에서 **같은 고속도로 노선의 가장 가까운 다른 개발용 RWIS**를 하나 고른다. 목표 시각보다 엄격히 이전이고 최대 30분 전인 참조 노면온도를 그대로 예측값으로 쓴다. 목표 지점의 관측값·지연값은 참조할 수 없고, 보호 3개소도 참조 후보에 없다. 비교 대상은 기존 14회 관측소 보류 검증의 과거 AWS·ASOS Ridge 노면온도 예측이다. 세 번째 비교는 두 예측을 **고정 1:1로 평균**한 비학습 융합 기준선이다. 가중치 탐색이나 보류 지점별 편향 보정은 하지 않았다.

기상 Ridge와 같은 목표 시각 483,095개 중 참조 RWIS가 30분 이내에 있는 483,061개(99.993%)를 **모든 모델에 동일하게** 적용했다. 참조 시각은 10분 전 482,992개, 20분 전 54개, 30분 전 15개다. 최근접 같은 노선 참조 RWIS 거리는 지점별 4.0~23.9km였다. BIAS는 예측−관측으로 정의했다. 저장 위치는 모두 `outputs/private/neighbor_rwis/`다.

| 입력 | 관측소 평균 MAE °C | 평균 RMSE °C | 실측 −2~2°C 평균 MAE °C | 기상 단독보다 MAE 개선 지점 |
| --- | ---: | ---: | ---: | ---: |
| 과거 AWS·ASOS Ridge | 1.738 | 2.280 | 1.441 | 기준 |
| 같은 노선 다른 RWIS의 과거 노면온도 | 1.313 | 1.957 | 1.093 | 13/14 |
| 고정 1:1 평균 | **1.286** | **1.794** | **1.039** | **14/14** |

고정 평균의 관측소 평균 MAE는 기상 단독보다 약 **26.0% 낮다**. 이는 주변 RWIS의 과거 관측을 실사용 입력으로 확보할 수 있을 때, 미관측 지점 노면온도 추정에 실질적 정보가 있음을 보여준다. 고정 평균은 주변 RWIS 단독보다 7/14곳에서만 좋아서 모든 지점의 최선 방법은 아니다. 특히 Ice 관측이 가장 많았던 12210은 주변 RWIS 단독 MAE 1.944°C가 기상 Ridge 1.572°C보다 나빴다. 두 값을 평균한 경우에는 1.497°C였다. 그 지점의 참조 거리는 20.3km이고 주변 RWIS 단독 BIAS는 −1.703°C다. 보류 지점 정답으로 이 편향을 보정하지 않았다.

같은 공간 보류 예측을 겨울별로 **사후 분해**하면 첫 겨울(2024-11~2025-02)의 관측소 평균 MAE는 기상 1.680, 주변 RWIS 1.190, 고정 평균 1.197°C였고, 둘째 겨울(2025-11~2026-02)은 각각 1.796, 1.435, 1.375°C였다. 고정 평균이 기상 단독보다 좋은 지점은 첫 겨울 14/14, 둘째 겨울 13/14다. 이는 **겨울 간 선행 학습→후행 검증이 아니다**. 기상 Ridge의 각 공간 fold는 두 겨울을 함께 학습했으므로 시간 일반화 수치로 표현하면 안 된다. 세 노선 평균에서도 고정 평균이 기상 단독보다 낮았지만, 각각 개발 지점이 5·5·4개뿐이다.

## 해석과 다음 단계

이번 결과는 도로기상 관측망의 **동적 주변값**이 유용하다는 근거다. 교량·터널 정적 거리의 추가 효과는 별도 [시설·이력 실험](FACILITY_HISTORY_REPORT.md)에서 악화됐고, 아직 도로·지형 정보가 주변 기상 대비 추가 이익을 주는지 전체적으로 답하지는 못했다. 직접 Ice 분류기는 여전히 실사용 불가이므로 이 노면온도 결과를 Ice 판정 성능으로 대체하지 않는다.

운영 적용 전에는 참조 RWIS의 실제 발표 지연, 통신 장애, 노선 전체 1km 구간에서의 참조 거리·범위 밖 여부를 확인해야 한다. 본 기준선은 참조 RWIS를 찾을 수 없는 시각을 34개 제외했으므로, 운영 파이프라인에서는 기상 단독으로 돌아가는 대체 규칙이 필요하다. 다음 학습 모델은 외부 보류 지점뿐 아니라 **내부 임계값 검증의 보류 지점도 RWIS 참조 집합에서 제거**해야 한다. 그 규칙이 없으면 주변 RWIS 융합 모델의 성능이 부풀려질 수 있다. 보호 3곳은 모델·참조 규칙·임계값·평가 정책을 고정한 뒤 한 번만 열어야 한다.

재실행: `python scripts/baseline_neighbor_rwis.py --smoke` → `python scripts/baseline_neighbor_rwis.py` → `python scripts/diagnose_neighbor_rwis.py` → `python scripts/check_notebook.py --run-stage neighbor_rwis_diagnostic`. 단일 노트북은 [analysis_review.ipynb](../notebooks/analysis_review.ipynb)이다.

Additional spatial limitation: nearest reference is chosen by straight-line station distance within the same route name. Carriageway direction, branches, and along-road chainage are not yet modeled. This is appropriate for a station benchmark only; a segment map needs a route-network assignment and reference-distance audit.
