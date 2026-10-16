# icy-road-ai · 도로 결빙 위험 추정

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
[![검증](https://github.com/jinwon25/icy-road-ai/actions/workflows/checks.yml/badge.svg?branch=main)](https://github.com/jinwon25/icy-road-ai/actions/workflows/checks.yml)

전북도 고속도로의 기상·도로환경 자료로 관측 장비가 없는 도로의 노면온도와 결빙 여부를 추정하는 개인 분석 프로젝트입니다. 공간·겨울 분리 검증으로 새 지점에서의 오차와 결빙 사건 손실을 함께 확인합니다.

## 현재 상태

**제출 기술 후보 준비 · 성능 적합 판정과 공식 제출 전**입니다. 10월 16일 공식 사이트를 다시 확인하고 단순 기준선 비교·CSV 추론·모델 카드·ZIP 복원 경로를 보완했습니다.

| 항목 | 확인한 상태 |
| --- | --- |
| 현재 후보 | 기상 12변수 기반 MSE·MAE 2모델의 고정 평균 |
| 개발 온도 | 외부 개발 9곳·155,236유효행, 전체 행 MAE 1.200531°C / 지점 균등 MAE 1.200440°C |
| 개발 결빙 | 144유효슬롯 조건의 일별 지점 평균 F1 0.030633. 공식 점수 아님 |
| 로컬 결과물 | `outputs/private/submission_candidate_20261016_v1.zip`: 모델·지도·16쪽 보고서·실행 데모·기준선 검산 |
| 추가 모델 | 결빙점 가중 모델은 저온 오차가 줄어도 기존 사건을 놓쳐 미채택 |
| 남은 일 | 최종 CSV·결측 표현·제출 일정 확인, 입력 공백 보완, 미사용 적격 지점 검증 |

[현재 진행 현황과 다음 작업](docs/STATUS.md) · [제출 후보와 보고서](docs/delivery/MODEL_REPORT_UPGRADE_20261014.md)

현재 후보의 일별 F1 **0.030633**은 항상 결빙 **0.055216**, ASOS 기온 ≤0°C 규칙 **0.071122**보다 낮습니다. FP는 각각 20,255·148,507·57,912건으로 순위가 달라지고, F1에 포함되는 날짜 분모도 다릅니다. 온도 MAE 개선을 결빙 탐지의 우수성으로 표현하지 않습니다. [비교표·지점 편중·재현성 수정](docs/delivery/REVIEW_RESPONSE_20261016.md) · [오늘 공식 확인](docs/competition/OFFICIAL_UPDATE_20261016.md)

추가로 72개 기온·노면 결합을 공간 제외 조건에서 비교했지만 기온 기준선을 넘지 못했습니다. 인접 ASOS 대체도 9곳 중 2곳만 품질 기준을 통과해 채택하지 않았습니다. 원 관측 공백·AWS 접근 제약·미사용 지점 조건까지 확인했으며 현재 실행 후보는 유지합니다. [후속 실험과 다음 조건](docs/research/AIR_ROAD_AND_INPUT_GAPS_20261016.md)

## 처음 읽는 순서

1. [진행 현황](docs/STATUS.md): 완료한 일·한계·다음 작업
2. [폴더 구조](docs/STRUCTURE.md): 코드·데이터·실험·제출물 위치
3. [실행 스크립트 안내](scripts/README.md): 검증·분석·후보 패키징 진입점
4. [문서 목록](docs/README.md): 대회·데이터·검증·연구·제출·과거 기록

## 분석 질문과 데이터

| 항목 | 내용 |
| --- | --- |
| 질문 | 미관측 노면온도와 Ice를 추정하고 새 지점·겨울에서도 성능을 유지할 수 있는가? |
| 입력 | RWIS 노면온도·상태, ASOS·AWS 기상, 도로·교량·터널·지형 |
| 기간 | 2024년 11월–2025년 2월 / 2025년 11월–2026년 2월, 10분 단위 |
| 개발 | 첫 겨울 대회 14곳 + 비대회 9곳 |
| 보호 | 부곡교 12410·삼봉 33411·해전 23402. 학습·모델 선택·주변 참조에서 제외 |
| 정답 | 원본 상태 `04` Ice만 결빙. 미정의·결측은 평가에서 제외 |
| 배포본 | 최신 연구는 `20261007`, 루트 기본 환경은 `20260915` 보존본 |

[변수 사전](docs/data/VARIABLE_DICTIONARY.md) · [검증 설계](docs/validation/VALIDATION_PROTOCOL.md)

## 방법과 결과 해석

평가 그룹을 전처리·학습·후보 선택에서 제외하고 목표 시각보다 엄격히 이른 관측만 사용합니다. 온도 오차와 함께 결빙의 오경보·미탐·짧은 사건 손실을 비교합니다.

현재 후보의 개발 전체 행 MAE는 기존 1.232271°C에서 1.200531°C로 2.58% 감소했습니다. 개발 자료를 반복 비교한 결과이며, 새 지점 일반화와 공식 점수를 입증하지 않습니다. 새 공간 평가에서는 온도 평균 개선과 결빙 사건 손실이 함께 나타나 여러 후보를 미채택했습니다.

[상세 실험·실패 사례](docs/research/WEATHER_MEMORY_REVIEW_20261013.md) · [과거 README의 전체 결과](docs/history/PROJECT_OVERVIEW_20261014.md)

## 실행 방법

Windows·Python 3.11·CPU로 개발했습니다. 의존성은 [requirements.txt](requirements.txt)에 고정했습니다. 원본 없이 수행하는 검증은 다음과 같습니다.

```powershell
python -m pip install -r requirements-dev.txt
$env:OMP_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
python -m unittest discover -s tests -v
python scripts/check_repository.py --include-untracked
python scripts/check_markdown.py --include-untracked
```

전체 분석에는 참가 권한과 로컬 원본·캐시가 필요합니다. 수정본 작업 루트는 `outputs/private/releases/20261007/`이며 루트의 9월 15일 환경과 섞지 않습니다. 이미 개봉한 보호·다음 겨울 평가는 새 독립 평가로 재실행하지 않습니다. [전체 실행 안내](docs/delivery/RUNBOOK.md)

## 폴더 구성

```text
icy-road-ai/
├── config/              # 자료 버전·검증·실험 설정
├── docs/
│   ├── STATUS.md        # 현재 현황과 다음 작업
│   ├── STRUCTURE.md     # 폴더 역할·정리 내역
│   ├── competition/     # 대회 규정·공식 Q&A
│   ├── data/            # 데이터 감사·EDA·변수 사전
│   ├── validation/      # 검증 규약·평가 현황
│   ├── research/        # 실험 결과·선행연구
│   ├── delivery/        # 제출 후보·보고서·실행 안내
│   ├── history/         # 누적 진행 기록·이전 소개
│   └── images/          # 집계 그림
├── notebooks/           # 출력 없는 분석 노트북
├── scripts/             # 실행 진입점, README에서 목적별 탐색
├── src/                 # 재사용하는 처리·모델·평가 코드
├── tests/               # 합성 데이터 검증
├── outputs/private/     # Git 제외: 캐시·모델·예측·제출 후보
├── .github/             # CI·변경 기준·공유 조건
└── AI_USAGE.md          # AI 지원·검토 기록
```

원본 ZIP·참가신청서·`secret.env`·`.venv_research/`도 로컬에서 보존합니다. 원본 ZIP 위치는 기존 코드와 해시 고정 설정을 따릅니다. [설정 안내](config/README.md)

## 한계와 이용 조건

관측 Ice가 일부 지점에 집중되고 온도 개선이 지역 구성에 의존합니다. 입력 공백은 보호 예측 18행에 남아 있으며 정답을 보지 않고 null로 유지합니다. 조건 노출을 사고확률이나 검증된 위험등급으로 해석하지 않습니다.

[AIDA 공식 문제·자료·참가 양식](https://aida.kisti.re.kr/competition/main/problem/PROB_000000000004604/detail.do) · [공식 제출 안내](https://aida.kisti.re.kr/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId=564) · [참고 문헌](docs/research/REFERENCES.md)

대회 자료는 참가 서약의 이용·보안·종료 후 폐기 조건을 따릅니다. 코드 제출 의무를 대회 중 공개 허용으로 해석하지 않습니다. [공유 범위](.github/PUBLICATION.md)
