# 현재 진행 상태 — 2026-10-02

현재까지 끝낸 일, 남은 문제, 다음 작업을 정리합니다. 상단이 최신 개발 상태이며 과거 실험 기록은 아래 접힌 부분에서 확인할 수 있습니다.

[문서 목록·용어 풀이](README.md) · [프로젝트 소개](../README.md)

## 수정본 전 후속 작업 완료

[수정본 전 작업 보고서](PRE_CORRECTION_WORK_REPORT.md)에 주변 RWIS 정보 감사·내부 참조 제외·기존 오경보 진단·정적 도로 구간을 정리했다. 직전 주변 Ice는 실제 결빙 239개 중 1개, 과거 60분 이력은 6개만 적중했다. 습도는 외부 평가 타깃의 Ice 239개 모두에서 확보됐으나, 내부 제외를 적용한 수분 참조 546조합 중 47조합에는 같은 노선의 참조가 없었다. 결측을 다른 검증 지점으로 채우지 않는다.

정적 중심선 275.889km를 최대 1km 구간 467개로 만들고 Shapefile·GPKG 저장/재읽기를 확인했다. 위험 점수는 전부 미산정이며 공식 이정·방향별 최종 위험지도가 아니다. 구간/오경보 결과를 모델 성능 개선으로 주장하지 않는다.

## 추가 완료: 결빙 비선형 모델 검증

[상세 보고서](ICE_NONLINEAR_REPORT.md)에 고정 HGB 모델의 전체 14개 외부 LOSO·각 3개 내부 관측소 분할 결과를 기록했다. 동일 유효 정답 483,652행·Ice 239개를 유지하고 임계값은 내부 OOF에서만 정했다.

- 로지스틱 TP21/FP955/FN218 대비 HGB 10분 F1 정책 TP22/FP20,363/FN217.
- HGB 일평균 F1 정책 TP112/FP68,513/FN127. 적중 지점 1→8/11, 사건 18→105/215로 늘었지만 경보 품질은 부적합하다.
- 대회 집계에 가까운 개발 일평균 F1은 0.001087→0.005694. 이 후보는 다음 비교용으로 보존하되 최종 모델로 확정하지 않는다. 무결빙일 오경보는 130→1,345일이다.
- 완전 날짜 정책은 양성 239개 중 236개를 포함한다. 분모·지점 편차·사건·날짜 충족률 민감도와 탐색적 지점 재표집을 추가했다.
- 새 단계: ice_nonlinear, ice_nonlinear_comparison. 입력 감사·설정/분할 해시·내부 임계값 기록을 비공개 산출물로 저장했다.

최신 근거: [공식 변경사항](OFFICIAL_UPDATE_20261002.md), [공간·시간 검증](NEIGHBOR_TRANSFER_REPORT.md), [AI 활용 기록](../AI_USAGE.md).

- 운영진 Q&A: 지점별 일평균 후 3개 지점 평균, 실제·예측 모두 무결빙인 날 제외, 상태 0/-999 제외 권고가 확인됐다. 부분 관측 날짜·한쪽 지표만 미정의인 날·제출 스키마는 미확정이다.
- 운영진이 자정 행 변환 오류를 인정하고 10월 6일까지 정정·추가 자료를 예고했다. 현재 모든 실험은 20260915 구버전 결과다.
- 첫 겨울 다른 지점 학습→다음 겨울 미관측 지점 검증을 14회 완료했다. 동일 241,201행의 기상 MAE 1.82813°C, 고정 1:1 RWIS 혼합 1.38902°C. RWIS 30분/60분 지연 가정은 1.44411/1.57304°C다. 공식 점수나 결빙 분류 성능이 아니다.
- 원본 ZIP을 config/data_source.json의 이름·SHA256으로 고정하고 12개 로더의 임의 ZIP 선택을 제거했다. 기존 캐시를 새 데이터로 자동 재생성하는 기능은 아니다.
- 위험도 평가 기준표 이미지를 확보했다. 도로시설 41·기하구조 26·기후 6·교통운영 27점 체계를 두 겨울 관측만으로 재현하지 않는다.
- 노면온도 후보는 고정 혼합이며 직접 결빙 분류는 여전히 부적합하다. 보호 3개 지점은 타깃·학습·참조에서 제외했다.
- 최종 모델·추론 경로·공식 평가 CSV·500m/1km 지도·데모영상은 미완료다. 참가자 기여 검토도 남아 있다.

