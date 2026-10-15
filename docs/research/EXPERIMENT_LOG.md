# 실행·실험 기록

실제로 실행한 명령과 당시 결과를 남긴 이력입니다. 아래 테스트 수·단계 수·다음 작업은 각 실행 시점의 기록이며 최신 상태는 진행 현황에서 확인합니다.

[문서 목록·용어 풀이](../README.md) · [프로젝트 소개](../../README.md)

2026-09-23, Windows 10 build 26200, Python 3.11.2, pandas 2.2.3, NumPy 2.2.6, GeoPandas 1.1.3, pyogrio 0.12.1, pyproj 3.7.2, scikit-learn 1.6.1. 원본 ZIP과 PDF는 변경하지 않았다. 외부 서비스에 데이터 업로드·대회 제출 없음.

| 실행 | 결과 | 해석 |
| --- | --- | --- |
| `python scripts/audit_data.py --limit-files 3` | 3개 첫 파일 파싱 성공 | 전체 실행 전 흐름 확인 |
| `python scripts/audit_data.py` | 720개 파일, 63개 ID 그룹(실측 61 + 빈 ID 2), 파싱 오류 0 | 관측소 ID `.0` 변형을 발견해 보호 필터 수정 후 전체 재생성. 최초 집계 폐기 |
| `python scripts/audit_timestamps.py` | AWS 완전 빈 행 285,823건, 자정 중복 2,776건 | ASOS 첫 열이 원본 인덱스임을 반영해 시각 열 수정 후 재생성 |
| `python scripts/audit_spatial.py` | 도로 선형 1,471개, DEM 30m, 중첩 공간 레이어 5종 | 64비트 부동소수 GeoTIFF 메타데이터 파서로 처리 |
| `python scripts/eda_development.py` | 개발 14개 지점 Ice 239개 시점/215개 사건 | 단일 시점 사건 198건, 라벨 품질 점검 필요 |
| `python scripts/make_splits.py` | 외부 LOSO 14회, 보호 지점 중첩 0 | 내부 3분할 모두 결빙 관측 지점 3–4곳 |
| `python scripts/baseline_asos.py --limit-days 2` | 이틀 자료 4,018 유효 쌍/4,032 목표, 오류 없이 실행 | 후방 시각 결합과 계산 비용 확인. 이틀 점수는 성능 근거로 쓰지 않음 |
| `python scripts/baseline_asos.py` | 개발 14개 지점, 483,095 유효 쌍, 지점 평균 MAE 2.394°C(직접) / 2.174°C(학습 지점 보정) | 공식 지점 미사용, 과거 ASOS만 입력. 4곳에서 보정 악화 |
| `python -m unittest discover -s tests -v` | 8개 테스트 통과 | 결측·자정·무결빙·BIAS·보호 지점 검증 |
| `python scripts/audit_aws_boundaries.py --limit-files 3` → 전체 | 자정 중복 2,776쌍 모두 수치 동등, 측정값 충돌 0건 | 891쌍은 원시 숫자 표기만 다름. 짝 없는 25건은 3월 1일 |
| `python scripts/audit_aws_cleaning.py --limit-files 3` → 전체 | AWS 1,077,128행 중 788,504행 유지, 파일 날짜 내 중복 0건 | 빈 ID 285,823행·다음 날 00:00 2,801행 제외 |
| `python -m unittest discover -s tests -v` | 11개 테스트 통과 | 날짜 필터·중복 ID·시각 파싱 실패 사례 포함 |
| `python scripts/check_notebook.py` 및 `--run-stage validation_splits` | 실제 Jupyter 커널에서 코드 셀 10개 통과, 저장 출력 0개 | 등록 9단계의 결과 조회와 단계 선택 실행 확인 |

ASOS 기준 실험의 지점별 OOF 보정 예측은 `outputs/private/baseline/predictions.csv`에 있다. 기상·도로환경 결합 모델, 분류 임계값, 공식 지점 성능은 아직 없다. 다음 실험에는 입력 자료 버전, 특징, 분할, 난수 시드, 지점별 결과와 실패 사례를 추가한다.

