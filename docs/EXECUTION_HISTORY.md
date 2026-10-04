# 실행 설명 및 과거 기록

이 문서는 정리 전 README의 실험 이력을 보존한다. 현재 상태와 실행 범위는 [루트 README](../README.md)를 먼저 확인한다. 과거 시점의 테스트·단계 수는 현재 상태가 아니다.

# 최신 안내 — 2026-10-02

[수정본 전 작업 결과](PRE_CORRECTION_WORK_REPORT.md): 주변 RWIS 참조 감사, 오경보의 수분 조건 진단, 위험 점수 없는 최대 1km 도로 구간 467개를 추가했습니다. 실행 단계는 rwis_context, ice_context_diagnostic, road_segment_scaffold입니다.

## 결빙 분류 후속 결과

[비선형 결빙 검증 보고서](ICE_NONLINEAR_REPORT.md)를 추가했습니다. 동일 관측소 분할에서 일평균 F1은 개선됐지만 오경보가 크게 늘어 최종 모델로 확정하지 않았습니다. `python scripts/baseline_ice_nonlinear.py`로 전체 학습, `python scripts/compare_ice_nonlinear.py`로 비교와 그림을 재생성합니다. 새 노트북 단계는 ice_nonlinear와 ice_nonlinear_comparison입니다.

현재 상태는 [PROJECT_STATUS.md](PROJECT_STATUS.md), 규정 변경은 [OFFICIAL_UPDATE_20261002.md](OFFICIAL_UPDATE_20261002.md)를 먼저 확인하세요. 10월 6일까지 원본 오류 정정·관측소 추가가 예고됐습니다. 기존 결과는 20260915 구버전 개발 실험입니다.

새 [공간·시간 분리 검증](NEIGHBOR_TRANSFER_REPORT.md)은 첫 겨울 다른 지점으로 학습하고 다음 겨울의 미관측 지점을 예측합니다. 14개 지점·241,201행에서 기상 MAE 1.828°C 대비 고정 혼합 1.389°C입니다. 결빙 분류·공식 보호 지점 평가·위험도 지도·최종 제출은 미완료입니다.

```powershell
python -m unittest discover -s tests -v
python scripts/evaluate_neighbor_transfer.py
python scripts/check_notebook.py --run-stage neighbor_transfer
```

원본은 `config/data_source.json`의 파일명과 SHA256으로 검증합니다. 다른 ZIP을 함께 둬도 임의 선택하지 않으며 동일 이름의 내용 변경은 오류로 중단합니다. 새 버전은 별도 작업 복사본에서 감사하고 모든 캐시를 다시 만들어야 합니다.

제출 공지의 데모영상과 [AI 활용 기록](../AI_USAGE.md) 요구를 추가했습니다. 현재 실험은 CPU 기반이며 최종 학습 모델·추론 진입점은 아직 없습니다. 아래는 기존 실행 설명과 실험 이력입니다.

---

## 이전 기록 (당시 가정 포함)

# 전북도 고속도로 결빙 상태 추정

미관측 도로 구간의 도로기상 상태와 결빙 여부를 추정하는 대회 프로젝트입니다. 현재 원본 데이터 감사, 개발용 탐색 분석, 관측소 단위 검증, 노면온도 추정과 첫 직접 결빙 분류 기준선 2종을 실행했습니다. 두 분류 기준선은 오경보 또는 미탐이 커 최종 모델이 아닙니다. 도로·지형 추가 효과와 공식 보호 3개소 점수는 아직 없습니다.

원본 ZIP과 참가신청서 PDF는 프로젝트 루트에 둡니다. 모든 감사 결과와 압축 해제 복사본은 `outputs/private/`에 저장되며 Git에서 제외합니다. 원본은 수정하지 않습니다.

실행 환경: Windows 10 (build 26200), Python 3.11.2. 필요한 패키지는 `requirements.txt`에 기록했습니다.

