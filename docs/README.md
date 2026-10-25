# 문서 안내

이 페이지는 현재 결과와 과거 근거를 찾아가는 목차입니다. **처음 읽는다면 [프로젝트·지표·버전 설명](START_HERE.md)부터 확인하세요.** 날짜가 붙은 실험 문서는 그때의 조건과 판단을 보존하며, 현재 상태를 뜻하지 않습니다.

최신 후속 연구는 [기온 기준선의 제한 보정 64후보·69행 비교](research/ANCHORED_ICING_20261025.md)와 [제설·센서·추가 검증 지역 확보](research/ICING_ACQUISITION_20261025.md)입니다. 최고 고정 후보의 소폭 이득과 내부 선택 절차의 실패를 구별하고, 새 4개 지역의 기상 입력 23,048행 확보와 정답 미조회 상태를 설명합니다. 기존 v5 모델·ZIP은 보존하며 이번 연구가 그 ZIP 안에 들어 있다고 표현하지 않습니다.

10월 25일 [공식 규정·제출 일정](competition/OFFICIAL_UPDATE_20261025.md)을 상세 본문과 참가서약까지 재확인했습니다. 결과물 날짜는 공식적으로 별도 공지 예정이며, 데모에 서비스 구축이 필수가 아니라는 답변을 반영했습니다. 새 연구의 [문헌·공개 구현](research/ICING_REFERENCES_20261025.md)과 [전이·임계값 비교](research/ICING_TRANSITION_REVIEW_20261025.md)를 연결합니다.

현재 v5는 [결빙 전이 연구·최신 규정·문서 정리](research/ICING_TRANSITION_REVIEW_20261025.md)를 추가하고 아래 모델과 결과물을 보존합니다.

앞선 v4: [후속 11개 온도 대조·14개 결빙 상태 정책과 구간 탐색](delivery/FOLLOWUP_UPGRADE_20261024.md)을 완료하고 v3 모델을 유지했습니다. [기존 모델·실행 계약·검산](delivery/EXTENDED_UPGRADE_20261024.md), [확장 실험](research/EXTENDED_SEARCH_20261024.md), [최신 논문·GitHub·Hugging Face와 대회 조건 검토](research/OPEN_SOURCE_REVIEW_20261024.md)를 함께 확인합니다. 같은 개발 기준의 온도 MAE는 이전 v2보다 13.66% 낮고, 결빙 판정은 v2를 유지합니다.

앞선 v2: [두 겨울 후보](delivery/AWARD_UPGRADE_20261024.md). 앞선 [CSV 정리](delivery/DELIVERY_UPGRADE_20261024.md)는 v1의 기록이며 [열·단위·집계 규약](delivery/CSV_CONTRACT.md)은 v3의 두 온도 출력을 포함합니다.

현재 상태와 제출 준비를 먼저 보고, 필요할 때 데이터·검증·실험 근거를 찾아 읽습니다. 과거 기록의 수치를 현재 성능으로 해석하지 않습니다.

[프로젝트 소개](../README.md) · [진행 현황](STATUS.md) · [폴더 구조](STRUCTURE.md) · [스크립트 안내](../scripts/README.md)

## 처음 읽는 순서

1. [처음 읽는 안내](START_HERE.md): 해결할 문제, 온도와 결빙의 차이, 용어와 버전.
2. [현재 진행 현황](STATUS.md): 완료한 일, 채택한 모델, 아직 남는 한계.
3. [최신 공식 규정·일정](competition/OFFICIAL_UPDATE_20261025.md): 확정 조건과 공지 대기 항목.
4. [제한 보정 연구](research/ANCHORED_ICING_20261025.md)와 [자료 확보](research/ICING_ACQUISITION_20261025.md): 최신 방법·결과·한계. 배경은 [기준선 미탐 원인](research/ICING_GAP_AND_SYNOPTIC_20261025.md), [앞선 자료·문헌](research/ADDITIONAL_ICING_SOURCES_20261025.md)에서 확인합니다.
5. [v5 추가 내용](research/ICING_TRANSITION_REVIEW_20261025.md), [보존한 v4 구성과 검증](delivery/FOLLOWUP_UPGRADE_20261024.md), [CSV 규약](delivery/CSV_CONTRACT.md): 결과물 읽기.
6. [검증 규약](validation/VALIDATION_PROTOCOL.md)와 [스크립트 안내](../scripts/README.md): 실행·검산. [상세 실행 이력](delivery/RUNBOOK.md)은 필요한 단계만 참고합니다.