다음 우선순위: 수정본 확보 후 별도 복사본에서 원본 감사→전체 캐시 재생성→동일 분모 비교. 이후 개발 지점만 사용하는 결빙 분류 개선과 지형·구간 특징을 검증한다. 모델·평가를 고정하기 전 보호 지점은 열지 않는다.

재실행: `python scripts/evaluate_neighbor_transfer.py` 또는 `python scripts/check_notebook.py --run-stage neighbor_transfer`.

최종 검증: 단위 테스트 31개, 실제 Jupyter 커널 코드 셀 27개 통과. 실행 목록 40단계, 노트북 저장 출력 0개. 원본과 보호 지점 규칙을 유지했다.

---

<details>
<summary>이전 기록 펼치기 — 당시 가정·진행 상태 포함</summary>


### 프로젝트 진행 상태 — 2026-09-23

완료: 데이터 감사, 보호 관측소 분리·검증 규약, 개발용 EDA, ASOS/AWS 노면온도 추정, 개발용 직접 Ice 분류 기준선 2종과 10분 OOF·잠정 일별 지표, 단일 시각 Ice 전후 상태 감사. 공식 보호 지점 3곳의 동적 정답을 개발 분석에 사용하지 않았다. 현재 분류 기준선은 실사용에 부적합하며 도로·지형 결합 효과, 공식 최종 평가, 위험도 지도와 제출 파일은 아직 없다.

현재 핵심 결정:
- 원본은 ZIP에서 직접 읽고 `outputs/private/`에만 복원 가능한 산출물을 둔다. Git 초기 저장소는 없고 `.gitignore`를 준비했다.
- RWIS 12410·33411·23402와 ID 표기 변형은 최종 평가용으로 보호한다.
- 잠정 분류 타깃은 04 Ice만 양성, 정의된 다른 상태는 음성, 미정의는 제외다.
- 외부 공간 검증은 개발용 14개 지점의 LOSO 14회, 내부는 각 회차의 3개 관측소 그룹이다.
- 일별 평가는 운영진 답변 전 `config/evaluation.json`의 10분 단위·완전 날짜·미정의 `null` 설정을 **잠정 평가**로만 사용한다.
- 난수 시드 20260923. 현재 감사·분할·기준 모델은 결정적이다.

핵심 수치: 일별 CSV 720개, RWIS 587,520행/실측 17지점, ASOS 57,600행/10지점, AWS 1,077,128행/실측 34지점. 개발용 RWIS 유효 상태 483,652건 중 Ice 239건, 사건 215건이다. AWS에 완전 빈 행 285,823개와 자정 중복 2,776건이 있다. 도로 중심선은 EPSG:5179 선형 275.889km다.

첫 기준 모델은 과거 10–60분의 최근접 ASOS 기온으로 노면온도를 추정한다. 개발용 지점 평균 MAE는 직접 기준 2.394°C, 다른 학습 지점 중앙값 보정 2.174°C다. 보정이 4/14곳에서 악화됐고 ASOS 거리는 최대 39.7km다. 같은 483,095시점의 개발용 LOSO에서 기상 융합 Ridge는 지점 평균 MAE 1.771°C(18.54% 개선)였다. 14곳 중 1곳은 전체 MAE, 4곳은 관측 −2–2°C 구간 MAE가 악화됐다. 첫 겨울 학습→둘째 겨울 보조 검증은 같은 지점에서 2.215→1.766°C였으나 공간 점수와 구분한다. 이 값은 공식 점수가 아니며 도로 특징 효과도 아직 나타내지 않는다.

현재 쟁점: 필수 추정 변수·제출 스키마, 일별 평가 정의, 동일 시각 주변 자료 가용성은 미확인이다. AWS 자정 중복 891건의 원시 문자열 차이는 수치 표기 차이로 확인됐고 측정값 충돌은 0건이다. 개발 RWIS 14곳과 해당 노선 중심선의 거리는 최대 22.3m로 확인됐다. 자료 패키지에는 곡률 shapefile과 기존 결빙취약구간 목록이 없다. 198/215 결빙 사건이 단일 10분 시점이므로 라벨 안정성 점검이 필요하다.