AWS 자정 동등성 감사의 첫 구현에서 두 겨울 사이 공백을 같은 지점이라는 이유로 비교해 15건의 가짜 충돌이 생겼다. 같은 **시각** 조건을 추가해 전 기간을 재집계했고, 최종 결과는 측정값 충돌 0건이다. 초기 집계는 폐기했다. 다음 실험은 AWS/ASOS의 후방 시각 결합을 작은 날짜 범위에서 점검한다.

| 실행 | 결과 | 해석 |
| --- | --- | --- |
| `python scripts/build_weather_features.py --limit-days 2` → 전체 | 개발용 483,777목표, 과거 AWS 기온 340,453·ASOS 기온 483,095 연결 | 보호 지점 제외, 목표보다 이전·최대 60분; AWS 지점별 연결률 약 52–82% |
| `python scripts/baseline_weather_ridge.py --smoke` → 전체 | 14개 지점 LOSO, 같은 483,095개 시점 MAE 2.174→1.771°C | 고정 Ridge 한 개. 12209 전체 악화, −2–2°C 구간 4개 지점 악화 |
| `python scripts/check_notebook.py` | 12개 코드 셀 실제 커널 통과 | `stdout=None` 재현 검사, 새 모델 결과·누수 검증 셀 포함, 출력 저장 0건 |

| 실행 | 결과 | 해석 |
| --- | --- | --- |
| `python scripts/diagnose_weather_ridge.py` | 12209의 2025–26 겨울 AWS 누락 5,851개 시점에서 MAE 2.457→2.924°C | 다른 AWS 대체와 위치별 편차 검증 우선 |
| `python scripts/audit_station_road_alignment.py` | 개발 RWIS 14곳 해당 노선 중심선 거리 중앙값 16.3m, 최대 22.3m, 노선 불일치 0 | 정적 특징 결합의 위치 QA 통과 |

| 실행 | 결과 | 해석 |
| --- | --- | --- |
| `python scripts/evaluate_weather_temporal.py` | 첫 겨울 학습 241,894행→둘째 겨울 검증 241,201행, 지점 평균 MAE 2.215→1.766°C | 같은 관측소를 양쪽 겨울에 사용한 시간 보조 검증으로 공간 LOSO와 분리 |

| 실행 | 결과 | 해석 |
| --- | --- | --- |
| `python scripts/check_notebook.py --run-stage weather_temporal` | 실제 Jupyter 커널에서 코드 셀 13개 통과, 등록 단계 14개·저장 출력 없음 | 겨울 간 검증을 추가한 뒤 노트북 최종 실행 확인 |

| 실행 | 결과 | 해석 |
| --- | --- | --- |
| python scripts/audit_aws_fallback.py --smoke → 전체 | 개발용 483,777개 시각; 최근접 AWS 340,453, 3개 AWS 후보 434,253; 12209 25,894→30,192 | 유효한 과거 60분 기온만 연결. 노면온도 정답과 보호 지점은 읽지 않음. 입력 가용성 결과이며 MAE 개선 주장이 아님 |
| python scripts/check_notebook.py --run-stage aws_fallback | Jupyter 커널 14개 코드 셀 통과, 실행 목록 15단계, 저장 출력 0 | 신규 후속 사례 셀 실행 및 결과 확인 |
| python -m unittest discover -s tests -v | 12개 통과 | 기존 시각 누수·분할·평가 함수 검증 유지 |


| 실행 | 결과 | 해석 |
| --- | --- | --- |
| python scripts/build_aws_fallback_features.py --smoke → 전체 | 개발 483,777개 시각 중 기온 434,253 연결, 순위별 340,521·70,914·22,818 | 원본 AWS의 유효 과거 60분 자료만 사용, 보호 RWIS 제외 |
| python scripts/baseline_weather_ridge.py --smoke --variant fallback → 전체 | 같은 14개 LOSO·483,095개 시각; 지점 평균 MAE 1.738°C | 기존 Ridge α=100 및 fold 안 전처리 유지 |
| python scripts/compare_weather_variants.py | 최근접→대체 MAE 1.771→1.738°C, RMSE 2.319→2.280°C, 14/14 전체 MAE 개선 | 12209 ASOS보다 나쁨; 23202의 −2–2°C 구간 악화. 결빙 분류 성능 아님 |
| python scripts/check_notebook.py --run-stage weather_fallback_comparison | Jupyter 커널 15개 코드 셀 통과, 18단계 등록, 출력 저장 0 | 비교 결과를 단일 노트북에서 실행·확인 |
| python -m unittest discover -s tests -v | 12개 통과 | 기존 누수·평가 테스트 유지 |