## 대회

- [공식 상세·참가서약 재확인과 데모 답변 — 2026-10-25](competition/OFFICIAL_UPDATE_20261025.md)
- [공식 새 게시물과 미확인 범위 — 2026-10-19](competition/OFFICIAL_UPDATE_20261019.md)
- [공식 사이트 전체 재확인 — 2026-10-16](competition/OFFICIAL_UPDATE_20261016.md)
- [대회 요구사항과 적용 범위 — 2026-10-25](competition/COMPETITION_REQUIREMENTS.md)
- [공식 Q&A633 답변과 일별 평가 후속 검증 — 2026-10-13](competition/OFFICIAL_QNA_20261013.md)
- [공식 정보 재검토와 저장소 검증 — 2026-10-09](competition/OFFICIAL_REVIEW_20261009.md)
- [문제설명·데이터 설명·Q&A 통합 검토 — 2026-10-07](competition/OFFICIAL_TABS_REVIEW_20261007.md)
- [공식 정보 변경·확인 기록 — 2026-10-02](competition/OFFICIAL_UPDATE_20261002.md)
- [Q&A 반영과 수정 데이터 검증 — 2026-10-07](competition/OFFICIAL_UPDATE_20261007.md)
- [공식 사이트 추가 정보와 오프라인 재현 — 2026-10-13](competition/OFFICIAL_UPDATE_20261013.md)
- [운영진 확인 질문 — 2026-10-13](competition/QUESTIONS_FOR_ORGANIZER.md)

## 데이터

- [자료 품질 점검 — 2026-09-23](data/DATA_AUDIT.md)
- [개발 자료 탐색 — 2026-09-23](data/EDA_REPORT.md)
- [변수 사전과 품질 요약](data/VARIABLE_DICTIONARY.md)

## 검증

- [평가·제출 준비 현황 — 2026-10-14](validation/EVALUATION_STATUS.md)
- [학습·평가 분리와 지표 계산 규칙 — 2026-10-02](validation/VALIDATION_PROTOCOL.md)

## 연구