다음 작업: AWS 결측 시 다른 지점을 쓰는 가용성 기반 대체를 검증하고, 중심선과 정합한 RWIS 지점에 교량·터널·DEM 정적 특징을 안전하게 추출할 수 있는지 점검한다. 그 후 동일 LOSO·동일 분모에서 기상만의 기준과 도로·지형 추가 모델을 비교한다. 공식 질문에 의존하는 평가는 잠정으로만 기록한다.

현재 재실행 명령:

```powershell
python scripts/audit_data.py
python scripts/audit_timestamps.py
python scripts/audit_aws_boundaries.py
python scripts/audit_aws_cleaning.py
python scripts/audit_spatial.py
python scripts/audit_station_road_alignment.py
python scripts/make_variable_dictionary.py
python scripts/eda_development.py
python scripts/make_splits.py
python scripts/baseline_asos.py --limit-days 2
python scripts/baseline_asos.py
python scripts/build_weather_features.py --limit-days 2
python scripts/baseline_weather_ridge.py --smoke
python scripts/build_weather_features.py
python scripts/baseline_weather_ridge.py
python scripts/diagnose_weather_ridge.py
python scripts/evaluate_weather_temporal.py
python -m unittest discover -s tests -v
```

실행 결과를 검토하는 단일 노트북은 `notebooks/analysis_review.ipynb`이다. `config/notebook_workflow.json`에 등록된 14개 단계를 `RUN_STAGES`로 선택해 실행할 수 있다. 23개 셀 중 13개 코드 셀을 실제 Jupyter 커널에서 순차 실행했고, 12개 테스트가 통과했다. `stdout=None` 재현 사례도 노트북에서 확인했다. `--run-stage validation_splits`로 선택 실행도 확인했다. 저장된 출력은 비워 두었다. 앞으로 새 단계마다 실행 목록과 노트북 결과 셀을 함께 갱신하고 `python scripts/check_notebook.py`로 검증한다.

상세 근거는 `DATA_AUDIT.md`, `VALIDATION_PROTOCOL.md`, `EDA_REPORT.md`, `BASELINE_REPORT.md`, `WEATHER_FUSION_REPORT.md`, `REFERENCES.md`, `QUESTIONS_FOR_ORGANIZER.md`, `EXPERIMENT_LOG.md`에 있다.

### 후속 사례·문헌 검토 및 AWS 대체 감사 — 2026-09-23 추가

- 개발용 14개 RWIS의 483,777목표 시각에서 기존 최근접 AWS 기온 340,453시각(70.38%), 상위 3개 AWS의 60분 이내 유효 과거 기온 후보 434,253시각(89.76%)이었다. 2·3순위 AWS가 93,732시각을 추가로 연결했고 49,524시각은 계속 결측이다. 이는 입력 가용성 감사이며 예측 오차 개선이 아니다.
- 12209는 25,894/34,560에서 30,192/34,560시각으로 연결 후보가 늘었다. 후보 AWS 거리는 4.45·5.21·17.96km여서 거리와 관측 나이에 따른 편향 검증이 필요하다.
- 스크립트 scripts/audit_aws_fallback.py 및 비공개 결과 outputs/private/aws_fallback/summary.json을 만들고, [후속 근거](FOLLOWUP_EVIDENCE.md)와 [문헌 목록](REFERENCES.md)에 FHWA·기상청 공식 사례와 원 논문을 연결했다.
- [분석 노트북](../notebooks/analysis_review.ipynb)에는 새 결과 셀과 실행 단계 aws_fallback을 연결했다. python scripts/check_notebook.py --run-stage aws_fallback에서 실제 Jupyter 커널 14개 코드 셀이 통과했고, 12개 단위 테스트도 통과했다. 저장 출력은 없다.
- 다음 작업은 상위 AWS 대체를 실제 기상 특징으로 구현하고 **기존과 동일한 LOSO·동일 평가 행**에서 노면온도 MAE·BIAS·RMSE와 12209 및 −2–2°C 실패 사례를 비교하는 것이다. 이후 시설·DEM의 좌표/수직 단위/시간 적합성을 확인해 정적 특징을 시험한다. 공식 보호 3개소·일별 F1 규정은 여전히 잠금/미확정이다.


