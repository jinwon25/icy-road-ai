# 분석 결과 읽는 순서

[최종 보고서](delivery/FINAL_ANALYSIS_REPORT.md)는 문제·자료·모형·실험·공간 결과·현장 확인 계획을 설명한다. GitHub에서 읽을 수 있는 본문과 집계 도표이며 원자료나 실행 모형을 포함하지 않는다.

## 먼저 확인할 결과

노면온도 MAE는 학습 제외 3지점 평균 0.978°C다. 같은 103,131개 관측쌍에서는 기본 12특성 회귀보다 MAE가 14.6% 낮았다. MAE는 오차의 절댓값 평균이며 작을수록 관측 온도에 가깝다.

결빙 정밀도는 0.0195, 재현율은 0.5936, F1은 0.0326이다. 실제 Ice가 있는 한 지점의 날짜별 지표를 평균한 값이다. 정밀도는 결빙으로 판정한 것 중 실제 Ice의 비율, 재현율은 실제 Ice 중 찾아낸 비율이다. 전체 관측의 TP·FP·FN을 합쳐 한 번 계산한 비율과 다르다. 온도 추정의 개선과 낮은 결빙 탐지 성능을 함께 읽어야 한다.

중복 기상 입력을 합친 기준 조합에는 3구간·2개 범위가 남았다. 결빙이 확인된 신규 구간 수가 아니라 추가 계측·시설 확인 후보 수다. 기존 공개 목록과 75개 선정 기준의 민감도를 함께 제시했다. 현장 기록은 미측정 상태다.

## 로컬 완성물 열람

참가 권한이 있는 작업공간에서 `outputs/private/competition_submission/`을 연다. GitHub 복제본에는 아래 파일이 없으며 대회 제출용 자료를 별도로 갖춰야 한다.

| 경로 | 확인할 내용 |
| --- | --- |
| `icy_road_model/start.html` | 핵심 결과·비교 근거·결빙의 한계 |
| `icy_road_model/demo/index.html` | 주제별 분석, 비교 범위 선택, 8개 장면의 실행 영상 |
| `icy_road_model/report/analysis_report.pdf` | 14쪽 보고서와 책갈피·질문별 이동 |
| `icy_road_model/index.html` | 노선·겨울·기상 변수별 지도 |
| `icy_road_model/maps/sections.html` | 기존 목록 대조와 선정 기준 민감도 |
| `icy_road_model/results/field/index.html` | 인접 비교 후보와 빈 측정 기록 양식 |
| `icy_road_model/README.md` | 설치·학습·추론·전체 기간 재현 명령 |

지도와 데모는 별도 서버 없이 Chrome·Edge에서 열린다. [현재 상태](STATUS.md) · [공식 기준](competition/OFFICIAL_RULES_AND_RUBRIC_20261106.md)
