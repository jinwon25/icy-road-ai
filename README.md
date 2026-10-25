# icy-road-ai · 미관측 도로의 노면온도와 결빙 조건 추정

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
[![검증](https://github.com/jinwon25/icy-road-ai/actions/workflows/checks.yml/badge.svg?branch=main)](https://github.com/jinwon25/icy-road-ai/actions/workflows/checks.yml)

공공 기상 관측의 시간 이력으로 센서가 없는 고속도로 구간의 노면온도를 추정하고, 결빙 탐지와 공간적 활용 가능성을 검증합니다. 2026 DATA·AI 분석 경진대회의 전북 고속도로 과제이며, 같은 지역의 정답을 학습한 모델로 그 지역을 평가하지 않도록 공간 분할을 적용합니다.

## 확인한 결과

| 항목 | 결과 | 해석 |
| --- | --- | --- |
| 노면온도 | MAE 1.326890 → **1.145698°C**, 13.66% 감소 | 동일 개발 9곳·두 겨울·310,091유효쌍. 반복 개발 점수 |
| 결빙 탐지 | 현재 F1 **0.026554**, 기온 기준선 **0.036601** | 같은 입력 범위의 일별 지점 평균. 기준선 미달 |
| 새 4지역 평가 | 주 후보 F1 증가, 재현율 하락·8사건 손실 | 후보·예측 사전 고정. 자료 품질 조건도 실패하여 미채택 |
| 공간 결과 | 500m 843개·1km 423개, 지도·CSV·오프라인 탐색 | 같은 도로의 두 분할. 독립 검증 표본이나 결빙확률이 아님 |

**온도 개선을 결빙 성능 향상으로 해석하지 않습니다.** 학습은 허용 23지점의 두 겨울 자료를 사용하며, 보호 지점 12410·33411·23402의 정답은 추가 학습·후보 선택·평가에서 제외합니다. 보호 예측의 입력 부족 18행은 NA로 유지합니다.

[10쪽 보고서 원고](docs/delivery/ANALYSIS_REPORT.md) · [심사자 검토 안내](docs/delivery/REVIEWER_GUIDE.md) · [현재 상태](docs/STATUS.md)

## 결과물 읽기

현재 **v7 검토 묶음**은 온도 모델 v3·결빙 판정 v2를 유지하고 보고서·문서 구성을 개편한 결과입니다. 유사 대회의 실제 공개 보고서·발표자료와 공식 기준을 참고해 성과·실패·활용 범위·재현 절차를 한 흐름으로 정리했습니다. [비교 검토와 반영 사항](docs/delivery/BENCHMARK_REVIEW_20261025.md)

1. [처음 읽는 안내](docs/START_HERE.md): 자료·지표·버전의 의미.
2. [보고서](docs/delivery/ANALYSIS_REPORT.md): 질문·방법·온도 및 결빙 결과·새 지역 평가·활용·한계.
3. [v7 구성·검증](docs/delivery/REVIEW_BUNDLE_V7_20261026.md): PDF·노트북·데모와 실행 방법.
4. [CSV 규약](docs/delivery/CSV_CONTRACT.md): 열·단위·NA·지표 분모.
5. [문서 목록](docs/README.md): 상세 실험·공식 규정·과거 기록.

로컬 산출물은 `outputs/private/submission_candidate_20261026_v7/`에 있습니다. 원자료·모델·전체 예측·ZIP은 GitHub에 포함하지 않으므로 저장소 복제만으로 해당 파일이 생기지 않습니다. [폴더 구조](docs/STRUCTURE.md)

## 분석 범위와 남은 과제

기간은 2024년 11월–2025년 2월과 2025년 11월–2026년 2월이며 시간 간격은 10분입니다. 과거 노면 정답 없이 기상·열 이력·태양 위치 63변수로 온도를 추정합니다. 결빙 정답은 원본 상태 `04` Ice만 양성이고 결측·미정의 상태는 평가에서 제외합니다.

결빙의 안정적 개선, 성암교 좌표 불일치, 진천터널외부의 관측 부족·상태 충돌, 센서·제설 이력 확보가 남아 있습니다. 구간 환경과 추정값의 상관은 기술통계이며 사고확률·현장 위험등급·제설 효과를 입증하지 않습니다. [최신 모델링·입력 진단](docs/research/RESIDUAL_AND_INFORMATION_20261025.md) · [원문 품질 진단](docs/research/RWIS_CAUSE_AND_ADDITIVE_20261025.md)

## 실행과 재현

Windows·Python 3.11·CPU 환경으로 개발했습니다. 원본 없이 실행하는 저장소 검사는 다음과 같습니다.

```powershell
python -m pip install -r requirements-dev.txt
python -m pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cpu
$env:OMP_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
python -m pytest -q tests
python scripts/check_repository.py
python scripts/check_markdown.py
```

PyTorch는 연구 MLP의 검사에 사용하며 최종 HGB 추론에는 필요하지 않습니다. 실제 모델·노트북 재현은 비공개 묶음의 포함 자료를 사용합니다. 전체 연구 탐색은 참가 권한과 로컬 입력이 필요합니다. [스크립트 안내](scripts/README.md) · [실행 이력](docs/delivery/RUNBOOK.md)

## 규정과 제출 상태

**10월 25일 23:50 KST 공식 확인에서 결과물 접수 날짜·경로는 별도 공지 예정입니다.** 11월 6일은 참가신청 종료일, 11월 25일은 소개 페이지의 시상식 날짜입니다. [공식 확인 기록](docs/competition/OFFICIAL_UPDATE_20261025.md)

대회 자료의 이용·보안·종료 후 폐기 조건을 따릅니다. 코드 제출 의무를 대회 중 공개 허용으로 해석하지 않으며, 현재는 비공개 검토 후보로 대회 접수·외부 공개를 수행하지 않았습니다. AI가 지원한 단계와 실제 검토는 [AI_USAGE](AI_USAGE.md)에 구분합니다. [공유 범위](.github/PUBLICATION.md)

[이전 v6 소개](docs/history/PROJECT_OVERVIEW_20261025.md) · [전체 문서 목록](docs/README.md)