### 대체 AWS 특징·LOSO 결과 — 2026-09-23 추가

- 2일 소규모 실행 후 전체 개발 자료에 상위 3개 중 가용 AWS 특징을 생성했다. 483,777시각 중 AWS 기온 434,253시각이 연결됐다. 작은 실행 감사 요약이 기존 smoke 요약과 충돌한 경로를 발견해 smoke_aws_fallback/으로 분리하고 기존 요약을 다시 생성했다.
- 동일한 483,095 평가 시각·14개 LOSO·고정 Ridge α=100에서 최근접 AWS 대비 대체 AWS 지점 평균 MAE 1.77055→1.73769°C, RMSE 2.31891→2.28003°C였다. 전체 MAE는 14/14개소 개선됐지만 12209는 ASOS 기준보다 나쁘고, −2–2°C의 23202는 악화했다. 공식 검증 결과가 아니다.
- scripts/build_aws_fallback_features.py, scripts/compare_weather_variants.py와 기존 Ridge 스크립트의 --variant fallback 옵션을 추가했다. [후속 근거](FOLLOWUP_EVIDENCE.md), [기상 실험 보고서](WEATHER_FUSION_REPORT.md), [단일 분석 노트북](../notebooks/analysis_review.ipynb)에 동일 분모 비교를 반영했다.
- 노트북 실행 목록 18단계, 코드 셀 15개가 실제 Jupyter 커널에서 통과했고 12개 단위 테스트가 통과했다. 결과 파일은 outputs/private/에만 있다.
- 다음 작업은 12209의 큰 양의 편향·시설 배치·센서 대표성과 23202의 결빙점 부근 악화를 분석하는 것이다. 그 뒤 좌표·시점·수직 단위를 검증한 도로·지형 특징을 같은 LOSO에 추가해 핵심 질문에 답한다. 보호 지점 최종 평가는 아직 실행하지 않는다.

재실행 명령: python scripts/audit_aws_fallback.py → python scripts/build_aws_fallback_features.py → python scripts/baseline_weather_ridge.py --variant fallback → python scripts/compare_weather_variants.py → python scripts/check_notebook.py.


### 공식 평가 대비 현황 — 2026-09-23

[평가 항목별 현황과 다음 실행](EVALUATION_STATUS.md)을 추가했다. 현재 완료된 정량 모델은 개발용 노면온도 추정뿐이다. 보호 3개소 최종 점수, 10분 Ice 예측, 일별 F1·Precision·Recall, 외부 데이터 입력 효과, 3개 노선 위험도 지도는 아직 없다. 다음 실행은 개발용 직접 Ice 분류 기준선과 잠정 일별 평가 흐름이며, 그 결과를 노트북에 연결한다. 운영진 답변 전 무결빙일·불완전한 날·최종 평균 방식은 잠정으로 유지한다.


### 첫 결빙 분류 기준선 및 잠정 일별 평가 — 2026-09-23

