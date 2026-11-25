# 실행 스크립트 안내

공개본 검사는 [저장소 파일 검사](check_repository.py)와 [Markdown 검사](check_markdown.py)에서 시작합니다. 설치·테스트 명령은 [프로젝트 실행](../README.md#프로젝트-실행)에 있습니다. 아래 연구 스크립트의 입력 경로와 버전은 실험 당시 기준입니다.

## 최종 결과와 제출본

[현재 결과](../docs/STATUS.md)와 [최종 보고서 원고](../docs/delivery/FINAL_ANALYSIS_REPORT.md)를 먼저 읽는다. 전체 실행은 대회 원자료와 로컬 연구 자산이 필요하며 GitHub 복제만으로 제출본이 생성되지는 않는다.

- `evaluate_short_forcing_icing_20261106.py`, `evaluate_aws_short_forcing_20261106.py`: ASOS·AWS 단기 이력 후보의 지역 제외 학습과 내부 문턱 선택. 두 후보 모두 미채택했다.
- `audit_short_forcing_20261106.py`, `audit_aws_short_forcing_20261106.py`: 감쇠식·시간 경계·지점 분리·미래 입력 교란과 저장 모형 점수 재현.
- `verify_late_report_and_sources_20261106.py`, `final_requirements_delivery_review_20261106.py`: 보고서 수치·책갈피·링크와 규정·평가 입력 대조.
- `package_late_submission_20261106.py`: 문서자료·모델자료 ZIP 생성과 압축 해제본의 추론·지표 재현.
- `install_late_submission_20261106.py`: 검증한 제출본을 로컬 제출 경로로 반영하고 이전 제출본 보관.

편집·패키징 스크립트는 단계별 산출물과 검수 영수증을 사용했습니다. 실제 제출 코드에서는 [전체 기간 검산](../submission/source/code/check_full_validation.py), [ASOS 단기 이력](../submission/source/code/analyze_short_forcing_review.py), [AWS 단기 이력](../submission/source/code/analyze_aws_short_forcing_review.py)의 계산 순서를 확인할 수 있습니다. 입력표 폐기 후의 실행 범위는 [제출 소스 안내](../submission/README.md)에 적었습니다.


## 11월 2일 후속 점검·공간 이력·채택 풍속의 구간 적용

- [현재 묶음 점검](review_project_state_20261102.py): 기존 v12 폴더와 문서·모델 ZIP의 실제 구성원·바이트·해시를 읽기 전용으로 대조합니다.
- [공간·기상 이력 12적합](evaluate_weather_network_history_20261102.py) → [별도 검산](audit_weather_network_history_20261102.py) → [CSV·그림](summarize_weather_network_history_20261102.py): 147특성 후보는 두 검증 모두 악화해 미채택했습니다.
- [현재 69특성 풍속의 843구간 적용](project_wind_network_segments_20261102.py) → [전량 집계·보존·19구간 API 검산](audit_wind_network_segments_20261102.py) → [이전·현재·변화 지도](render_wind_network_segments_20261102.py): 기존 기온·습도·노면온도·결빙 결과를 보존하는 별도 출력입니다. 실제 완료 여부는 출력 폴더의 영수증을 확인합니다.

[후속 점검·결과·실행 위치](../docs/delivery/FOLLOWUP_REVIEW_20261102.md) · [입력 정의와 참고자료](../docs/research/NETWORK_HISTORY_PLAN_20261102.md) · [풍속 CSV 규약](../docs/delivery/CSV_CONTRACT.md#관측망-풍속-구간-적용--2026-11-02). 기존 완료 폴더를 덮어쓰지 않으며 연구 재실행에는 원 비공개 입력이 필요합니다.

## 앞선 기록: 주변 관측망과 풍속 개선을 통합한 v12

- [공간 관측망36적합](evaluate_weather_network_20261101.py)·[독립 검산](audit_weather_network_20261101.py): 고정계획과 허용23곳의 기상 정답만 사용합니다.
- [새 풍속 묶음 생성](build_wind_network_supplement_20261101.py)·[별도 위치 전체재학습 검증](verify_wind_network_supplement_20261101.py)·[CLI](predict_wind_network.py)·[재학습](retrain_wind_network.py).
- [입력 점검 화면](build_weather_network_viewer_20261101.py)·[1840조합 검증](audit_weather_network_viewer_20261101.py)·[후속 보고서](build_network_followup_20261101.py)·[v12 포장](package_review_v12.py).

연구 전체 재실행은 원 비공개 작업공간이 필요합니다. 기본 제출 실행과 독립 풍속 실행은 포함 자료로 재현하며 [입력 계약](../docs/delivery/WIND_NETWORK_20261101.md)을 따릅니다.

## 앞선 기록: 추가 검증·실행 프로필·기상 탐색 v11

`evaluate_weather_thermodynamics_20261101.py`·`audit_weather_thermodynamics_20261101.py`는 물리124입력·24적합·4재학습 검산, `evaluate_weather_catboost_20261101.py`·`audit_weather_catboost_20261101.py`는82입력·12적합·고정평균·2재학습 검산입니다. 모두 현재 습도 교체 조건을 넘지 못했습니다. `evaluate_frost_icing_20261101.py`·`audit_frost_icing_20261101.py`는 고정 서리 규칙의 봉인 후 반증입니다.

`predict_competition_profile.py --icing-profile ...`는 알려진 기온 기준선을 F1 우선 후보로 명시하거나 기존 v2를 그대로 실행합니다. `build_competition_profile_review_20261101.py`가 같은 개발 비교·실제 CLI·보호 예측의 온도/18NA 보존을 검증합니다. 기본 온도·기상 모형은 바꾸지 않습니다.

`build_weather_explorer_20261101.py`는 로컬 HTML의 지도·두 겨울 시계열·품질·CSV를 만들고 `audit_weather_explorer_20261101.py`는 수치·실제 브라우저·다운로드·모바일을 검증합니다. 브라우저 테스트 환경의 Node 경로는 원 작업 환경에 따라 지정합니다. 화면 자체는 Python·인증·외부 요청 없이 실행됩니다.

`build_followup_review_20261101.py`, `prepare_analysis_manuscript_v11.py`, `build_analysis_report_v11.py`, `package_review_v11.py`가 후속 지표·노트북·22쪽 보고서·실행 검토·두 ZIP을 연결합니다. [현재 결과와 실제 파일](../docs/delivery/REVIEW_BUNDLE_V11_20261101.md)

## 앞선 기록: 11월 1일 습도 이력·안정화·v10

`evaluate_weather_space_time_memory.py`는 순간/과거 입력의 지역·겨울 동시 제외 비교, `evaluate_weather_history_spatial_20261101.py --config ...`는 동일 두 겨울 공간 비교입니다. 초기 구현의 문맥 의존을 수정한 최종 실험은 `evaluate_weather_history_stable_20261101.py`와 `audit_weather_history_stable_20261101.py`이며 완료 결과의 소스 원본·집계 수정은 별도 finalizer 기록에 남습니다. 실패·수정 전 결과를 최종 수치로 사용하지 않습니다.

`predict_weather_history.py`·`retrain_weather_history.py`는 채택 습도의 24시간 문맥 추론·전체 학습 진입점입니다. `build_weather_history_supplement.py`가 별도 실행 자료를 만들고 `verify_weather_history_supplement.py`가 위치 이동·CLI·실제 Jupyter 전체 재학습을 검증합니다. 완료 출력 폴더는 덮어쓰지 않습니다.

`project_weather_history_segments_20261101.py`·`audit_weather_history_segments_20261101.py`는 843구간 기상 적용·전량 집계·대표 재추론, `render_weather_history_projection_20261101.py`는 새 지도입니다. `build_stable_weather_review_20261101.py`는 최종 지표·그림·연구 노트북을 만듭니다. `prepare_analysis_manuscript_v10.py`·`build_analysis_report_v10.py`·`package_review_v10.py`가 새 원고·19쪽 PDF·검토 폴더·두 ZIP을 준비합니다. [결과·실제 검증](../docs/delivery/REVIEW_BUNDLE_V10_20261101.md)

이 문서는 실행 목적에 맞는 스크립트를 찾는 입구입니다. `evaluate_*`는 비교 실험, `audit_*`는 저장 결과의 별도 검산, `check_*`는 코드·문서 검사를 뜻합니다. 학습·검산에는 `outputs/private/`의 허용 자료가 필요하며 GitHub만 내려받으면 해당 자료가 생기지 않습니다. [용어와 버전](../docs/START_HERE.md)

## 앞선 기록: 10월 31일 학습 목표 비교와 지표면 자료 확보

`prepare_analysis_manuscript_v8.py`·`build_analysis_report_v8.py`는 13쪽 통합 원고·수치 대조·PDF 렌더링을 수행합니다. 실제 시각 검토 영수증이 있어야 `package_review_v8.py --stage prepare`, `--stage verify`, `--stage package`를 순서대로 실행할 수 있습니다. v8 기본 실행 노트북과 포함 집계 노트북을 구별하고 기존 자산 506개를 보존합니다. `record_inventory_review_v8.py`는 복사된 화면의 실제 조작 영상과 상대 다운로드 경로를 검증합니다. [구성과 실제 검사](../docs/delivery/REVIEW_BUNDLE_V8_20261031.md)

`evaluate_antecedent_forcing.py`는 순간·누적 기상 입력을 같은 BCE 조건에서 20회 적합합니다. `audit_antecedent_forcing.py`는 별도 격자 필터의 입력 계산부터 모델·선택·평가까지 대조합니다. `build_antecedent_notebook.py`는 학습 예제·재추론·지표의 검토 노트북을 만듭니다. 완료 결과를 덮어쓰지 않으며 [실행 조건·수치·변경 기록](../docs/research/ANTECEDENT_FORCING_20261031.md)을 먼저 읽습니다.

`prepare_reanalysis_inputs.py`·`audit_reanalysis_inputs.py`는 원문·엄격한 과거 시간 연결을 검증합니다. `evaluate_reanalysis_temperature.py`·`evaluate_reanalysis_icing.py`와 각각의 `audit_*`는 추가 입력의 온도 8모델·분류 30모델을 비교·검산합니다. [완료 결과·실행 순서](../docs/research/REANALYSIS_INPUTS_20261031.md)

`fetch_public_vulnerable_sections.py`·`fetch_public_road_context.py`는 개인정보 없는 공식 파일 다운로드를 사용합니다. `analyze_vulnerability_inventory.py`는 두 목록의 시점 차이를, `prepare_official_culvert_anchors.py`는 CSV·DBF·SHP 원문 일치를 검사합니다. `align_official_culvert_chainage.py` → `build_vulnerability_comparison.py` → `audit_official_chainage_alignment.py`는 이정 보간·목록 비교·독립 계산 대조입니다. `build_chainage_review_viewer.py`·`audit_chainage_review_viewer.py`는 인터넷 없는 탐색 화면과 실제 브라우저 검사를 제공합니다. [조건·오차·검산](../docs/research/OFFICIAL_CHAINAGE_COMPARISON_20261031.md)

`evaluate_objective_icing.py`는 사전 고정한 네 손실을 지역 이중 제외 40모델로 비교합니다. `audit_objective_icing.py`는 전처리·추론·선택·지표·사건·블록 재표집을 별도 계산으로 대조합니다. [결과와 실행 순서](../docs/research/OBJECTIVE_ICING_20261031.md) · [연구 노트북](../notebooks/objective_icing_review_20261031.ipynb)

`fetch_reanalysis_inputs.py`는 기존 개발 지점만 대상으로 ERA5-Land 공개 입력을 수집합니다. `--limit 1`로 첫 원문·단위를 확인할 수 있고 같은 설정으로 재개합니다. 새 정답·보호 지점은 요청하지 않으며 완료 시 원문 해시·반환 격자·시간별 품질을 남깁니다. 결과는 사후 재분석 전용입니다.

## 앞선 10월 31일 두 ZIP 제출 준비와 재현 검사

`python scripts/package_submission_channels.py --output outputs/private/submission_channels_20261031`은 보존된 v7을 기반으로 문서자료·모델자료를 별도 폴더·ZIP으로 만듭니다. 기존 출력이 있으면 중단합니다. 모델·예측 해시 보존, 현재 노트북·144행 예제 실행, 문서 링크·인증정보 검사, 두 ZIP 전 구성원 검증을 수행합니다. 실제 업로드는 하지 않습니다. [요구사항 대조](../docs/delivery/FOLLOWUP_READINESS_20261031.md)

`review_submission_bundle.py --smoke`는 `current_notebook` 명세를 우선하고 과거 v7은 알려진 v7 노트북을 사용합니다. `--notebook <묶음 내부 경로>`로 명시할 수 있지만 manifest 밖의 파일은 거부합니다. 출력에 선택 경로를 남깁니다.

`review_official_updates.py --previous <완료 폴더> --output <새 폴더>`는 확인 불완전 시 원문·요약을 보존하고 종료코드 2를 반환합니다. 최신 규정의 해석은 수집 성공 여부와 별도로 확인합니다.

## 앞선 보고서 원고·PDF와 v7 검토 묶음

[현재 보고서](../docs/delivery/ANALYSIS_REPORT.md)와 [개편 근거](../docs/delivery/BENCHMARK_REVIEW_20261025.md)를 먼저 읽습니다. 모델링을 다시 실행하지 않고 기존 집계와 봉인된 예측을 사용합니다.

| 스크립트 | 역할 |
| --- | --- |
| `build_editorial_report.py --output <새 폴더>` | Markdown 원고·기존 집계에서 그림과 10쪽 PDF 작성, 핵심 수치·페이지·문자 경계 검사 |
| `package_review_v7.py --stage prepare` | 기존 v6 자산과 Git 인덱스 문서, 검수한 보고서를 새 v7에 복사 |
| `package_review_v7.py --stage verify` | 기존 자산 보존·문서 링크·예제 예측·노트북 실행 검사 |
| `package_review_v7.py --stage package` | 전체 파일·인증정보 검사 후 ZIP 생성 및 모든 구성원 대조 |

보고서 생성에는 연구 환경의 reportlab·PyMuPDF·matplotlib·markdown-it-py와 Windows 맑은 고딕이 필요합니다. PDF는 생성 후 전체 페이지를 렌더링하여 시각 검수해야 합니다. 패키징은 원 비공개 작업 공간과 완료한 검수 영수증이 필요하며 기존 출력 폴더·ZIP을 덮어쓰지 않습니다.

## 앞선 기온 시작값·시간 보정·정보량 진단과 v6 검토

[연구 결과](../docs/research/RESIDUAL_AND_INFORMATION_20261025.md)와 [v6 실행 안내](../docs/delivery/REVIEW_BUNDLE_V6_20261025.md)를 먼저 읽습니다. 기존 허용 개발 자료만 쓰며 보호 정답과 개봉한 새 4지역은 추가 학습·선택에서 제외합니다. 완료한 출력 경로는 재사용하지 않습니다.

| 스크립트 | 역할 |
| --- | --- |
| `evaluate_residual_icing.py` | 기온 시작값·가중치 3조건, 30적합·49정책의 내부 선택과 외부 지역 비교 |
| `evaluate_causal_trend.py` | 엄격히 과거 두 시간의 기온 변화·경과분으로 보정하는 10정책 비교 |
| `audit_residual_and_trend.py` | 30모델 독립 재학습·전량 마진·내부 선택·시간 입력·최종 지표 검산 |
| `diagnose_weather_information.py` | 동일 입력별 결빙·비결빙 중복과 정답을 알고 계산한 전체 행 F1 상한 진단 |
| `audit_weather_information.py` | 별도 튜플 계수로 8개 입력 구분의 72개 수치 대조 |
| `build_v6_review_brief.py` | 검산 완료 집계로 2쪽 검토 PDF 작성. 별도 페이지 렌더·시각 검수 필요 |
| `review_submission_bundle.py --smoke` | 묶음 루트에서 무결성 검사 후 예측 144행·예제 노트북 5개 코드 셀 실행 |
| `package_review_v6.py --stage prepare/verify/package` | 세 단계를 각각 순서대로 실행. v5 자산 보존·Git 인덱스 스냅샷·실행 검사·ZIP 전체 대조 |

패키징은 원 비공개 작업 공간과 완료 감사·PDF 검수 기록이 있어야 실행됩니다. `prepare/verify/package`는 하나의 문자열 옵션이 아니라 순서대로 호출할 세 옵션입니다. v6의 단순 추론 검사는 연구 원자료 없이 포함 자료로 실행합니다. 연구 재학습 입력까지 ZIP에 모두 들어 있지는 않습니다.

## 앞선 원문 이상 진단과 경보를 보존하는 추가 탐지

[결과·출처·한계](../docs/research/RWIS_CAUSE_AND_ADDITIVE_20261025.md)와 [미발송 자료 요청·수령 조건](../docs/research/RWIS_DATA_REQUEST_20261025.md)을 먼저 읽습니다. 아래 분석은 기존 4지역의 완료 평가를 수정하지 않으며 제출 모델을 바꾸지 않습니다.

| 스크립트 | 역할과 입력 |
| --- | --- |
| `review_rwis_anomaly_sources.py --output <새 비공개 폴더>` | 공식 지점·상태 PDF와 제설 공개 경로의 실제 응답 보존. HTTP 200이어도 PDF 서명을 별도로 확인 |
| `reprobe_rwis_anomalies.py --output <새 비공개 폴더>` | 이미 평가한 12213·33406의 정해진 8개 요청만 진단용 재조회. `secret.env`의 KMA 키 필요, 완료 점수 변경 없음 |
| `analyze_rwis_anomalies.py` | 앞선 원문 489개와 완료 평가를 읽어 240날짜의 누락·중복·좌표를 분해. 새 정답 복구 기능 없음 |
| `audit_rwis_anomalies.py` | 별도 CSV 집계로 분류·좌표·CCTV 실파일·기존 봉인 보존 확인 |
| `evaluate_additive_icing.py` | [고정 설정](../config/additive_icing_20261025.json)으로 기존 허용 23곳에서 20모델·57정책과 2선택 절차 비교 |
| `audit_additive_icing.py` | 저장 모델·전처리·가중치·훈련 분리·내부 전체 후보 지표와 선택 검산 |
| `report_rwis_additive.py` | 검산 완료 요약으로 원인·성능 집계 그림 생성 |

완료한 실행 예시는 다음과 같습니다. 경로를 그대로 재사용하면 원문·모델·감사·그림 보존 검사에서 중단합니다. GitHub 복제본에는 비공개 연구 입력이 없으므로 이 실행을 합성 테스트와 구별합니다.

```powershell
python scripts/review_rwis_anomaly_sources.py --output outputs/private/rwis_anomaly_sources_20261025_v1
python scripts/reprobe_rwis_anomalies.py --output outputs/private/rwis_anomaly_reprobe_20261025_v1
python scripts/analyze_rwis_anomalies.py
python scripts/audit_rwis_anomalies.py
python scripts/evaluate_additive_icing.py
python scripts/audit_additive_icing.py
python scripts/report_rwis_additive.py
```

CCTV 실제 파일은 공공데이터포털의 파일 상세 조회 → CAPTCHA 필요 여부 확인 → 허용된 다운로드 순서로 확보했습니다. 취득 원문·메타데이터·다운로드 영수증은 `outputs/private/rwis_anomaly_additional_sources_20261025_v1/`에 있습니다. 기관 계정·키 신청·제설 자료 다운로드까지 자동 수행하는 스크립트가 아닙니다.

## 새 4지역: 입력 검증·예측 사전 고정·일회 평가

[실험 보고서](../docs/research/BLIND_ICING_20261025.md)는 새 지역과 반복 개발 결과, 입력 품질과 센서 정답의 품질을 구별합니다. [설정](../config/blind_icing_20261025.json)은 정답 요청 전 고정한 후보·주 후보·성공 기준입니다. 기존 v5 제출 모델을 바꾸는 명령이 아닙니다.

| 스크립트 | 목적과 실행 단계 |
| --- | --- |
| `fetch_training_asos_parity.py` | 학습 ASOS 6곳의 같은 API 입력 확보. `--recover-cached`는 정상 수집 원문에서 실제 관측 누락을 보존하며 오프라인 복구 |
| `blind_icing_validation.py prepare` | 새/학습 기상 품질·단위·결측 비교와 엄격한 과거 연결 |
| `blind_icing_validation.py fit` | 허용 23곳만으로 두 모델 학습, 새 4곳의 전체 138,240행 예측 |
| `blind_icing_validation.py seal` | 후보·모델·입력·예측·평가 코드 고정. 과거 요청 이력이 있으면 중단 |
| `audit_blind_icing.py prediction` | 정답 요청 전 시각·1,797,120입력값·모델·전처리·가중치 검산 |
| `blind_icing_validation.py collect` | 봉인·사전 감사 통과 후 동일 960개 날짜 구간 수집 |
| `resume_blind_icing_transport.py` | 긴 응답을 나눠 재개. 모든 요청에 공통 간격 제한, 단일 작성자로 기록 보존 |
| `blind_icing_validation.py evaluate` | 전체 수집 완료 후 고정 4후보의 일회 평가·사건·불확실성·성공 조건 계산 |
| `audit_blind_icing.py result` | 별도 일별 집계·사건 구현과 상태 매핑으로 검산 |
| `audit_blind_icing_empty_adapter.py` | 원래 사후 감사의 빈 시각 열 오류를 메모리 자료형만 보완해 재개. 관측 파일·결과·원 감사 코드는 유지 |
| `verify_blind_icing_completed.py --output <새 비공개 JSON>` | 완료 원문을 다시 파싱해 960구간·정규화·요청 범위·성공 조건·봉인·v5 ZIP을 읽기 전용 재검산 |
| `reproduce_blind_icing_models.py` | 허용 자료만으로 모델 재적합, 봉인 예측과 전량 대조 |
| `evaluate_asos_parity_development.py` | 기존 9개 개발 지점에서 같은 API 형식으로 네 지역 제외 진단. 새 정답 접근 없음 |
| `diagnose_asos_anchor_development.py` | 기존 지역의 실제 탐지 변화와 일별 F1의 평가 날짜 변화 분해 |
| `diagnose_blind_icing_result.py` | 완료된 새 지역 결과의 위치 거리·결측·평균 분모·미탐 진단. 새 학습·후보 선택 기능 없음 |
| `report_blind_icing.py inputs` / `results` | 기상 가용률 또는 감사 완료된 결과의 집계 그림 생성 |

위 표는 실행 순서를 설명하는 기록입니다. 완료된 출력은 덮어쓰지 않고, 이미 정답을 수집한 4곳을 새 블라인드 실험으로 다시 시작하지 않습니다. 재검토에는 봉인과 완료 영수증을 읽거나 `verify_blind_icing_completed.py`에 새 영수증 경로를 지정합니다. 원문·모델·예측은 `outputs/private/blind_icing_20261025_v2/`에만 있습니다. GitHub 복제본에는 해당 비공개 자료가 없으므로 합성 테스트와 실제 평가 재현을 구별합니다.

960날짜 수집·일회 평가·독립 감사는 완료됐으며 주 후보의 성공 조건은 미충족입니다. `resume_blind_icing_transport.py`는 분석 전에 추가한 [충돌 격리 모듈](../src/rwis_response_quality.py)을 사용합니다. 동일 지점·시각에서 값이 다르면 모두 격리하고 원문·변환본·사유를 남깁니다. 점수가 유리한 상태를 고르는 기능은 없습니다. 결과 그림의 최종 명령은 `python scripts/report_blind_icing.py results --output outputs/private/blind_icing_report_20261025_v2`였으며, 같은 출력 이름으로 다시 실행하면 보존 검사가 중단합니다.

## 10월 25일 제한 보정·새 지역 기상 입력 확보

[모델 비교와 미채택 이유](../docs/research/ANCHORED_ICING_20261025.md) · [자료 확보 수준·요청 경로](../docs/research/ICING_ACQUISITION_20261025.md). 아래 명령은 새 연구 출력만 만들며 기존 제출 v5를 교체하지 않습니다. 완료 출력 이름은 재사용할 수 없습니다.

| 스크립트 | 역할 |
| --- | --- |
| `evaluate_anchored_icing.py` | 새 ASOS 회귀 20개·기존 HGB 점수로 제한 보정 64후보와 내부 선택 3절차 비교 |
| `audit_anchored_icing.py` | 전처리·학습 분리·재추론·모든 내부 후보 지표·외부 판정·사건 독립 검산 |
| `summarize_anchored_icing.py` | 69행 후보표·서로 같은 예측·겨울별 비교 그림 생성 |
| `probe_icing_acquisition.py` | 공개 제설 연도·파일 목록과 ASOS/AWS 접근 상태 확인. 제설 파일 다운로드는 하지 않음 |
| `prepare_expanded_weather_catalog.py` | 당시 관측소 위치 API 접근 기록. 이번에는 403이어서 아래 공개 CSV 사용 |
| `download_public_station_history.py` | 로그인 없는 공식 종관 관측소 위치·변경 이력 CSV 수집 |
| `screen_expanded_icing_regions.py` | 대상 3노선·미조회·기존 지점 거리·ASOS 거리·후보 간 거리로 선별 |
| `fetch_expanded_asos_inputs.py` | 선별된 ASOS의 두 겨울 시간 입력만 수집. 노면 정답 요청 기능 없음 |
| `audit_expanded_icing_inputs.py` | 위치·선택을 별도 구면 거리 계산으로 대조하고 원문 46필드·모든 시각 검산 |

```powershell
python scripts/download_public_station_history.py --output outputs/private/public_asos_history_20261025_v1
python scripts/screen_expanded_icing_regions.py --output outputs/private/expanded_icing_regions_20261025_v2
python scripts/fetch_expanded_asos_inputs.py --screen outputs/private/expanded_icing_regions_20261025_v2 --output outputs/private/expanded_asos_inputs_20261025_v1
python scripts/audit_expanded_icing_inputs.py --screen outputs/private/expanded_icing_regions_20261025_v2 --weather outputs/private/expanded_asos_inputs_20261025_v1 --output outputs/private/expanded_icing_inputs_audit_20261025_v1
```

API 수집은 `KMA_AUTH_KEY` 환경 변수 또는 로컬 `secret.env`가 필요하며 인증값은 요청 기록·출력에 남기지 않습니다. CSV 위치 이력은 인증 없이 제공됩니다. 공개 페이지 해석에 쓰는 Beautiful Soup 4.12.3을 포함해 `python -m pip install -r requirements-research.txt`로 연구 의존성을 설치합니다. 선별 설정의 입력 경로와 원본 요청 이력도 필요하므로 원본 없는 clone에서 이 명령을 그대로 재현할 수 있는 것은 아닙니다. 코드 자체 검사는 합성 테스트로 수행합니다.

기상 파일 확보는 학습 입력 검산이나 독립 성능 평가 완료와 다릅니다. 새 지역의 결측·품질·과거 연결을 확인하고 후보·전체 예측·평가 기준을 고정하기 전 노면 정답을 열지 않습니다.

## 앞선 10월 25일 기온 기준선 차이와 추가 기상 연구

[원인·전체 결과](../docs/research/ICING_GAP_AND_SYNOPTIC_20261025.md)에서 점수 해석과 실제 비공개 경로를 확인합니다. 아래 과정은 제출 모델을 바꾸지 않는 개발 실험입니다.

| 스크립트 | 역할 |
| --- | --- |
| `diagnose_icing_baseline_gap.py` | 현재 판정과 기온 기준선의 미탐 조건·지점별 F1·날짜 분모 효과 분해 |
| `review_additional_icing_sources.py` | 제설 자료·RSCD 원 저자와 복제본의 공개 원문·접근 결과 보존 |
| `prepare_synoptic_icing.py` | 제공 ASOS의 미사용 8관측을 과거 관측 규칙으로 연결하고 별도 검산 |
| `evaluate_synoptic_icing.py` | 50개 모델·수분 이력 규칙·중첩 선택 비교. 완료 모델은 해시 확인 후 재사용 |
| `audit_synoptic_icing.py` | 50모델 재추론·학습 가중치·수분 상태·지표·선택·원인 분해를 별도로 대조 |
| `summarize_synoptic_icing.py` | 감사 영수증에 맞는 전체 후보표와 비교 그림 생성 |

학습 재개 시 저장 전후 DataFrame의 내부 index가 달라도 실제 지점·시각·순서가 일치하면 이어서 실행합니다. 키가 달라진 경우에는 중단합니다. 원본 데이터·설정·학습 코드 변경을 허용하는 기능은 아닙니다. 이미 `summary.json`이 있는 완료 폴더는 덮어쓰지 않습니다.

## 앞선 10월 25일 결빙 전이 연구

| 스크립트 | 역할 |
| --- | --- |
| `review_official_updates.py` | 공식 원문·질문·답변·빈 참가서약을 이전 보존본과 대조 |
| `evaluate_icing_transition.py` | 기상 조건부 상태 전이 모델 30개를 지역 이중 제외로 학습·비교 |
| `refine_icing_thresholds.py` | 새 학습 없이 내부 지역의 모든 서로 다른 점수에서 임계값 선택 |
| `audit_icing_transition.py` | 저장 모델·상태 재귀·지역 분리·날짜별 지표·결빙 사건·선택 결과 검산 |
| `summarize_icing_transition.py` | 검산된 44행 후보표와 F1·정밀도·재현율 그림 생성 |
| `package_icing_review_candidate.py` | v4 실행 자산을 보존하고 v5 준비·실행 검증·ZIP 검산 수행 |

계획은 [전이 학습 설정](../config/icing_transition_20261025.json)과 [임계값 설정](../config/icing_threshold_refinement_20261025.json), 결과·정확한 실행 명령은 [연구 보고서](../docs/research/ICING_TRANSITION_REVIEW_20261025.md)에서 확인합니다. 완료된 실험 출력은 덮어쓰지 않고 새 비공개 경로를 사용합니다.

## v3 이후 후속 연구

[후속 비교·구간 탐색 기록](../docs/delivery/FOLLOWUP_UPGRADE_20261024.md)에서 실제 완료 상태를 확인합니다. `evaluate_followup_temperature.py`는 고정한 시간 이력·손실·알고리즘 대조를 기존 실행기에 연결하고, `extend_followup_capacity.py`는 사전 기준을 통과한 600회 모델만 연장합니다. `evaluate_followup_offset.py`는 평가 지역을 보정에서도 제외한 6개 적합을 수행합니다. 대응하는 `audit_followup_temperature.py`·`audit_followup_offset.py`가 저장 모델·분리·출력·보정 계산을 확인합니다.

`evaluate_icing_state_memory.py`·`audit_icing_state_memory.py`는 결빙 시간 상태 정책과 별도 벡터 재계산, `audit_long_memory.py`는 긴 기상 이력의 정규 격자 재계산을 담당합니다. `compare_followup_results.py`는 완료·감사된 후보만 현재 v3와 같은 여섯 기준으로 비교합니다. 원 실행 보고서의 이전 v2 대비 통과 여부를 v3 개선으로 읽지 않습니다.

`audit_followup_failure_diagnostics.py`는 결빙의 지점·겨울 집중, 관측 온도와의 관계, 오경보 날짜의 진단표를 별도 집계합니다. 원인을 센서 오류로 확정하거나 정답을 바꾸는 도구가 아닙니다.

`build_review_dashboard.py`·`audit_review_dashboard.py`는 검증된 CSV·공간 도형으로 통신 없는 탐색 화면을 만들고 숫자·필터·다운로드·모바일 표시를 검사합니다. `package_followup_candidate.py`는 후속 비교가 기존 모델 유지로 끝난 경우에만 새 v4를 만들도록 제한합니다. 기존 v3를 덮어쓰지 않으며 `prepare`·`assets`·`verify`·`package` 순서와 완료 영수증을 따릅니다.

`record_review_dashboard.py`는 실제 Chromium 조작을 WebM으로 녹화하고 다운로드·재생·전체 프레임 디코딩을 검사합니다. 별도 Playwright와 Chromium이 필요한 검수 도구이며 제출 모델 추론에는 필요하지 않습니다. 실제 영상 프레임의 시각 검토 여부는 녹화 영수증에 기록합니다.

## 10월 24일 기상·열 이력 확장

[확장 통합 기록](../docs/delivery/EXTENDED_UPGRADE_20261024.md)을 먼저 확인합니다. `compare_extended_completion.py`는 완료 설정과 고정 평균을 모으고, `audit_advanced_models.py`·`audit_extended_classification.py`는 저장 모델과 지역 제외·임계값 선택을 검산합니다. `seal_extended_selection.py`는 감사 영수증을 연결한 선택안만 제출 준비에 넘깁니다.

`build_extended_candidate.py`가 새 폴더·포함 학습 입력·전체 공간 추론을 구성합니다. `train_extended_submission.py`·`predict_extended_submission.py`가 현재 독립 실행 코드이며 새 후보의 `code/train.py`·`code/predict.py`에 복사됩니다. `export_extended_delivery_tables.py`, `complete_extended_delivery.py`, `render_extended_review.py`, `finalize_extended_candidate.py`는 CSV·지도·실제 출력 데모·노트북·보고서와 검증 ZIP을 만듭니다. 현재 준비·완료 상태는 검증 영수증을 확인하며 기존 v2에 이 생성기를 적용하지 않습니다.

## 이전 v2: 10월 24일 두 겨울 모델 고도화

당시 진입점은 [실험·결과·실행 안내](../docs/delivery/AWARD_UPGRADE_20261024.md)입니다. `evaluate_award_ice.py`·`audit_award_ice.py`는 첫 겨울 중첩 분류 선택, `prepare_two_winter_development.py`·`evaluate_two_winter.py`·`audit_two_winter.py`는 비보호 두 겨울 비교, `upgrade_two_winter_candidate.py`는 최종 적합·전체 추론, `complete_two_winter_delivery.py`는 지도·실행 예제·노트북을 생성합니다. `render_award_review.py`는 이전 6쪽 보고서의 생성기입니다. 아래 이전 패키징 진입점은 당시 후보용이며 보존된 v2를 덮어쓰는 용도로 사용하지 않습니다.

## 10월 24일 CSV 산출·새 후보 통합

`export_delivery_tables.py`는 후보 manifest에 고정된 예측·허용 개발표만 읽고 CSV 11종과 파일별 키·자료형·결측·해시 목록을 새 폴더에 생성합니다. CSV 숫자 재독해·일별/겨울 합계·기존 24개 지표를 검산합니다. `package_delivery_tables.py`는 원 ZIP과 검증한 CSV를 새 ZIP에 통합하며 기존 모델·데이터·보고서·데모 해시를 보존합니다. [실행 명령·검증](../docs/delivery/DELIVERY_UPGRADE_20261024.md) · [CSV 규약](../docs/delivery/CSV_CONTRACT.md)

모든 명령은 저장소 루트에서 실행합니다. 단계 간 import·작업 루트 계산·봉인 기록을 보존하기 위해 기존 Python 파일 위치와 명령은 유지합니다.

[현재 현황](../docs/STATUS.md) · [실행 안내](../docs/delivery/RUNBOOK.md) · [설정 안내](../config/README.md)

## 자주 찾는 진입점

| 목적 | 파일 |
| --- | --- |
| 코드·노트북 출력·인증정보 검사 | [check_repository.py](check_repository.py) |
| GFM 렌더·링크·앵커 검사 | [check_markdown.py](check_markdown.py) |
| 현재 v3 보고서 작성 | [render_extended_review.py](render_extended_review.py) |
| 현재 v3 검산·ZIP 생성 | [finalize_extended_candidate.py](finalize_extended_candidate.py) |
| 현재 온도·별도 결빙 기준 추론 | [extended_runtime.py](../src/extended_runtime.py) |
| 제출 ZIP 해시 검증·새 폴더 복원 | [submission_archive.py](../src/submission_archive.py) |
| 현재 지도·화면·영상·노트북 생성 | [complete_extended_delivery.py](complete_extended_delivery.py) |
| 10월 19일 누수·지표·노트북 감사와 새 후보 | [review_delivery_20261019.py](review_delivery_20261019.py) |
| 새 출력 폴더에 공식 목록·본문·첨부 표시 대조 | [review_official_updates.py](review_official_updates.py) |
| 과거 Ridge·HGB 기준선 데모 | [demo_inference.py](demo_inference.py) |
| 데이터 버전별 작업 복사본 | [prepare_release_workspace.py](prepare_release_workspace.py) |

학습·공식 사이트 수집·패키징은 출력 경로와 선행 조건을 확인한 뒤 실행합니다. 현재 후보 묶음과 이미 완료한 평가를 덮어쓰지 않습니다. 수정본 연구는 별도 작업 루트의 실행 안내를 따릅니다.

10월 19일 후보는 [제출용 노트북](../notebooks/submission_review.ipynb)을 압축 해제 폴더에서 실행합니다. 원 연구 공간이 필요한 기존 `analysis_review.ipynb`와 구별합니다. [단계별 실행·검증 결과](../docs/delivery/DELIVERY_REVIEW_20261019.md)

다음은 10월 16일 이전 후보의 실행 예입니다. 현재 v3는 압축 해제 폴더의 README와 `code/predict.py`를 따릅니다. 원본 저장소에는 모델이 포함되지 않습니다.

```powershell
python -m src.submission_archive --archive outputs/private/submission_candidate_20261016_v1.zip --output outputs/private/candidate_work_20261016
python -m src.submission_runtime --input outputs/private/candidate_work_20261016/data/weather_example.csv --models outputs/private/candidate_work_20261016/model --output outputs/private/new_candidate_prediction.csv
```

복원 경로·예측 경로가 이미 존재하면 중단합니다. 예제는 현재 학습 모델의 실행 확인용이며 새 지점 성능 평가가 아닙니다. [기준선·재현성 후속 검토](../docs/delivery/REVIEW_RESPONSE_20261016.md)

## 10월 16일 추가 연구

현재 실행 모델은 유지합니다. 다음 실험은 기존 개발 자료·공간 제외 저장 모델·감사 자료가 필요하며, 완료 폴더나 감사 영수증이 있으면 덮어쓰지 않고 중단합니다. 공개 코드만으로 연구 전체를 재현할 수 있다는 뜻이 아닙니다. [결과·선행연구·한계](../docs/research/AIR_ROAD_AND_INPUT_GAPS_20261016.md)

| 목적 | 실행 파일 |
| --- | --- |
| 같은 날 공식 원문·양식 재대조 | [review_official_followup_20261016.py](review_official_followup_20261016.py) |
| 72개 기온·노면 규칙과 두 내부 선택 경로 | [evaluate_air_road_blending.py](evaluate_air_road_blending.py) |
| 시간창·지표·사건·20모델 재추론 독립 검산 | [audit_air_road_blending.py](audit_air_road_blending.py) |
| ASOS 대체·개발 648개 합성 공백 | [evaluate_asos_gap_fallback.py](evaluate_asos_gap_fallback.py) |
| ASOS 행별 선택·온도·참고 출력 검산 | [audit_asos_gap_fallback.py](audit_asos_gap_fallback.py) |
| 원 ASOS 공백 1회 조회 | [probe_asos_gap_source.py](probe_asos_gap_source.py) |
| 정상 ASOS 대조군·첫 겨울 직전 원 관측 3회 조회 | [collect_asos_gap_controls.py](collect_asos_gap_controls.py) |
| 둘째 겨울 직전·장수 공백·AWS 접근 3회 조회 | [collect_weather_gap_followup.py](collect_weather_gap_followup.py) |
| 원 기상과 캐시·결측·최초 입력 대조 | [audit_weather_source_gaps.py](audit_weather_source_gaps.py) |
| 기존 위치 표와 현재 요청 이력만으로 미사용 지점 점검 | [audit_remaining_station_metadata.py](audit_remaining_station_metadata.py) |
| 후속 연구 4쪽 PDF 작성·렌더링 | [build_air_road_gap_report.py](build_air_road_gap_report.py) |
| 새 실험·문서·PDF·보존 해시 종합 검사 | [check_air_road_followup_quality.py](check_air_road_followup_quality.py) |

인증 조회 세 파일은 기존 `KMA_AUTH_KEY` 환경값 또는 로컬 `secret.env`가 필요합니다. 키·키 포함 URL을 출력하거나 저장하지 않습니다. API 요청량은 합계 7회이며 공식 원 기상만 읽습니다. 보호·이미 개봉한 도로 정답이나 외부 예측 서비스는 요청하지 않습니다. AWS 응답은 403이었으며 이를 접근 성공으로 표시하지 않습니다.

기존 결과가 없는 별도 작업 공간에서 실행할 때는 `python scripts/파일명.py`를 사용합니다. 실험 다음 해당 감사를 실행합니다. 원 기상 감사는 세 수집 파일이 모두 완료돼야 합니다. 보고서 작성은 모든 감사가 통과한 뒤 수행합니다. 현재 보존된 결과를 다시 생성하려고 삭제하지 않습니다.

## 전체 스크립트 목록

파일명의 기능을 기준으로 찾기 쉽게 묶었습니다. 현재 후보에서 직접 쓰는 파일과 과거 실험 파일을 모두 포함합니다.

<details>
<summary>검증 · 13개</summary>

- [check_blending_quality.py](check_blending_quality.py)
- [check_ice_methodology_quality.py](check_ice_methodology_quality.py)
- [check_markdown.py](check_markdown.py)
- [check_model_report_quality.py](check_model_report_quality.py)
- [check_notebook.py](check_notebook.py)
- [check_official_updates_20261013.py](check_official_updates_20261013.py)
- [check_qa633_quality.py](check_qa633_quality.py)
- [check_repository.py](check_repository.py)
- [check_submission_candidate_quality.py](check_submission_candidate_quality.py)
- [check_weather_memory_control_quality.py](check_weather_memory_control_quality.py)
- [check_weather_memory_quality.py](check_weather_memory_quality.py)
- [verify_offline_inference_20261013.py](verify_offline_inference_20261013.py)
- [verify_submission_candidate_demo.py](verify_submission_candidate_demo.py)

</details>

<details>
<summary>제출 · 22개</summary>

- [analyze_submission_failure_modes.py](analyze_submission_failure_modes.py)
- [audit_submission_candidate.py](audit_submission_candidate.py)
- [audit_submission_diagnostics.py](audit_submission_diagnostics.py)
- [build_demo_video.py](build_demo_video.py)
- [build_research_delivery.py](build_research_delivery.py)
- [build_revised_submission_report.py](build_revised_submission_report.py)
- [build_submission_candidate_demo.py](build_submission_candidate_demo.py)
- [build_submission_draft.py](build_submission_draft.py)
- [complete_submission_candidate_materials.py](complete_submission_candidate_materials.py)
- [demo_inference.py](demo_inference.py)
- [finalize_submission_candidate.py](finalize_submission_candidate.py)
- [fix_submission_candidate_csv_io.py](fix_submission_candidate_csv_io.py)
- [infer_submission_candidate_spatial.py](infer_submission_candidate_spatial.py)
- [package_current_candidate_review_20261014.py](package_current_candidate_review_20261014.py)
- [package_model_report_upgrade.py](package_model_report_upgrade.py)
- [prepare_submission_candidate.py](prepare_submission_candidate.py)
- [record_submission_candidate_demo.py](record_submission_candidate_demo.py)
- [render_submission_candidate_report.py](render_submission_candidate_report.py)
- [repair_submission_candidate_delivery.py](repair_submission_candidate_delivery.py)
- [reproduce_freezing_delivery.py](reproduce_freezing_delivery.py)
- [reproduce_research_delivery.py](reproduce_research_delivery.py)
- [research_report_upgrade_20261014.py](research_report_upgrade_20261014.py)

</details>

<details>
<summary>공식정보 · 18개</summary>

- [audit_official_chainage_anchors.py](audit_official_chainage_anchors.py)
- [audit_official_nodelink_geometry.py](audit_official_nodelink_geometry.py)
- [audit_qa633_development.py](audit_qa633_development.py)
- [build_official_directed_segment_candidates.py](build_official_directed_segment_candidates.py)
- [build_official_requirements_20261013.py](build_official_requirements_20261013.py)
- [compare_official_answers_20261013.py](compare_official_answers_20261013.py)
- [complete_official_qna_review.py](complete_official_qna_review.py)
- [complete_official_requirements_20261014.py](complete_official_requirements_20261014.py)
- [evaluate_qa633_development.py](evaluate_qa633_development.py)
- [fetch_official_details_20261013.py](fetch_official_details_20261013.py)
- [inspect_official_changes_20261014.py](inspect_official_changes_20261014.py)
- [inspect_official_updates_20261013.py](inspect_official_updates_20261013.py)
- [inspect_qa633_followup_inputs.py](inspect_qa633_followup_inputs.py)
- [inspect_qa633_results.py](inspect_qa633_results.py)
- [plot_qa633_review.py](plot_qa633_review.py)
- [review_official_answers_20261013.py](review_official_answers_20261013.py)
- [review_official_updates_20261013.py](review_official_updates_20261013.py)
- [review_official_updates_20261014.py](review_official_updates_20261014.py)

</details>

<details>
<summary>데이터준비 · 29개</summary>

- [build_aws_fallback_features.py](build_aws_fallback_features.py)
- [build_environment_features.py](build_environment_features.py)
- [build_fog_features.py](build_fog_features.py)
- [build_ice_features.py](build_ice_features.py)
- [build_kma_external_development_features.py](build_kma_external_development_features.py)
- [build_moisture_memory.py](build_moisture_memory.py)
- [build_offline_review_bundle_20261013.py](build_offline_review_bundle_20261013.py)
- [build_physical_features.py](build_physical_features.py)
- [build_road_segment_scaffold.py](build_road_segment_scaffold.py)
- [build_route_facility_features.py](build_route_facility_features.py)
- [build_segment_environment_inventory.py](build_segment_environment_inventory.py)
- [build_segment_exposure.py](build_segment_exposure.py)
- [build_solar_terrain_features.py](build_solar_terrain_features.py)
- [build_static_station_features.py](build_static_station_features.py)
- [build_weather_control_bundle.py](build_weather_control_bundle.py)
- [build_weather_features.py](build_weather_features.py)
- [build_weather_memory_bundle.py](build_weather_memory_bundle.py)
- [build_weather_memory_stable_bundle.py](build_weather_memory_stable_bundle.py)
- [cache_point_sources.py](cache_point_sources.py)
- [download_kma_external_development.py](download_kma_external_development.py)
- [download_kma_external_reserved.py](download_kma_external_reserved.py)
- [fetch_copernicus_dem.py](fetch_copernicus_dem.py)
- [fetch_ice_practice_references.py](fetch_ice_practice_references.py)
- [fetch_power_radiation.py](fetch_power_radiation.py)
- [fetch_spatial_blending_reference.py](fetch_spatial_blending_reference.py)
- [make_splits.py](make_splits.py)
- [make_variable_dictionary.py](make_variable_dictionary.py)
- [precompute_external_development_inputs.py](precompute_external_development_inputs.py)
- [prepare_release_workspace.py](prepare_release_workspace.py)

</details>

<details>
<summary>학습평가 · 51개</summary>

- [baseline_asos.py](baseline_asos.py)
- [baseline_ice_logistic.py](baseline_ice_logistic.py)
- [baseline_ice_nonlinear.py](baseline_ice_nonlinear.py)
- [baseline_neighbor_rwis.py](baseline_neighbor_rwis.py)
- [baseline_weather_ridge.py](baseline_weather_ridge.py)
- [evaluate_antecedent_forward.py](evaluate_antecedent_forward.py)
- [evaluate_catboost_forward.py](evaluate_catboost_forward.py)
- [evaluate_daily_rank_policy.py](evaluate_daily_rank_policy.py)
- [evaluate_daily_threshold_transfer.py](evaluate_daily_threshold_transfer.py)
- [evaluate_development_thermal_ice.py](evaluate_development_thermal_ice.py)
- [evaluate_dsm_consistent.py](evaluate_dsm_consistent.py)
- [evaluate_estimated_temperature_forward.py](evaluate_estimated_temperature_forward.py)
- [evaluate_external_augmentation.py](evaluate_external_augmentation.py)
- [evaluate_external_reserved.py](evaluate_external_reserved.py)
- [evaluate_external_temperature.py](evaluate_external_temperature.py)
- [evaluate_forward_physics.py](evaluate_forward_physics.py)
- [evaluate_freezing_weight.py](evaluate_freezing_weight.py)
- [evaluate_frozen_holdout.py](evaluate_frozen_holdout.py)
- [evaluate_height_transfer.py](evaluate_height_transfer.py)
- [evaluate_ice_methodology.py](evaluate_ice_methodology.py)
- [evaluate_joint_surface.py](evaluate_joint_surface.py)
- [evaluate_memory_forward.py](evaluate_memory_forward.py)
- [evaluate_method_blending.py](evaluate_method_blending.py)
- [evaluate_neighbor_transfer.py](evaluate_neighbor_transfer.py)
- [evaluate_physical_ice.py](evaluate_physical_ice.py)
- [evaluate_regularized_forward.py](evaluate_regularized_forward.py)
- [evaluate_score_blending.py](evaluate_score_blending.py)
- [evaluate_score_calibration.py](evaluate_score_calibration.py)
- [evaluate_surface_state_ensemble.py](evaluate_surface_state_ensemble.py)
- [evaluate_surface_state_forward.py](evaluate_surface_state_forward.py)
- [evaluate_surface_state_v2_ensemble.py](evaluate_surface_state_v2_ensemble.py)
- [evaluate_surface_state_v2_forward.py](evaluate_surface_state_v2_forward.py)
- [evaluate_temperature_mean.py](evaluate_temperature_mean.py)
- [evaluate_temperature_pairs.py](evaluate_temperature_pairs.py)
- [evaluate_temperature_physics.py](evaluate_temperature_physics.py)
- [evaluate_temperature_transfer.py](evaluate_temperature_transfer.py)
- [evaluate_temperature_uncertainty.py](evaluate_temperature_uncertainty.py)
- [evaluate_thermal_consensus.py](evaluate_thermal_consensus.py)
- [evaluate_weather_distance.py](evaluate_weather_distance.py)
- [evaluate_weather_memory_controls.py](evaluate_weather_memory_controls.py)
- [evaluate_weather_memory_temperature.py](evaluate_weather_memory_temperature.py)
- [evaluate_weather_memory_temperature_stable.py](evaluate_weather_memory_temperature_stable.py)
- [evaluate_weather_temporal.py](evaluate_weather_temporal.py)
- [predict_external_reserved.py](predict_external_reserved.py)
- [predict_frozen_holdout.py](predict_frozen_holdout.py)
- [research_ice_methodology.py](research_ice_methodology.py)
- [research_method_blending.py](research_method_blending.py)
- [research_temperature_uncertainty.py](research_temperature_uncertainty.py)
- [research_weather_memory_20261013.py](research_weather_memory_20261013.py)
- [train_ice_candidate.py](train_ice_candidate.py)
- [train_temperature_candidate.py](train_temperature_candidate.py)

</details>

<details>
<summary>분석감사 · 90개</summary>

- [analyze_external_rwis_quality.py](analyze_external_rwis_quality.py)
- [audit_aws_boundaries.py](audit_aws_boundaries.py)
- [audit_aws_cleaning.py](audit_aws_cleaning.py)
- [audit_aws_fallback.py](audit_aws_fallback.py)
- [audit_candidate_prediction_coverage.py](audit_candidate_prediction_coverage.py)
- [audit_chainage_reference.py](audit_chainage_reference.py)
- [audit_completion.py](audit_completion.py)
- [audit_daily_threshold_transfer.py](audit_daily_threshold_transfer.py)
- [audit_data.py](audit_data.py)
- [audit_dem_units.py](audit_dem_units.py)
- [audit_estimated_temperature_forward.py](audit_estimated_temperature_forward.py)
- [audit_freezing_weight.py](audit_freezing_weight.py)
- [audit_fresh_station_validation.py](audit_fresh_station_validation.py)
- [audit_fresh_uncertainty.py](audit_fresh_uncertainty.py)
- [audit_ice_events.py](audit_ice_events.py)
- [audit_ice_methodology.py](audit_ice_methodology.py)
- [audit_ice_weather_history.py](audit_ice_weather_history.py)
- [audit_joint_surface.py](audit_joint_surface.py)
- [audit_kma_external_development.py](audit_kma_external_development.py)
- [audit_kma_rwis_catalog.py](audit_kma_rwis_catalog.py)
- [audit_method_blending.py](audit_method_blending.py)
- [audit_point_input_parity.py](audit_point_input_parity.py)
- [audit_regularized_forward.py](audit_regularized_forward.py)
- [audit_rwis_context.py](audit_rwis_context.py)
- [audit_score_blending.py](audit_score_blending.py)
- [audit_score_calibration.py](audit_score_calibration.py)
- [audit_segment_exposure.py](audit_segment_exposure.py)
- [audit_segment_inference.py](audit_segment_inference.py)
- [audit_sensor_availability.py](audit_sensor_availability.py)
- [audit_spatial.py](audit_spatial.py)
- [audit_station_road_alignment.py](audit_station_road_alignment.py)
- [audit_surface_state_ensemble.py](audit_surface_state_ensemble.py)
- [audit_surface_state_forward.py](audit_surface_state_forward.py)
- [audit_surface_state_v2_ensemble.py](audit_surface_state_v2_ensemble.py)
- [audit_surface_state_v2_forward.py](audit_surface_state_v2_forward.py)
- [audit_temperature_blind_validation.py](audit_temperature_blind_validation.py)
- [audit_temperature_mean.py](audit_temperature_mean.py)
- [audit_temperature_mean_blind.py](audit_temperature_mean_blind.py)
- [audit_temperature_pairs.py](audit_temperature_pairs.py)
- [audit_temperature_transfer.py](audit_temperature_transfer.py)
- [audit_temperature_uncertainty.py](audit_temperature_uncertainty.py)
- [audit_thermal_consensus.py](audit_thermal_consensus.py)
- [audit_timestamps.py](audit_timestamps.py)
- [audit_unresolved_evidence.py](audit_unresolved_evidence.py)
- [audit_weather_distance.py](audit_weather_distance.py)
- [audit_weather_memory_controls.py](audit_weather_memory_controls.py)
- [audit_weather_memory_temperature.py](audit_weather_memory_temperature.py)
- [audit_weather_memory_temperature_stable.py](audit_weather_memory_temperature_stable.py)
- [audit_weather_network_expansion.py](audit_weather_network_expansion.py)
- [compare_data_releases.py](compare_data_releases.py)
- [compare_facility_weather.py](compare_facility_weather.py)
- [compare_fog_ablation.py](compare_fog_ablation.py)
- [compare_ice_history.py](compare_ice_history.py)
- [compare_ice_nonlinear.py](compare_ice_nonlinear.py)
- [compare_ice_variants.py](compare_ice_variants.py)
- [compare_physical_ice.py](compare_physical_ice.py)
- [compare_weather_variants.py](compare_weather_variants.py)
- [diagnose_ice_baseline.py](diagnose_ice_baseline.py)
- [diagnose_ice_context.py](diagnose_ice_context.py)
- [diagnose_joint_surface.py](diagnose_joint_surface.py)
- [diagnose_neighbor_rwis.py](diagnose_neighbor_rwis.py)
- [diagnose_state_temperature.py](diagnose_state_temperature.py)
- [diagnose_weather_ridge.py](diagnose_weather_ridge.py)
- [inspect_blending_evidence.py](inspect_blending_evidence.py)
- [inspect_ice_methodology_evidence.py](inspect_ice_methodology_evidence.py)
- [inspect_ice_methodology_results.py](inspect_ice_methodology_results.py)
- [inspect_weather_memory_controls.py](inspect_weather_memory_controls.py)
- [inspect_weather_memory_inputs.py](inspect_weather_memory_inputs.py)
- [inspect_weather_memory_results.py](inspect_weather_memory_results.py)
- [plot_chainage_review.py](plot_chainage_review.py)
- [plot_fresh_validation.py](plot_fresh_validation.py)
- [plot_ice_methodology.py](plot_ice_methodology.py)
- [plot_joint_surface.py](plot_joint_surface.py)
- [plot_method_blending.py](plot_method_blending.py)
- [plot_physical_comparison.py](plot_physical_comparison.py)
- [plot_temperature_mean_review.py](plot_temperature_mean_review.py)
- [plot_temperature_transfer_review.py](plot_temperature_transfer_review.py)
- [plot_temperature_uncertainty.py](plot_temperature_uncertainty.py)
- [plot_terrain_evidence.py](plot_terrain_evidence.py)
- [plot_unresolved_evidence.py](plot_unresolved_evidence.py)
- [plot_weather_distance_review.py](plot_weather_distance_review.py)
- [plot_weather_memory_controls.py](plot_weather_memory_controls.py)
- [plot_weather_memory_temperature.py](plot_weather_memory_temperature.py)
- [plot_weather_memory_temperature_stable.py](plot_weather_memory_temperature_stable.py)
- [render_segment_review.py](render_segment_review.py)
- [review_temperature_mean_failure.py](review_temperature_mean_failure.py)
- [review_unresolved_evidence.py](review_unresolved_evidence.py)
- [review_weather_memory_events.py](review_weather_memory_events.py)
- [review_weather_memory_tradeoffs.py](review_weather_memory_tradeoffs.py)
- [summarize_fresh_uncertainty.py](summarize_fresh_uncertainty.py)

</details>

<details>
<summary>기타 · 13개</summary>

- [complete_report_reference_review.py](complete_report_reference_review.py)
- [eda_development.py](eda_development.py)
- [export_segment_condition_maps.py](export_segment_condition_maps.py)
- [freeze_assessment.py](freeze_assessment.py)
- [fresh_station_validation.py](fresh_station_validation.py)
- [infer_segment_ice_exploratory.py](infer_segment_ice_exploratory.py)
- [infer_segment_temperature.py](infer_segment_temperature.py)
- [plan_weather_network_expansion.py](plan_weather_network_expansion.py)
- [refresh_manifests.py](refresh_manifests.py)
- [reproduce_weather_fallback.py](reproduce_weather_fallback.py)
- [resume_fresh_collection.py](resume_fresh_collection.py)
- [temperature_blind_validation.py](temperature_blind_validation.py)
- [temperature_mean_blind_validation.py](temperature_mean_blind_validation.py)

</details>