| 실행 | 결과 | 해석 |
| --- | --- | --- |
| python scripts/build_ice_features.py --limit-days 2 → 전체 | 개발 483,805개 시각, 유효 상태 483,652, Ice 239, 미정의 153 | 노면온도 결측과 독립적으로 결빙 정답 구성, 보호 3개소 제외 |
| python scripts/baseline_ice_logistic.py --smoke → 전체 | 14개 지점 LOSO; 최근접 AWS TP 164·FP 96,743·FN 75 | 작은 실행은 희귀도 왜곡으로 성능 근거에서 제외. 전체 실행 임계값은 내부 OOF만 사용 |
| python scripts/build_aws_fallback_features.py --target ice → python scripts/baseline_ice_logistic.py --variant fallback | Ice 시각 AWS 연결 134→214, 대체 모델 TP 21·FP 955·FN 218 | 동일 목표 483,805행·정답 483,652행 확인. TP 21건 12210에만 집중 |
| python scripts/compare_ice_variants.py → python scripts/diagnose_ice_baseline.py | 같은 Ice 날짜 110개의 날짜 F1 0.04134→0.01037, FP 있는 무결빙 날짜 1,684→130 | 일별 전체 평균의 정의된 날짜 수 1,794→240으로 달라 직접 우열 판단 불가 |
| python scripts/check_notebook.py --run-stage ice_variant_comparison --run-stage ice_diagnostic | 17개 코드 셀 실제 Jupyter 커널 통과, 24단계 등록, 저장 출력 0 | 단일 노트북에서 분류 결과 확인·비교 |
| python -m unittest discover -s tests -v | 14개 통과 | 임계값·일별 지표·보호 지점·시각 결합 테스트 |


| 실행 | 결과 | 해석 |
| --- | --- | --- |
| python scripts/audit_ice_events.py | Ice 사건 215개 중 한 시각 198개, 그중 코드 12/15 인접 166개, 12–Ice–12 62개·15–Ice–15 24개 | 원시 04 정답 유지; 사건 전후의 품질·처리 맥락을 비공개 CSV에 저장 |



## 2026-09-23 · 시설 거리·과거 기상 입력의 추가 효과

비교 행을 노면온도 483,095개와 노면상태 목표 483,805개(유효 483,652개·결빙 239개)로 고정했다. 난수 시드는 20260923이다. 제공 시설 도형(EPSG:5179)에서 가장 가까운 시설 거리, 이어 해당 노선 중심선의 50m 주변 영역과 겹치는 시설 거리를 만들었다. Ridge의 α=100을 유지했을 때 지점 평균 MAE는 1.73769에서 각각 1.77786°C·1.78025°C로 악화됐다. 두 입력을 채택하지 않았으며 시설 자료의 기준 시점은 미확인이다.

AWS 과거 3시간 이력은 목표 RWIS보다 이전인 관측 시각에서 끝난다. 서로 겹치는 `rain_15m`을 합산하지 않았다. 클래스 가중 로지스틱 C=0.1과 내부 관측소 OOF 임계값 선택은 유지했다. 기존 대체 AWS 대비 TP/FP/FN은 21/955/218에서 19/3,123/220으로 바뀌었다. 같은 실제 결빙 날짜 110개의 잠정 평균 F1은 0.01037에서 0.00688로 낮아졌다. 적중 19개는 모두 12210이며 다른 13곳의 적중은 0개다. 현재 모델에서 이력 입력은 채택하지 않았다. [상세 표·실행 명령](FACILITY_HISTORY_REPORT.md)

## 2026-09-23 · 같은 노선의 과거 주변 관측 비교

개발 관측소 14곳을 번갈아 학습에서 제외해 비교했다. 목표 지점은 자신의 참조에서도 빼고 보호 지점은 모든 단계에서 제외했다. 같은 노선의 가장 가까운 다른 RWIS에서 10–30분 전 노면온도를 가져와, 기존 기상 Ridge와 고정 1:1 평균을 비교했다.