- 보호 RWIS 12410·33411·23402를 제외한 14개 개발 지점의 전체 483,805시각을 독립 결빙 타깃 파이프라인으로 처리했다. 유효 Ice 정답 483,652시각, Ice 239시각, 미정의 153시각으로 기존 EDA와 일치한다. 노면온도 결측 여부로 결빙 평가 행을 줄이지 않았다.
- 한 종류의 클래스 가중 로지스틱 회귀를 외부 LOSO 14회에 사용하고, 각 외부 학습 지점 안의 3분할 OOF 10분 F1로 임계값을 정했다. 최근접 AWS 입력은 TP 164·FP 96,743·FN 75; 상위 3개 가용 AWS 입력은 TP 21·FP 955·FN 218이다. 양쪽 모두 실사용 분류기로 부적합하다. 대체 AWS 모델 TP 21건은 12210 한 곳에만 있다.
- 잠정 일별 144개 유효 시점 기준 3,308 지점·날짜가 채택됐다. F1 정의 날짜는 최근접 1,794·대체 240으로 달라 단순 평균 비교는 불공정하다. 같은 실제 Ice 날짜 110개에서 날짜 평균 F1은 각각 0.04134·0.01037; 무결빙 날짜 오경보는 1,684·130개다. 공식 점수가 아니다.
- 실제 Ice 239시각 중 AWS 기온은 최근접 134, 대체 214시각에서 확보된다. 노면온도 0°C 이하인 비결빙 시각이 141,024개라 저온만으로 Ice를 판별할 수 없다. 노면온도는 이 진단에만 사용했고 직접 분류기 입력에는 넣지 않았다.
- 새 스크립트: scripts/build_ice_features.py, scripts/baseline_ice_logistic.py, scripts/compare_ice_variants.py, scripts/diagnose_ice_baseline.py. [분류 보고서](ICE_BASELINE_REPORT.md), [평가 대비 현황](EVALUATION_STATUS.md), [노트북](../notebooks/analysis_review.ipynb)을 갱신했다. 노트북 25단계·18개 코드 셀 실제 커널 통과, 단위 테스트 15개 통과. 출력은 outputs/private/만 사용한다.
- 다음 작업은 개발용 단일 시각 Ice 전후 상태 QC와 과거 수분·열 이력 특징의 가용성 점검이다. 이후 내부 학습 지점에서 지점 균형·오경보 한계를 고려한 임계값을 설계한다. 현재 OOF 결과에 맞춰 임계값을 다시 튜닝하거나 보호 3개소를 열지 않는다.

재실행 명령: python scripts/build_ice_features.py → python scripts/baseline_ice_logistic.py → python scripts/build_aws_fallback_features.py --target ice → python scripts/baseline_ice_logistic.py --variant fallback → python scripts/compare_ice_variants.py → python scripts/diagnose_ice_baseline.py → python scripts/check_notebook.py.


### 단일 시각 Ice 사건 맥락 감사 — 2026-09-23

개발용 215개 Ice 사건의 바로 전후 상태를 확인했다. 198개 한 시각 사건은 모두 양쪽에 유효 비결빙 코드가 있었고, 166개는 코드 12 또는 15와 맞닿아 있었다. 62개는 12–Ice–12, 24개는 15–Ice–15였다. 이 결과는 라벨 제거 근거가 아니므로 원시 04를 유지한다. scripts/audit_ice_events.py와 비공개 outputs/private/ice_event_audit/를 추가하고 [분류 보고서](ICE_BASELINE_REPORT.md), [노트북](../notebooks/analysis_review.ipynb)에 연결했다. 다음은 이 상태 전환과 강수·습도·이슬점의 과거 이력을 함께 검토하는 것이다.





### 시설 거리·과거 기상 이력 실험 — 2026-09-23

시설 거리 입력을 추가하는 두 가지 비교와, 관측소별 학습·평가를 분리한 과거 기상 이력 분류 모델을 실행했다. 모든 입력·출력에서 보호 지점 12410·33411·23402를 제외했다. [시설·기상 이력 보고서](FACILITY_HISTORY_REPORT.md)에 결과와 한계를 정리했다.

- **시설 거리:** 개발 지점 14곳에서 제공 교량·터널 도형(EPSG:5179)을 사용했다. 가장 가까운 시설까지의 거리와 해당 고속도로 중심선 50m 주변에 있는 시설까지의 거리를 동일한 483,095개 노면온도 행에서 비교했다. 지점 평균 MAE는 기상만 1.7377°C, 임의 시설 거리 추가 1.7779°C, 노선 주변 시설 거리 추가 1.7802°C였다. 두 입력 모두 채택하지 않았다. 시설 자료의 기준 시점과 공식 노선 귀속은 미확인이다.
- **과거 3시간 기상:** 목표 시각 이전 AWS 이력이 실제 결빙 239개 시점 중 214개에 있었다. AWS 기온 −5°C에서 3°C 조건에서, 과거 강수 관측이 있던 13,958개 시점 중 66개, 없던 177,737개 시점 중 91개에서 결빙이 있었다. 이는 관측된 연관성이며 인과효과가 아니다.
- **결빙 분류:** 같은 483,805개 목표 시점과 14개 외부 검증 회차에서, 대체 AWS 로지스틱의 TP/FP/FN은 21/955/218, 과거 이력 추가 모델은 19/3,123/220이었다. 같은 실제 결빙 날짜 110개의 잠정 평균 F1은 0.0104에서 0.0069로 낮아지고, 무결빙일의 오경보 날짜는 130일에서 239일로 늘었다. 이력 모델의 적중 19개는 모두 12210 지점이었다. 두 모델 모두 위험 지도나 공식 최종 평가에 사용할 수준으로 검증되지 않았다.
- **실행 기록:** 로컬 전용 산출물은 `spatial/station_facility*`, `facility_weather_comparison`, `route_facility_weather_comparison`, `ice_weather_history`, `ice_history_logistic`, `ice_history_comparison`에 저장했다. 보고서에 스크립트와 시간 경계 테스트 2개를 기록했다. 당시 노트북은 등록 단계 32개·코드 셀 21개였고 실제 커널 실행과 단위 테스트 17개가 통과했다.

