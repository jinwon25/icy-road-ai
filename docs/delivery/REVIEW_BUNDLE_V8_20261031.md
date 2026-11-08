# v8 통합 보고서와 공식 취약구간 비교

v8은 13쪽 보고서, 최신 공식 목록의 추정 위치, 두 겨울 노출 비교와 검토 자료를 통합한 비공개 묶음입니다. 온도 모델 v3·결빙 판정 v2는 기존과 같습니다. 후속 98적합의 실패를 숨기지 않고 새 공간 정보의 활용 범위·위치 오차·기상자료 공유를 설명합니다. 실제 대회 접수 완료본은 아닙니다.

## 현재 결과와 진입점

- 작업 폴더: `outputs/private/submission_candidate_20261031_v8/`
- 현재 보고서: `reports/analysis_report_v8.pdf`와 [동일 원고](ANALYSIS_REPORT_20261031.md)
- 공식 목록 화면: `research/latest/official_inventory_viewer_20261031_v1/index.html`
- 실행 노트북: `notebooks/submission_review_v8.ipynb`
- 포함 집계 검토: `notebooks/latest_research_review_v8.ipynb`

새 화면은 500m 843개 보고 구간 중 821개의 제한적 이정 보간, 문제 목록 11개·최신 목록 8개의 전북 도형 연결을 제공합니다. 최신 목록의 본부 관할과 행정구역을 구별해 경계 구간을 포함했습니다. 조건 기준으로 선택된 318개 보고 구간은 방향별 8개 연속 범위입니다. 정확히 상위 25%, 독립적인 318개 위험 발견, 측량으로 검증한 위치를 의미하지 않습니다. [분석·검산·자료의 한계](../research/OFFICIAL_CHAINAGE_COMPARISON_20261031.md)

온도 MAE 1.145698°C·13.66% 감소는 동일 개발 9곳·두 겨울의 비교입니다. 결빙 F1 0.026554는 기온 기준선 0.036601보다 낮습니다. [목적함수](../research/OBJECTIVE_ICING_20261031.md), [재분석 입력](../research/REANALYSIS_INPUTS_20261031.md), [누적 기상 조건](../research/ANTECEDENT_FORCING_20261031.md)의 추가 연구에서도 안정적인 개선을 확인하지 못해 실행 모델을 유지했습니다.

## 재현 범위

Windows·Python 3.11·CPU에서 버전을 고정한 환경 파일을 사용합니다. 최종 모델의 포함 자료 학습·추론과 두 검토 노트북에 외부 AI API·인증키가 필요하지 않습니다. 최초 패키지 설치는 별도입니다. 묶음 루트에서 실행합니다.

```powershell
python -m pip install -r requirements-notebook.txt
python scripts/review_submission_bundle.py --smoke --output local_review/my_review.json
python scripts/check_notebook.py notebooks/latest_research_review_v8.ipynb
python -X utf8 code/train.py --output local_review/my_refit
```

최종 실행 노트북의 5개 코드 셀은 v7과 같습니다. 설명과 현재 보고서 경로만 갱신했습니다. 후속 검토 노트북은 2개 코드 셀에서 포함 연구 집계·검산·공간 자료를 확인합니다. 날짜별 연구 노트북과 전체 실패 실험의 재적합은 원 비공개 작업 공간의 추가 입력이 필요한 경우가 있어 기본 실행과 구별합니다.

실패 실험의 집계·선택·검산 및 일부 소형 모델은 포함하지만 모든 원자료·예측 캐시를 넣지 않습니다. 공개 자료의 원문 수집 코드와 이용조건은 연구 문서에 연결합니다. 불확실한 CCTV 원 좌표는 새 지도 묶음에 넣지 않고 집계 진단을 보존합니다.

## 검증 기록

전체 테스트 442개·하위 검사 7개가 통과했고 기존 pandas 경고 1건이 남았습니다. 13쪽 PDF를 모두 이미지로 검토했으며 지도 범례·노선명·연결 표시를 보완했습니다. 보고서 수치를 기존 JSON에 연결하고 페이지 수·제목 위치·문자 경계를 검사했습니다. 기존 핵심 실행 자산 506개를 해시로 보존한 새 폴더를 준비했습니다.

v8 폴더에서 **예측 144행의 정확한 일치, 현재 노트북 5개 코드 셀과 후속 검토 노트북 2개 코드 셀 실행, 핵심 자산 506개 보존**을 확인했습니다. `validation/v8_delivery.json`의 상태는 `v8_delivery_verified`입니다. 새 실제 화면 영상은 `demo/inventory_comparison_walkthrough.webm`이며 26.44초·661프레임·25fps·1320×1000입니다. 목록 변경·구간 선택·확대를 확인했고 외부 요청·페이지 오류는 0건, 상대 CSV·GIS 연결은 3개 모두 유효했습니다.

두 ZIP의 단일 최상위 폴더·구성원·바이트 수·SHA-256 전량 검증을 완료했습니다. `outputs/private/submission_channels_20261031_v8/submission_receipt.json`의 상태는 `two_channel_archives_verified`입니다. ZIP 내부 문서는 압축 전 실행 확인 시점의 기록이며, 압축의 최종 해시와 완료 상태는 상위 영수증과 아래 표를 따릅니다. 과거 ZIP과 보호 봉인을 새 검증으로 덮어쓰지 않았습니다.

| 제출 칸 | 실제 로컬 ZIP | 바이트 | SHA-256 |
| --- | --- | ---: | --- |
| 문서자료 | `outputs/private/submission_channels_20261031_v8/icy_road_documents.zip` | 553,090 | `d80e3f7516444058b4a8cf22bbcaa7f174e977a80936160604b63eaa83cccd0d` |
| 모델자료 | `outputs/private/submission_channels_20261031_v8/icy_road_model.zip` | 446,137,175 | `9bba073e5f6608322b367c085eb05b8a24aaf6001284b34dd803ca3af095bd50` |

명세 자체를 제외한 문서자료 5파일·모델자료 1,917파일을 모두 대조했습니다. 최종 저장소 검사도 추적·새 파일 848개에서 인증정보 형식·제외 자료·노트북 출력 혼입 없이 통과했습니다. 원 사용자 문서와 로그의 해시도 유지합니다.

## 제출 칸 구분

문서자료에는 현재 보고서·공식 목록 비교 그림·결빙 조건 기준표를, 모델자료에는 실행 모델·데이터·전체 코드·환경·노트북·영상·GIS·CSV·검산 기록을 넣습니다. 각각 하나의 최상위 폴더를 가진 ZIP입니다. 10월 27일 접수 개시는 확인했지만 마감 날짜는 제공 공지 본문에 없습니다. 참가신청 종료일을 결과물 제출 마감으로 대신하지 않습니다.