- [결빙 전이와 임계값 정확 탐색 — 2026-10-25](research/ICING_TRANSITION_REVIEW_20261025.md)
- [새 논문·공개 구현과 이용조건 — 2026-10-25](research/ICING_REFERENCES_20261025.md)
- [온도 확장 연구 — 2026-10-24](research/EXTENDED_SEARCH_20261024.md)
- [논문·GitHub·Hugging Face 자료 검토 — 2026-10-24](research/OPEN_SOURCE_REVIEW_20261024.md)
- [기온·노면 72개 결합과 관측 공백·미사용 지점 검토 — 2026-10-16](research/AIR_ROAD_AND_INPUT_GAPS_20261016.md)
- [심사 관점 후속 연구·새 지점 평가 — 2026-10-10](research/AWARD_READINESS_REVIEW_20261010.md)
- [단순 기온 기준과 보정 결과](research/BASELINE_REPORT.md)
- [실행·실험 기록](research/EXPERIMENT_LOG.md)
- [시설 거리·과거 기상 입력 비교](research/FACILITY_HISTORY_REPORT.md)
- [후속 실험을 선택한 근거](research/FOLLOWUP_EVIDENCE.md)
- [미사용 8개 지점 사전 고정 평가 — 2026-10-09](research/FRESH_STATION_REVIEW_20261009.md)
- [첫 결빙 분류 모델과 실패 분석 — 2026-09-23](research/ICE_BASELINE_REPORT.md)
- [결빙 탐지 병목 진단과 후속 실행안 — 2026-10-09](research/ICE_BOTTLENECK_REVIEW_20261009.md)
- [결빙 학습 가중치·선택 기준 후속 검토 — 2026-10-09](research/ICE_GROUP_BALANCED_REVIEW_20261009.md)
- [결빙 방법론 여섯 가지의 공간 비교 — 2026-10-10](research/ICE_METHODOLOGY_REVIEW_20261010.md)
- [비선형 결빙 모델과 오경보 분석 — 2026-10-02](research/ICE_NONLINEAR_REPORT.md)
- [온도 교차 추정·노면상태 분류와 점수 이전 진단 — 2026-10-09](research/JOINT_SURFACE_REVIEW_20261009.md)
- [방법론 블렌딩의 검증과 후속 판단](research/METHOD_BLENDING_REVIEW_20261010.md)
- [주변 도로 관측을 추가한 노면온도 비교](research/NEIGHBOR_RWIS_REPORT.md)
- [다음 겨울·미관측 지점의 노면온도 검증 — 2026-10-02](research/NEIGHBOR_TRANSFER_REPORT.md)
- [정정 자료 배포 전 점검·구간 생성 — 2026-10-02](research/PRE_CORRECTION_WORK_REPORT.md)
- [공식 자료·선행연구 목록](research/REFERENCES.md)
- [점수 보정·노면상태와 온도 진단 — 2026-10-09](research/SCORE_CALIBRATION_REVIEW_20261009.md)
- [전북 두 겨울 구간 기상 노출·환경 근거 — 2026-10-09](research/SEGMENT_EXPOSURE_REVIEW_20261009.md)
- [고정 평균 온도 후보와 새 호남 지점 검증 — 2026-10-10](research/TEMPERATURE_MEAN_AND_BLIND_REVIEW_20261010.md)
- [추정 온도·수분 결빙 가안과 완료된 다음 겨울 검증 — 2026-10-09](research/THERMAL_ICE_AND_RESERVED_REVIEW_20261009.md)
- [미해결 사항의 위치와 평가 분모 및 입력 범위 검토](research/UNRESOLVED_EVIDENCE_REVIEW_20261010.md)
- [거리 변수 제거·기상망 확장 후속 검토 — 2026-10-10](research/WEATHER_DISTANCE_AND_NETWORK_REVIEW_20261010.md)
- [기상 단독 온도 모델 개선과 관측소 대표성 후속 검토 — 2026-10-09](research/WEATHER_FALLBACK_REVIEW_20261009.md)
- [기상 자료를 결합한 노면온도 모델 — 2026-09-23](research/WEATHER_FUSION_REPORT.md)
- [기상 이력 대조군과 온도·결빙 균형 후보 — 2026-10-13](research/WEATHER_MEMORY_REVIEW_20261013.md)

## 제출

- [단순 기준선·모델 카드·CSV·ZIP 복원 수정 — 2026-10-16](delivery/REVIEW_RESPONSE_20261016.md)
- [10월14일 대회 현황과 제출 후보 후속 검토](delivery/COMPETITION_STATUS_20261014.md)
- [결빙점 가중 모델 검증과 보고서 개편](delivery/MODEL_REPORT_UPGRADE_20261014.md)
- [연구 결과물 인계·마감 판단 — 2026-10-09](delivery/RESEARCH_DELIVERY_REVIEW_20261009.md)
- [단계별 실행 안내](delivery/RUNBOOK.md)
- [제출 후보 패키지와 추가 판정 검증](delivery/SUBMISSION_CANDIDATE_20261013.md)

## 과거 기록

- [누적 진행 이력 — 당시 상태 보존](history/PROJECT_STATUS.md)
- [이전 README 전체 결과·소개](history/PROJECT_OVERVIEW_20261014.md)

## 용어와 해석

| 용어 | 뜻 |
| --- | --- |
| MAE | 온도 예측 절대 오차 평균. 전체 행 평균과 지점 균등 평균을 구별 |
| FP / FN | 실제 비결빙의 오경보 / 실제 결빙의 미탐 |
| OOF | 해당 지점을 학습하지 않은 모델의 예측 |
| 봉인 | 평가 전에 모델·입력·예측을 고정하고 해시를 기록하는 절차 |
| 보호 지점 | 학습·선택·주변 참조에서 제외한 최종 평가용 지점 |
| 사건 | 연속된 10분 결빙을 묶은 사례. 단일 시점 사건도 별도 확인 |

공식 점수·반복 개발 점수·개봉한 새 공간 평가를 구별합니다. 전체 용어 풀이는 [이전 문서 안내](history/DOCUMENT_INDEX_20261014.md)에 보존했습니다.

[AI 지원 기록](../AI_USAGE.md) · [공유 조건](../.github/PUBLICATION.md)