```powershell
python -m pip install -r requirements.txt
python scripts/audit_data.py --limit-files 3
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

전체 스캔은 일별 CSV 720개를 ZIP에서 직접 읽습니다. 공간 감사는 원본을 보존하고 도로·DEM·중첩 ZIP의 로컬 복사본을 `outputs/private/spatial/`에 만듭니다. 기준 모델의 예측값과 지점별 수치는 `outputs/private/baseline/`에만 저장합니다.

결과를 한곳에서 확인하려면 [분석 검토 노트북](../notebooks/analysis_review.ipynb)을 Jupyter 또는 VS Code에서 열어 셀을 순서대로 실행합니다. 기본 실행은 15개 검증 테스트와 이틀짜리 작은 실행만 반복하고 기존 집계 결과를 읽습니다. 실험을 다시 실행하려면 노트북의 `RUN_STAGES`에 [실행 목록](../config/notebook_workflow.json)의 단계 ID를 넣습니다. 전체 재생성은 `REBUILD_FULL=True`로 선택합니다. 새 실험은 실행 목록에 스크립트·요약 산출물을 등록하고 노트북에 결과 해석 셀을 추가합니다. 노트북 파일에는 원본 행이나 실행 출력이 저장돼 있지 않습니다.

실제 Jupyter 커널에서 모든 셀을 자동 검증하려면 프로젝트 루트에서 `python scripts/check_notebook.py`를 실행합니다. 특정 등록 단계를 실제 커널에서 재실행하려면 `python scripts/check_notebook.py --run-stage validation_splits`처럼 지정합니다. 이 검증은 노트북 출력을 저장하지 않습니다.

작업 근거: [대회 요구사항 대조](COMPETITION_REQUIREMENTS.md), [데이터 감사](DATA_AUDIT.md), [변수 사전](VARIABLE_DICTIONARY.md), [검증 규약](VALIDATION_PROTOCOL.md), [개발용 EDA](EDA_REPORT.md), [첫 기준 실험](BASELINE_REPORT.md), [기상 융합 실험](WEATHER_FUSION_REPORT.md), [외부 1차 자료](REFERENCES.md), [운영진 질문](QUESTIONS_FOR_ORGANIZER.md), [진행 기록](PROJECT_STATUS.md).

공식 문제 페이지: https://aida.kisti.re.kr/competition/main/problem/PROB_000000000004604/detail.do (2026-09-23 확인). 페이지에는 전체 데이터 파일이 표시되지만 세부 일별 평가·필수 추정 변수·제출 스키마 답변은 확인되지 않았습니다. 대회 제출이나 외부 공개는 수행하지 않습니다.

## 후속 사례·문헌 검토

개발 자료의 AWS 결측 대체 가능성은 [후속 사례와 실험 근거](FOLLOWUP_EVIDENCE.md)에 정리했다. 공식 FHWA·기상청 자료와 원 논문별 적용 범위는 [문헌 목록](REFERENCES.md)에 있다. 감사 코드는 아래처럼 실행하며 결과는 Git에서 제외된 outputs/private/aws_fallback/에 저장한다. 단일 [분석 노트북](../notebooks/analysis_review.ipynb)의 마지막 두 결과 셀에서 지점별 가용성, 12209 사례와 동일 분모 모델 비교를 확인할 수 있다. RUN_STAGES에 aws_fallback, aws_fallback_features, weather_fallback_ridge, weather_fallback_comparison을 순서대로 넣으면 해당 단계가 재실행된다.

```powershell
python scripts/audit_aws_fallback.py --smoke
python scripts/audit_aws_fallback.py
python scripts/build_aws_fallback_features.py --smoke
python scripts/build_aws_fallback_features.py
python scripts/baseline_weather_ridge.py --variant fallback
python scripts/compare_weather_variants.py
python scripts/check_notebook.py --run-stage weather_fallback_comparison
```

현재 노트북에는 25개 실행 단계와 18개 코드 셀이 등록돼 있으며 실제 Jupyter 커널에서 통과했다. 노면온도 대체 AWS의 개발용 LOSO MAE는 1.738°C다. 결빙 분류 기준선 2종과 잠정 일별 점수도 실행했으나 실사용 성능과 공식 평가는 아직 없다.





평가 항목별 완료·미완료와 후속 실행 순서는 [공식 평가 대비 현황](EVALUATION_STATUS.md)에 정리했다. 노트북 마지막 안내 셀에서도 열 수 있다.



## 개발용 첫 결빙 분류 실행

[첫 결빙 분류 보고서](ICE_BASELINE_REPORT.md)에 동일 14지점 LOSO의 10분 예측, TP·FP·FN, 잠정 일별 지표의 분모 차이와 실패 원인을 기록했다. 결과 CSV는 모두 outputs/private/에만 있다. 실행 순서는 다음과 같다.

```powershell
python scripts/build_ice_features.py --limit-days 2
python scripts/build_ice_features.py
python scripts/baseline_ice_logistic.py --smoke
python scripts/baseline_ice_logistic.py
python scripts/build_aws_fallback_features.py --target ice
python scripts/baseline_ice_logistic.py --smoke --variant fallback
python scripts/baseline_ice_logistic.py --variant fallback
python scripts/compare_ice_variants.py
python scripts/diagnose_ice_baseline.py
python scripts/check_notebook.py --run-stage ice_variant_comparison --run-stage ice_diagnostic
```

첫 실행 때는 기존 비공개 결과를 단일 노트북에서 읽으면 되며, 전체 분류 학습은 내부 관측소 분할을 포함해 오래 걸리므로 필요할 때만 RUN_STAGES로 선택한다.





### Latest development experiments (2026-09-23)

[Facility proximity and prior-weather history report](FACILITY_HISTORY_REPORT.md) records paired station-held-out tests. Bridge/tunnel distance features worsened road-temperature MAE; adding three-hour AWS history worsened direct Ice classification. Both experiments remain development-only and their raw/prediction artifacts stay in `outputs/private/`. The [single review notebook](../notebooks/analysis_review.ipynb) shows and can rerun these stages; `python scripts/check_notebook.py` executes all result cells in a real Jupyter kernel.


The newest [prior neighboring RWIS benchmark](NEIGHBOR_RWIS_REPORT.md) found a development-only road-temperature gain: fixed weather/RWIS averaging achieved station-macro MAE 1.286 C versus weather-only 1.738 C on identical timestamps. It is available in the [review notebook](../notebooks/analysis_review.ipynb) and remains separate from the still-unreliable Ice classifier and unrun official protected-station evaluation.
