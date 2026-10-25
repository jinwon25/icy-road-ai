# icy-road-ai · 도로 결빙 위험 추정

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
[![검증](https://github.com/jinwon25/icy-road-ai/actions/workflows/checks.yml/badge.svg?branch=main)](https://github.com/jinwon25/icy-road-ai/actions/workflows/checks.yml)

전북도 고속도로의 기상·도로환경 자료로 관측 장비가 없는 도로의 노면온도와 결빙 여부를 추정하는 개인 분석 프로젝트입니다. 평가할 지역의 두 겨울을 학습에서 제외해 새 지점에서의 오차와 결빙 사건 손실을 함께 확인합니다. [처음 읽는 안내](docs/START_HERE.md)에 문제·지표·버전·읽는 순서를 설명했습니다.

## 현재 상태

**새 4지역에서 예측을 사전 고정한 일회 평가를 완료했습니다. 주 후보는 채택하지 않습니다.** 일별 F1은 기온 기준선 0.005454 → 0.006758(+23.90%)이지만 재현율이 0.764250 → 0.660669로 낮아지고 기존 탐지 8사건을 놓쳤습니다. 2지역 성능 악화·진천터널외부 관측 부족·성암교 좌표 22.29km 불일치도 확인했습니다. [입력 검증·사전 봉인·평가 결과와 한계](docs/research/BLIND_ICING_20261025.md)

두 겨울 138,240행의 기상 입력·예측은 정답 요청 전에 고정했습니다. 핵심 기상은 100% 존재했지만 도로 정답은 별도 품질 문제가 있었습니다. 평가 날짜를 기준선과 같게 고정한 사후 진단에서는 회귀 F1 0.005455로 개선이 거의 사라졌습니다. 평균 F1 증가를 안정적인 결빙 탐지 개선으로 주장하지 않습니다.

기존 개발 지역에서 회귀 후보의 작은 F1 증가는 오경보만 있던 118일이 평균 분모에서 빠지는 효과를 포함했습니다. ASOS가 탐지하던 결빙 504행·34사건도 놓쳤고, 같은 평가 날짜를 고정한 보조 지표는 낮아졌습니다. 평균 점수와 실제 탐지 개선을 구별합니다. 앞선 [64개 제한 보정 비교](docs/research/ANCHORED_ICING_20261025.md), [제설·센서 자료 및 새 지역 확보](docs/research/ICING_ACQUISITION_20261025.md)는 배경 기록입니다. 제설 원자료·센서 정비 이력은 아직 확보되지 않았습니다.

앞선 원인 분석은 현재 판정이 기온 기준선의 결빙을 수분 조건에서 2,668행, 노면온도 조건에서 1,490행 제외한다는 점을 확인했습니다. 추가 ASOS 8관측·수분 이력·50모델의 당시 결과는 [앞선 연구](docs/research/ICING_GAP_AND_SYNOPTIC_20261025.md)에 보존합니다.

이번 연구는 저장소와 별도 비공개 연구 폴더에 보존합니다. 기존 v5 제출 검토 ZIP과 모델은 그대로입니다. 앞선 30개 전이 모델·임계값 탐색은 [v5에 포함된 이전 연구](docs/research/ICING_TRANSITION_REVIEW_20261025.md)입니다.

기존 확장 회귀 설정 71개와 고정 평균 19개에서 선택한 63개 입력 모델의 공간 제외 개발 MAE는 1.326890 → 1.145698°C로 **13.66%** 낮아졌습니다. 두 겨울·네 지역·결빙점 부근에서 모두 개선했습니다. [기존 모델 선택·검산](docs/delivery/EXTENDED_UPGRADE_20261024.md) · [공개 자료와 대회 조건 검토](docs/research/OPEN_SOURCE_REVIEW_20261024.md)

결빙 분류 60개 모델과 기상 규칙 648개도 검토했지만 모든 채택 기준을 통과하지 못해 v2 결빙 판정을 유지합니다. **온도 개선을 결빙 성능 향상으로 해석하지 않습니다.** 모델·전체 예측·지도·CSV·8쪽 보고서·실제 출력 데모·노트북을 함께 갱신했습니다. [CSV 규약](docs/delivery/CSV_CONTRACT.md)

| 항목 | 확인한 상태 |
| --- | --- |
| 현재 후보 | 기상·열 이력·ASOS 태양 위치 63변수 HGB MAE 1,200회. 비보호 23곳·두 겨울 유효 793,149쌍 학습 |
| 개발 온도 | 외부 개발 9곳·두 겨울 310,091유효쌍, MAE 1.145698°C·RMSE 1.602392°C |
| 개발 결빙 | 두 겨울 일별 지점 F1 0.026554, 같은 가용 입력의 ASOS 기온 기준선 0.036601. 공식 점수 아님 |
| 로컬 결과물 | 비공개 v5. v3 온도·v2 결빙·지도·8쪽 보고서·노트북·CSV 11종·구간 탐색·20.16초 조작 영상 보존, 앞선 전이 연구·규정·문서 포함 |
| 추가 이득 | 2,400회 0.10%, 3시드 평균 0.37%, 후속 LightGBM L1 평균 0.27%. 사전 복잡성 기준 0.5% 미만이라 단일 모델 유지 |
| 검증 | 새 지역 입력 1,797,120값·두 모델 재학습·예측 일치. 960날짜·1,687응답의 원문과 지표 재검산 완료. 테스트 375개·하위 검사 7개 통과 |
| 남은 근거 | 실제 접수 날짜·경로의 공식 공지, 성암교 위치·진천터널외부 상태 충돌 원인, AWS 권한, 센서·제설 이력과 보호 입력 부족 18행 |

로컬 묶음은 `outputs/private/submission_candidate_20261025_v5/`에 있으며 ZIP·검증 영수증은 같은 상위 폴더에 있습니다. GitHub에는 이 비공개 산출물을 올리지 않습니다.

**공식 제출 날짜·방법은 10월 25일 19:38 KST 재확인에서도 별도 공지 예정입니다.** 11월 6일은 참가신청 종료일이며 11월 25일은 소개 페이지의 시상식 날짜입니다.

[현재 진행 현황과 다음 작업](docs/STATUS.md) · [10월 25일 최신 공식 확인](docs/competition/OFFICIAL_UPDATE_20261025.md) · [제출물 검증·노트북 보완](docs/delivery/DELIVERY_REVIEW_20261019.md)

비보호 둘째 겨울을 개발에 편입했고 같은 지역을 반복 비교했으므로 새 독립 평가나 공식 성적이 아닙니다. 보호 3곳 정답은 추가 학습·선택·검증에 사용하지 않았습니다. 결빙 Recall(실제 결빙을 찾아낸 비율)은 0.739628로 v2와 같습니다. 위 표는 입력 가용 범위를 맞춘 비교입니다. 과거 CSV 정책의 ASOS F1 0.036392와 혼동하지 않으며 날짜·지점 분모와 오경보(FP)·미탐(FN)을 함께 보고합니다.

탐색한 범위에서 추가 이득이 작아지는 것을 확인했으며 모든 개선 가능성을 소진했다는 뜻은 아닙니다. 앞선 v2의 6.08% 개선·첫 겨울 악화 기록은 [이전 연구](docs/delivery/AWARD_UPGRADE_20261024.md)에 보존합니다. 대회 제출·외부 공개는 수행하지 않았습니다.

과거 72개 기온·노면 결합과 인접 ASOS 대체의 미채택 기록도 보존합니다. 보호 예측의 입력 부족 18행은 계속 NA입니다. [과거 입력 공백 검토](docs/research/AIR_ROAD_AND_INPUT_GAPS_20261016.md)

## 처음 읽는 순서

1. [처음 읽는 안내](docs/START_HERE.md)와 [진행 현황](docs/STATUS.md): 용어·버전·완료한 일·한계
2. [폴더 구조](docs/STRUCTURE.md): 코드·데이터·실험·제출물 위치
3. [실행 스크립트 안내](scripts/README.md): 검증·분석·후보 패키징 진입점
4. [문서 목록](docs/README.md): 대회·데이터·검증·연구·제출·과거 기록

## 분석 질문과 데이터

| 항목 | 내용 |
| --- | --- |
| 질문 | 미관측 노면온도와 Ice를 추정하고 새 지점·겨울에서도 성능을 유지할 수 있는가? |
| 입력 | RWIS 노면온도·상태, ASOS·AWS 기상, 도로·교량·터널·지형 |
| 기간 | 2024년 11월–2025년 2월 / 2025년 11월–2026년 2월, 10분 단위 |
| 개발 | 허용 대회 14곳 + 비대회 9곳의 두 겨울 |
| 보호 | 부곡교 12410·삼봉 33411·해전 23402. 학습·모델 선택·주변 참조에서 제외 |
| 정답 | 원본 상태 `04` Ice만 결빙. 미정의·결측은 평가에서 제외 |
| 배포본 | 최신 연구는 `20261007`, 루트 기본 환경은 `20260915` 보존본 |

[변수 사전](docs/data/VARIABLE_DICTIONARY.md) · [검증 설계](docs/validation/VALIDATION_PROTOCOL.md)

## 방법과 결과 해석

평가 그룹을 전처리·학습·후보 선택에서 제외하고 목표 시각보다 엄격히 이른 관측만 사용합니다. 온도 오차와 함께 결빙의 오경보·미탐·짧은 사건 손실을 비교합니다.

과거 첫 겨울 후보의 개발 전체 행 MAE는 1.232271°C에서 1.200531°C로 2.58% 감소했습니다. 위 두 겨울 결과와 평가 범위가 다르므로 직접 비교하지 않습니다. 개발 자료를 반복 비교한 결과이며 새 지점 일반화와 공식 점수를 입증하지 않습니다. 후속 공간 평가에서는 온도 평균 개선과 결빙 사건 손실이 함께 나타나 여러 후보를 미채택했습니다.

[상세 실험·실패 사례](docs/research/WEATHER_MEMORY_REVIEW_20261013.md) · [과거 README의 전체 결과](docs/history/PROJECT_OVERVIEW_20261014.md)

## 실행 방법

Windows·Python 3.11·CPU로 개발했습니다. 의존성은 [requirements.txt](requirements.txt)에 고정했습니다. 원본 없이 수행하는 검증은 다음과 같습니다.

```powershell
python -m pip install -r requirements-dev.txt
python -m pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cpu
$env:OMP_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
python -m pytest -q tests
python scripts/check_repository.py --include-untracked
python scripts/check_markdown.py --include-untracked
```

함수형 pytest 검사와 기존 unittest 검사를 함께 실행합니다. `pytest.ini`가 보존된 과거 제출 폴더를 수집 대상에서 제외합니다. PyTorch는 자체 MLP 비교 검사용이며 최종 HGB 추론에 필요하지 않습니다. CPU 설치 명령은 [PyTorch 2.7.1 공식 안내](https://pytorch.org/get-started/previous-versions/)를 따릅니다. LightGBM·XGBoost를 포함한 연구 계열의 추가 버전은 [requirements-research.txt](requirements-research.txt)에 고정했습니다. CI도 같은 합성 검사·저장소 검사·GFM 렌더 검사를 실행하도록 구성했습니다. 비공개 저장소에는 코드·설정·출력 없는 노트북·집계 문서만 관리합니다.

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
