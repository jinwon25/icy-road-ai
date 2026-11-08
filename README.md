# 전북 고속도로의 겨울철 노면온도·기상 분석

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
[![검증](https://github.com/jinwon25/icy-road-ai/actions/workflows/checks.yml/badge.svg?branch=main)](https://github.com/jinwon25/icy-road-ai/actions/workflows/checks.yml)

센서가 없는 도로의 기상과 노면온도를 RWIS·AWS·ASOS의 과거 관측으로 추정하고, 교량·선형 정보와 공개 취약구간 목록을 대조한 분석이다. 참가팀은 **로드투인사이트**이며, 2026 DATA·AI 분석 경진대회 전북 고속도로 과제를 진행했다.

## 현재 결과

| 항목 | 결과 | 평가 범위 |
| --- | --- | --- |
| 노면온도 | MAE 지점 평균 **0.978°C** | 학습 제외 3지점·103,659 유효쌍 |
| 기본 회귀와 비교 | MAE **14.6% 감소** | 같은 관측쌍 103,131개, 12특성 회귀 대비 |
| 기온·습도·풍속 | MAE 1.324°C·5.687%p·0.500m/s | 개발 4지역의 지역 전체 제외 |
| 결빙 판정 | 정밀도 0.0195·재현율 0.5936·F1 0.0326 | 실제 Ice가 있는 1지점의 날짜별 평균 |
| 추가 계측 후보 | 3구간·2개 연속 범위 | 500m 보고 단위, 75개 기준 조합의 민감도 제공 |

노면온도의 개선이 결빙 탐지 성능 향상을 뜻하지는 않는다. 결빙은 오경보가 많아 자동 경보의 단독 근거로 삼기 어렵다. 공간 결과는 추가 관측·시설 확인을 위한 자료이며 결빙확률·사고확률·공식 위험등급을 검증한 결과가 아니다. 실제 현장 계측은 수행 전이다.

[최종 보고서 원고와 도표](docs/delivery/FINAL_ANALYSIS_REPORT.md) · [결과 읽는 순서](docs/START_HERE.md) · [현재 상태와 검증 범위](docs/STATUS.md)

## 자료와 방법

대상은 서해안·통영-대전·호남 고속도로의 500m 843구간이다. 기간은 2024년 11월–2025년 2월과 2025년 11월–2026년 2월이며, 10분 시각을 기준으로 분석했다. 학습 허용 23지점과 평가 3지점을 분리하고 추정 시각보다 앞선 기상만 입력했다.

노면온도는 기상 이력·태양위치 63특성의 HistGradientBoosting 회귀, 기상은 잔차 회귀와 주변 AWS 관측망으로 추정했다. 결빙은 기준온도와 기상 수분 대용조건으로 판정했다. 지역 전체를 제외한 비교, 기존 공개 목록 대조, 실제 기상 입력의 중복 제거와 선정 기준 민감도를 함께 확인했다.

추가로 검토한 ASOS·AWS 단기 이력 후보 두 가지는 총 40회 학습과 내부 문턱 선택에서 채택 기준을 충족하지 못했다. 현재 제출 모형과 필수 예측값은 유지했다. 실패 분석과 문헌 근거는 최종 보고서에 포함했다.

## 실행

Windows·Python 3.11·CPU 환경에서 개발했다. 저장소 검사 명령은 다음과 같다.

```powershell
python -m pip install -r requirements-dev.txt
python -m pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cpu
$env:OMP_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
python -m pytest -q tests
python scripts/check_repository.py
python scripts/check_markdown.py
```

원자료를 제외한 Windows·Python 3.11 복사본에서 테스트 502개와 하위 검사 7개, 저장소 파일 1,222개와 Markdown 125개의 검사를 통과했다. 이 명령은 합성 자료와 코드·문서를 검사하며 대회 원자료로 전체 분석을 재현하는 명령과 구분한다. PyTorch는 연구 비교 검사용이며 최종 온도 회귀의 추론에는 필요하지 않다. 추가 연구·보고서 의존성은 `requirements-research.txt`, `requirements-delivery.txt`에 나눠 두었다.

**GitHub에는 원자료·학습된 모형·행 단위 결과·제출 ZIP을 넣지 않았다.** 저장소 복제만으로 전체 학습·추론과 데모가 실행되지는 않는다. 참가 권한이 있는 로컬 작업공간의 실행 폴더는 `outputs/private/competition_submission/icy_road_model/`이며, 그 안의 `README.md`에 설치·학습·추론 방법이 있다. 전체 예측 103,680행과 예제 144행의 정확 재현은 이 로컬 제출본의 압축 해제본에서 확인한 결과다.

## 파일 구성

| 경로 | 역할 |
| --- | --- |
| [src/](src/) | 기상 입력·모형·지표·구간 처리 코드 |
| [scripts/](scripts/README.md) | 학습·검산·보고서·데모·패키징 진입점 |
| [config/](config/README.md) | 데이터 출처·분할·실험 설정 |
| [notebooks/](notebooks/) | 출력과 실행 번호를 비운 분석 흐름 |
| [tests/](tests/) | 시간 경계·분할 누출·지표 분모·재현 로직 검사 |
| [docs/](docs/README.md) | 최종 보고서, 규정, 상세 연구와 과거 기록 |

## 이용 조건과 한계

제공 자료는 승인된 대회 목적의 비공개 자료다. 참가 서약의 제3자 열람·제공 제한과 대회 종료 후 폐기 조건을 따르며, 수상작의 주최 측 공개 동의를 참가자의 자유로운 공개 허용으로 해석하지 않는다. 이 저장소는 비공개로 유지한다. [공유 범위](.github/PUBLICATION.md)

평가 지점 수와 실제 결빙 양성 수가 적고 반복 개발 지역의 결과는 새 독립 평가와 구분해야 한다. 지형 자료는 DSM 기반의 맥락이며 실제 일사·교량 높이·제설 효과를 측정한 자료가 아니다. 분모·해석 한계·출처·이용조건은 [보고서](docs/delivery/FINAL_ANALYSIS_REPORT.md)와 [공식 기준 대조](docs/competition/OFFICIAL_RULES_AND_RUBRIC_20261106.md)에 기재했다. [AI 활용 내역](AI_USAGE.md)도 함께 제공한다.