같은 평가 행 483,061개에서 기상 / 주변 관측 / 고정 평균의 지점 평균 MAE는 1.73761 / 1.31291 / 1.28582°C, RMSE는 2.27994 / 1.95677 / 1.79366°C였다. 고정 평균은 14곳 모두 기상 모델보다 개선됐지만 주변 관측만 쓰면 12210은 악화됐다. 혼합 가중치나 목표 지점 보정값을 조정하지 않았다. 겨울별 결과는 사후 진단이며 미래 겨울 검증이 아니다. 실제 제공 지연과 도로 구간의 참조 가용성은 미확인이다. [주변 관측 상세 결과](NEIGHBOR_RWIS_REPORT.md)

## 2026-10-02 공식 Q&A 및 공간·시간 분리 검증

Q&A 555·556, 제출 공지 564와 기준표 이미지를 확인했다. 일부 평가 규칙은 기존 구현과 일치하며 정정본 배포 예고에 따라 현 결과를 20260915 구버전으로 명시했다.

Ridge α=100·혼합 1:1을 고정하고 첫 겨울의 다른 지점 학습→둘째 겨울 제외 지점 평가 14회를 실행했다. 동일 241,201행 지점 평균 MAE: 기상 1.828130, 혼합 1.389021°C. RWIS 30분 지연 1.444110, 60분 지연 1.573041°C. 기본 혼합은 14/14, 30분 12/14, 60분 11/14 지점에서 기상 대비 개선. 지연을 튜닝하지 않았고 보호 3개소를 열지 않았다.

입력 ZIP 이름·SHA256 고정과 12개 호출부 수정. 새 출력은 outputs/private/neighbor_transfer 및 smoke_neighbor_transfer, 공식 근거는 official_review_20261002. 상세는 NEIGHBOR_TRANSFER_REPORT.md와 OFFICIAL_UPDATE_20261002.md.


## 2026-10-02 비선형 Ice 및 내부 일평균 임계값

사전에 고정한 HGB 100 iterations/15 leaves/learning_rate=.05/L2=10/balanced/early_stopping=False로 14개 외부·42개 내부 검증을 실행했다. 14개 기존 기상·시각 특징과 원래 전체 정답 행을 유지했으며 외부 정답으로 설정을 튜닝하지 않았다.

10분 F1 임계값: TP 22/FP 20,363/FN 217. 일평균 F1 임계값: TP 112/FP 68,513/FN 127. 기존 로지스틱: TP 21/FP 955/FN 218. 일평균 F1은 0.001087→0.005694로 개선되나 무결빙일 오경보 130→1,345일로 악화하므로 다음 비교 후보로만 보존한다. 최종 모델은 미선정이다.

사건 진단, 정의된 날짜·지점 수, 고정 Ice 날짜 비교, 부분 날짜 민감도, 원시 상태별 오류, 지점 재표집, 그림을 추가했다. 상세: ICE_NONLINEAR_REPORT.md. 출력: outputs/private/ice_nonlinear 및 ice_nonlinear_comparison. 보호 지점 사용 없음.


## 2026-10-02 수정본 전 정보 감사·정적 지도 기반

### 작업 결과

[수정본 전 작업 보고서](PRE_CORRECTION_WORK_REPORT.md)에 주변 RWIS 정보 감사·내부 참조 제외·기존 오경보 진단·정적 도로 구간을 정리했다. 직전 주변 Ice는 실제 결빙 239개 중 1개, 과거 60분 이력은 6개만 적중했다. 습도는 외부 평가 타깃의 Ice 239개 모두에서 확보됐으나, 내부 제외를 적용한 수분 참조 546조합 중 47조합에는 같은 노선의 참조가 없었다. 결측을 다른 검증 지점으로 채우지 않는다.

정적 중심선 275.889km를 최대 1km 구간 467개로 만들고 Shapefile·GPKG 저장/재읽기를 확인했다. 위험 점수는 전부 미산정이며 공식 이정·방향별 최종 위험 지도가 아니다. 구간/오경보 결과를 모델 성능 개선으로 주장하지 않는다.