당시 다음 작업은 주변 RWIS 입력을 점검하되 외부·내부 평가 지점을 모두 참조에서 제외하는 것이었다. 현재 분류 결과에 맞춰 보호 지점으로 설정을 조정하지 않는다. 공식 필수 추정 변수와 일별 평가 규칙을 확인한 뒤 최종 평가한다. 선택 실행은 `python scripts/check_notebook.py --run-stage ice_history_comparison`, 전체 결과 검토는 `python scripts/check_notebook.py`를 사용한다.

### 주변 도로 관측을 추가한 온도 예측 비교 — 2026-09-23

[주변 RWIS 보고서](NEIGHBOR_RWIS_REPORT.md)는 당시 미관측 지점의 노면온도 추정 결과다. 목표 지점과 같은 노선의 가장 가까운 다른 개발 관측소에서 30분 이내의 과거 노면온도를 가져왔다. 보호 지점 3곳은 목표·참조에서 모두 제외했다.

기상 Ridge의 483,095개 시점 중 세 방법이 공통으로 평가 가능한 483,061개를 사용했다. 지점 평균 MAE는 기상 Ridge 1.73761°C, 주변 노면온도만 사용 1.31291°C, 두 값을 1:1로 평균 1.28582°C였다. 고정 혼합은 개발 지점 14곳 모두에서 기상만 사용한 결과보다 오차가 작았다. RMSE는 2.27994에서 1.79366°C, 실측 −2°C에서 2°C 구간의 MAE는 1.44085에서 1.03861°C로 줄었다. 다만 12210에서 주변 관측만 사용하면 MAE 1.944°C로 기상 모델의 1.572°C보다 나빴고, 고정 혼합은 1.497°C였다. 목표 지점의 실제값과 그 과거값은 입력에 넣지 않았다.

참조 관측은 10분 전 482,992개·20분 전 54개·30분 전 15개였다. 겨울별 사후 진단의 MAE도 고정 혼합이 기상만보다 낮았다(첫 겨울 1.197 대 1.680°C, 둘째 겨울 1.375 대 1.796°C). 그러나 기상 모델이 두 겨울을 함께 학습했으므로 **첫 겨울로 다음 겨울을 예측한 검증은 아니다**. 실제 발표 지연, 미관측 구간과 참조 관측소의 거리, 학습형 모델에서 모든 내부·외부 평가 지점을 참조에서 빼는 구현은 당시 미확인이다. 결빙 분류·보호 지점 최종 평가·위험 지도도 미완료였다.

재실행 명령은 `python scripts/baseline_neighbor_rwis.py --smoke`, `python scripts/baseline_neighbor_rwis.py`, `python scripts/diagnose_neighbor_rwis.py`다. 당시 노트북은 등록 단계 34개·코드 셀 23개·저장 출력 0개였으며, `--run-stage neighbor_rwis_diagnostic`을 포함한 실제 커널 실행과 단위 테스트 17개가 통과했다. 후속 학습형 모델에서는 외부·내부 평가 지점을 모든 RWIS 참조 입력에서 제외하고, 보호 지점 평가 전에 모델·공식 평가 규칙을 확정해야 한다.

</details>
