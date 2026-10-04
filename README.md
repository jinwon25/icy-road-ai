# icy-road-ai

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
[![검증](https://github.com/jinwon25/icy-road-ai/actions/workflows/checks.yml/badge.svg?branch=main)](https://github.com/jinwon25/icy-road-ai/actions/workflows/checks.yml)

기상관측·도로환경 자료를 결합해 미관측 도로의 노면온도와 결빙 상태를 추정하는 개인 프로젝트입니다. 전북도 고속도로 구간별 위험정보를 만들기 위해 데이터 품질, 관측소 간 전이, 시간 누출과 오경보를 함께 검토합니다.

## 현재 상태

**2026 DATA·AI 분석 경진대회 참가 중 · 개발 단계**입니다. 문서 기준일은 2026-10-04, 최근 모델 실험은 2026-10-02이며 현재 자료는 **20260915 버전**입니다. 10월 6일까지 오류 정정·관측소 추가가 예고돼 기존 수치를 최종 성능으로 확정하지 않았습니다.

원본 자료·신청서·모델·예측 파일은 저장소에 포함하지 않습니다. 코드와 집계 문서는 우선 비공개로 보관하며 대회 중 공개 범위는 별도 확인합니다. [공유 범위](.github/PUBLICATION.md) · [공식 변경사항](docs/OFFICIAL_UPDATE_20261002.md)

## 분석 질문과 데이터

| 항목 | 내용 |
| --- | --- |
| 질문 | 도로기상 관측 장비가 없는 지점의 노면온도와 결빙 상태를 어떻게 추정할 수 있는가? |
| 자료 | 대회 제공 RWIS·ASOS·AWS, 교량·터널·도로·DEM·하천 자료 |
| 평가 기간 | 2024-11~2025-02, 2025-11~2026-02의 두 겨울 |
| 관측 단위 | 도로기상 10분 시점, 지점별 일별 분류 지표 |
| 개발 검증 | 공식 보호 지점을 제외한 14개 RWIS의 공간·시간 분리 검증 |
| 보호 지점 | 부곡교 12410·삼봉 33411·해전 23402: 학습·모델 조정에서 제외 |

## 방법과 주요 결과

1. **자료 감사**: 원본 ZIP의 파일명·SHA256을 고정하고 시간 경계, 결측·미정의 상태 코드, 관측소 위치와 입력 가용성을 점검했습니다.
2. **미관측 지점 검증**: 관측소를 제외하는 LOSO와 첫 겨울 학습 → 다음 겨울의 제외 지점 평가를 구분했습니다. 주변 관측값은 목표 시각 이전 자료로 제한하며 입력 지연 민감도도 확인했습니다.
3. **노면온도 추정**: 공간·시간 분리 검증의 14개 지점·241,201행에서 기상 입력 MAE **1.828°C**, 기상·주변 RWIS 고정 1:1 혼합 MAE **1.389°C**였습니다. 지점별 MAE의 단순 평균이며 공식 보호 지점 점수가 아닙니다. [설계와 상세 결과](docs/NEIGHBOR_TRANSFER_REPORT.md)
4. **결빙 분류 실패 분석**: 로지스틱·비선형 기준선을 비교했습니다. 일평균 F1 개선과 함께 오경보가 크게 늘어 최종 모델로 채택하지 않았습니다. 노면온도 개선이 결빙 분류 성능 개선을 보장하지 않습니다. [비선형 결과와 오경보](docs/ICE_NONLINEAR_REPORT.md)
5. **공간 결과 준비**: 최대 1km 도로 구간 467개를 만들고 내보내기를 확인했습니다. 현재 구간에는 위험 점수가 없으며 완성된 결빙 위험도 지도가 아닙니다. [정적 구간 검토](docs/PRE_CORRECTION_WORK_REPORT.md)

## 실행 방법

로컬 개발 환경은 Windows·Python 3.11이며 CPU 기반 실험입니다. 주요 버전은 pandas 2.2.3, scikit-learn 1.6.1, GeoPandas 1.1.3입니다. 전체 환경은 [requirements.txt](requirements.txt)를 참고하세요.

원본 없이 가능한 코드 검증:

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/check_repository.py
```

단위 테스트는 합성 입력으로 시간 경계·보호 지점 제외·일별 지표 분모·도로 구간 분할을 확인합니다. 전체 모델 성능 검증을 대신하지 않습니다.

참가 권한이 있는 로컬 환경에서 원본과 필요한 캐시를 갖춘 경우:

```powershell
python scripts/audit_data.py --limit-files 3
python scripts/baseline_asos.py --limit-days 2
python scripts/check_notebook.py
```

전체 학습은 고비용 작업이므로 [실행 단계 설정](config/notebook_workflow.json)과 [단계별 실행 안내](docs/RUNBOOK.md)를 확인하고 선택합니다. 노트북 기본 실행에도 원본과 기존 비공개 산출물이 필요합니다. 저장된 노트북에는 실행 출력이 없습니다. 새 자료는 별도 감사 후 캐시를 다시 만들어야 합니다.

## 파일 구성

| 경로 | 역할 |
| --- | --- |
| `src/` | 지표·시간 결합·특징·검증·도로 구간 처리 |
| `scripts/` | 자료 감사·기준 모델·비교·노트북 실행 진입점 |
| `notebooks/analysis_review.ipynb` | 분석 흐름과 결과 검토 |
| `config/` | 원본 버전·평가 규약·실험·노트북 단계 설정 |
| `tests/` | 데이터 없이 수행하는 로직 검증 |
| `docs/` | 자료 정의·검증 설계·실험 결과·상세 이력 |
| `AI_USAGE.md` | AI 지원 범위와 주요 검토 기록 |
| `outputs/private/` | 로컬 전용 산출물·캐시, Git 제외 |

[진행 현황](docs/PROJECT_STATUS.md) · [평가 대비 현황](docs/EVALUATION_STATUS.md) · [검증 규약](docs/VALIDATION_PROTOCOL.md) · [자료 사전](docs/VARIABLE_DICTIONARY.md) · [실험 목록](docs/EXPERIMENT_LOG.md)

## 해석과 남은 작업

- 보호 3개 지점의 최종 평가, 최종 모델·추론 진입점, 위험도 기준표·지도·데모영상은 미완료입니다.
- 일별 무결빙·무예측 날짜 제외와 지점별 평균 기준은 확인했지만 불완전 날짜·일부 0분모·제출 스키마·관측 자료 발표 지연은 추가 확인이 필요합니다.
- 개발 자료의 연관성과 모델 비교를 사고 발생·피해 확률이나 실제 운영 개선으로 해석하지 않습니다.
- 개인 프로젝트이며 Codex 지원을 사용했습니다. 구체적인 지원 범위와 참가자 검토가 필요한 사항은 [AI 활용 기록](AI_USAGE.md)에 구분했습니다.

## 출처와 이용 조건

[AIDA 공식 문제·참가 양식](https://aida.kisti.re.kr/competition/main/problem/PROB_000000000004604/detail.do) · [제출 공지](https://aida.kisti.re.kr/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId=564) · [공식 평가 Q&A](https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=556)

FHWA·기상청·공간 검증 논문의 적용 범위는 [1차 자료 목록](docs/REFERENCES.md)에 정리했습니다. 외부 관측 자료는 모델 입력에 추가하지 않았습니다. 제공 데이터는 참가 서약의 이용·보안·종료 후 폐기 조건을 따르며, 임의의 MIT 라이선스나 데이터 재배포 권한을 부여하지 않습니다.
