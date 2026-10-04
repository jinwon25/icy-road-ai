# 단계별 실행 안내

어떤 명령을 어떤 환경에서 실행하는지 안내합니다. 원본 없이 가능한 검증과 대회 원본·중간 산출물이 필요한 분석을 나누어 설명합니다.

[문서 목록·용어 풀이](README.md) · [프로젝트 소개](../README.md)

기준일: 2026-10-04. 현재 경로와 [노트북 단계 설정](../config/notebook_workflow.json)에 맞춘 실행 안내다. 분석 결과와 과거 가정은 각 보고서에서 확인한다.

## 데이터 없는 검증

프로젝트 루트에서 Python 3.11과 [필요 패키지](../requirements.txt)를 준비한다.

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/check_repository.py
```

단위 테스트 31개와 추적 파일 검사는 원본 ZIP 없이 가능하다. 저장소 검사는 Git 체크아웃을 기준으로 노트북 출력·금지 파일·문서 링크를 확인한다.

## 참가 권한이 있는 원본 환경

원본은 [data_source.json](../config/data_source.json)의 파일명·SHA256과 일치해야 한다. ZIP은 루트에 두고 감사·특징·모델·예측 결과는 `outputs/private/`에서 관리한다. 신청서는 실행 입력이 아니다.

```powershell
python scripts/audit_data.py --limit-files 3
python scripts/baseline_asos.py --limit-days 2
```

위 명령은 작은 실행이다. 전체 자료 분석 점수로 해석하지 않는다. ASOS 작은 실행은 `outputs/private/smoke/`로 분리된다. 전체 감사를 먼저 수행한 뒤 전체 특징·학습을 선택한다.

## 노트북 검토와 선택 실행

```powershell
python scripts/check_notebook.py
```

기본 검증은 원본·기존 비공개 집계가 있는 환경에서 Jupyter 커널의 27개 코드 셀을 실행하고 파일에 출력을 저장하지 않는다. 전체 노트북 실행에는 원본·캐시가 필요하다.

등록된 특정 단계 재실행:

```powershell
python scripts/check_notebook.py --run-stage validation_splits
python scripts/check_notebook.py --run-stage neighbor_transfer
```

모델 단계는 특징·기준 모델 등 선행 산출물을 필요로 하고 시간이 걸린다. 설정 목록은 명령과 요약 경로를 관리하며 모든 의존성을 자동 해결하지 않는다. `RUN_STAGES` 또는 CLI에 필요한 단계 ID를 순서대로 지정한다. 모든 단계 재생성은 노트북의 `REBUILD_FULL=True`를 명시적으로 선택한다.

## 주요 단계

| 분석 묶음 | 주요 단계 ID |
| --- | --- |
| 자료 감사 | `data_audit`, `time_audit`, `aws_boundary_audit`, `aws_cleaning` |
| 공간·사전 | `spatial_audit`, `station_road_alignment`, `variable_dictionary` |
| 개발 검증 | `development_eda`, `validation_splits` |
| 기상 기준선 | `baseline_asos`, `weather_features`, `weather_ridge` |
| AWS 대체 | `aws_fallback`, `aws_fallback_features`, `weather_fallback_ridge`, `weather_fallback_comparison` |
| 직접 결빙 | `ice_features`, `ice_logistic`, `ice_fallback_features`, `ice_fallback_logistic` |
| 시설·이력 | `station_facility`, `facility_weather`, `ice_weather_history`, `ice_history_logistic` |
| 주변 RWIS | `neighbor_rwis`, `neighbor_transfer`, `rwis_context` |
| 비선형 비교 | `ice_nonlinear`, `ice_nonlinear_comparison`, `ice_context_diagnostic` |
| 도로 구간 | `road_segment_scaffold` |

전체 40개 단계의 정확한 명령·설정·산출물은 [실행 설정](../config/notebook_workflow.json)을 기준으로 한다. 해석은 [진행 상태](PROJECT_STATUS.md), [검증 규약](VALIDATION_PROTOCOL.md), [평가 현황](EVALUATION_STATUS.md)을 참고한다.

## 정정 자료 전환

새 자료는 현재 원본·캐시와 섞지 않고 별도 작업 경로에서 감사한다. 원본 버전 설정과 열·기간·관측소·상태 코드를 대조한 뒤 특징과 모델 산출물을 재생성한다. 기존 캐시를 새 자료의 결과로 취급하지 않는다.

보호 3개 지점은 최종 평가 전까지 학습·모델 조정에서 제외한다. 최종 모델·위험도 지도·데모는 미완료다. [공유 범위](../.github/PUBLICATION.md)와 데이터 종료 후 폐기 조건을 별도로 유지한다.
