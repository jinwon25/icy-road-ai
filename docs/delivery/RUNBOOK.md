# 단계별 실행 안내

코드·문서 검증은 원본 없이 실행할 수 있습니다. 전체 분석은 참가 권한과 로컬 원본·중간 산출물이 필요하며, 이미 완료한 보호·다음 겨울 일회 평가와 기존 결과 폴더를 보존합니다.

[문서 목록](../README.md) · [현재 상태](../history/PROJECT_STATUS.md) · [공식 재검토](../competition/OFFICIAL_REVIEW_20261009.md)

## 제출 후보의 실제 실행

10월 16일 현재 후보는 `outputs/private/submission_candidate_20261016_v1.zip`입니다. [현재 후보 복원·저장소 추론·기준선 재현](REVIEW_RESPONSE_20261016.md#실행과-다음-판단)의 명령을 먼저 사용합니다. 삭제된 임시 해제 폴더를 입력으로 요구하지 않습니다. 아래 10월 13일 경로는 당시 패키지와 실험을 재현하는 기록입니다.

[통합 결과](SUBMISSION_CANDIDATE_20261013.md)의 비공개 후보는 `outputs/private/submission_candidate_20261013_v1/`입니다. 그 폴더의 README와 한국어 PDF에서 고정 환경·입력 계약·추론·재적합·위치별 CSV 내보내기 명령을 확인합니다. `code/predict.py`는 무손실 CSV 읽기를 사용하며 원래 기본 파서의 실패 결과를 보존합니다.

포함된 대표 모델과 학습 표의 재현, 공통 기상 그룹 추론, 개발 지표 재집계는 로컬 자료로 실행합니다. 원본 GIS·기상 원자료의 전체 재구축은 원본 작업 공간 의존입니다. 완료 폴더·봉인·예측을 다시 만들지 않고 새 출력 경로를 사용합니다. 원본 프로젝트의 보고서·지도·브라우저 데모 생성에는 `requirements-delivery.txt`의 추가 환경이 필요하며 추론만 실행할 때는 후보 폴더의 간단한 `requirements.txt`를 사용합니다.

## 새 Q&A633와 기존 판정 재집계

[최신 답변 검토](../competition/OFFICIAL_QNA_20261013.md)의 원문은 `outputs/private/official_updates_20261013_v2/`, 사실/미정 항목은 `config/official_requirements_20261013_v2.json`입니다. `review_official_answers_20261013.py`·`complete_official_qna_review.py`는 새 공개 스냅샷을 만들고 이전 완료본을 보존합니다. 기존 출력이 있으면 재실행하지 않습니다.

`evaluate_qa633_development.py`는 최신 온도/결빙 방법의 감사된 개발 예측3파일에서21개 고정 판정을 읽습니다. `audit_qa633_development.py`는 같은 학습 데이터를 다시 만드는 대신 저장 판정·일별 혼동행렬·지점 평균·CSV를 독립 계산으로 검산합니다. 새 모델 학습·임계값 선택은 없고 이미 개봉한 평가/다음 겨울/보호 정답도 사용하지 않습니다.

완료본 `qa633_development_20261013_v1/`의 `research_daily_metrics.csv`·`research_station_metrics.csv`는 지표별 날짜 수·관측량4조건·미정의 지점을 포함한 연구용 형식입니다. 주최 측이 정한 제출CSV 열·결측 표기가 아닙니다. `check_qa633_quality.py`는 공개 원문·새 설정·지표 감사·옛 모델/예측·봉인·전체 검사·로컬 GFM의 완료 영수증을 남깁니다.

## 기상 이력 온도 후속 연구 재현

최종 추가 비교는 `evaluate_weather_memory_controls.py`·`audit_weather_memory_controls.py`·`review_weather_memory_tradeoffs.py`입니다. 기상12·300회·MSE/MAE·학습 행을 유지하고 이력30개만 제거하며, 이전 온도·결빙 기준과 사건 유지 조건을 바꾸지 않습니다. 완료본 `weather_memory_controls_20261013_v1/`의 모델20개·예측·감사를 보존합니다.

`build_weather_control_bundle.py`의 고정2모델 평균 예제는 다음으로 재실행합니다. 이 하루에 입력 누락이 없음을 검사하며 일반 결측 환경의fallback 모델을 모두 포함한 운영 패키지는 아닙니다.

```powershell
.\.venv_research\Scripts\python.exe -X utf8 outputs/private/weather_control_offline_bundle_20261013_v1/run_offline.py
```

최종 품질 영수증은 `weather_memory_quality_20261013_v2/`이며 먼저 완료한 이력 연구의v1 영수증은 당시 스냅샷으로 보존합니다.

[새 보고서](../research/WEATHER_MEMORY_REVIEW_20261013.md)의 현재 완료본은 `outputs/private/weather_memory_temperature_20261013_v2/`입니다. 기존 `weather_distance`의23개 첫 겨울 입력과 감사된 `temperature_pair_blending`의 G/H 제외 예측이 필요합니다. 보호·개봉 평가·다음 겨울을 새로 읽거나 원래 완료 폴더를 덮어쓰는 흐름이 아닙니다.

`research_weather_memory_20261013.py`는 일차 문헌과 공식 공개 응답을 보존합니다. `evaluate_weather_memory_temperature_stable.py`는 고정소수점 이력과20모델을 학습하고, `audit_weather_memory_temperature_stable.py`는 정수 합성곱·모델 재예측·대표 재적합·같은 분모 지표를 확인합니다. `review_weather_memory_events.py`는347사건의 정체성과 기존 탐지 사건 손실을 대조합니다. 이전 부동소수점v1과 실패 묶음은 별도 보존합니다.

`build_weather_memory_stable_bundle.py`의 완료 묶음은5모델·216기상행·특징/예측 대조값만 담습니다. 고정 의존성을 설치한 환경에서 다음 읽기 실행이 가능합니다.

```powershell
.\.venv_research\Scripts\python.exe -X utf8 outputs/private/weather_memory_offline_bundle_20261013_v2/run_offline.py
```

144행 추론에 앞선12시간72행을 준비 입력으로 사용하며 실제 정답·키·원본ZIP은 포함하지 않습니다. 접속 시도0·특징6,048값 정확히 일치·예측/경계1,296값 허용오차1e-10 이내를 확인합니다. `check_weather_memory_quality.py`는 v1/v2·실패 로그·사건 검토·묶음·봉인·전체 검사·로컬 GFM의 새 완료 영수증을 남깁니다. 완료 영수증은 재실행으로 덮어쓰지 않습니다.

## 10월13일 공식 확인·오프라인 재현

[공식 변경 보고서](../competition/OFFICIAL_UPDATE_20261013.md)의 원문은 `outputs/private/official_updates_20261013_v1/`, 확인한 사실·미정 날짜는 `config/official_requirements_20261013.json`입니다. 익명 조회·이미지/HWP 추출·답변 대조는 `review_official_updates_20261013.py`·`fetch_official_details_20261013.py`·`inspect_official_updates_20261013.py`·`compare_official_answers_20261013.py`가 담당합니다. 기존 영수증이 있으면 재실행을 거부하며 새 날짜는 새 출력 버전으로 설정해야 합니다. HWP 읽기는 기존 비공개 도구 `outputs/private/official_review_20261007/tools/olefile`0.47을 사용하고 라이선스를 유지합니다.

`verify_offline_inference_20261013.py`는 감사된 온도3성분·미채택 CatBoost·경험적 범위와12207의 하루 캐시를 읽어 외부 접속 차단 상태로1,008개 예측을 대조합니다. `build_offline_review_bundle_20261013.py`는 모델4개·입력/대조자료3개·실행 코드2개·환경·README의11파일을 별도 묶음으로 준비하고 별도 Python에서576개 최종 출력 일치를 확인합니다. 완료본을 다시 만들거나 모델을 새 학습하는 명령이 아닙니다.

현재 설치된 Python 환경에서 완료 묶음을 읽어 재실행할 수 있습니다.

```powershell
.\.venv_research\Scripts\python.exe -X utf8 outputs/private/offline_review_bundle_20261013_v1/run_offline.py
```

묶음의 고정 환경 목록을 먼저 설치해야 하며 설치와 추론 실행은 구별합니다. 추론에는 인증키·외부 예측 서비스·새 관측 다운로드가 필요하지 않습니다. 네트워크 가드는 Python DNS·주요 소켓 인터페이스의 시도를 기록·차단하며 OS 전체 격리 보장은 아닙니다. 미채택 후보와 하루 개발 예제이므로 실제 운영·최종 제출·독립 성능의 검증과 구별합니다.

`check_official_updates_20261013.py`는 원문·양식·확정 사실·추론·묶음의 해시, 데이터 열의 목표 정답 미포함, 기존 봉인·전체 테스트·소스·로컬 GFM을 검증해 새 품질 영수증을 남깁니다. 문의·로그인·참가신청·결과물 제출·공개는 이 흐름에 포함하지 않습니다.

## 결빙 방법론 여섯 가지 재현

[비교 보고서](../research/ICE_METHODOLOGY_REVIEW_20261010.md)의 완료본은 `outputs/private/ice_methodology_20261010_v1/`입니다. 기존 첫 겨울23곳의 `ice_group_balanced` 개발 입력·독립 감사된 `joint_surface_20261009_v1`의 온도 교차 추정·보조 모델·학습/쿼리 행이 필요합니다. 데이터 없는 clone에서는 전체 학습을 실행할 수 없습니다.

```powershell
python scripts/evaluate_ice_methodology.py --output outputs/private/reproduction_ice_methodology_새버전
python scripts/audit_ice_methodology.py --experiment outputs/private/reproduction_ice_methodology_새버전
```

`config/ice_methodology_experiment.json`의 고정6후보는10개 공간 제외 맥락에서 새 분류70모델을 적합합니다. 기존 HGB100을 대조로 재사용하며 새 온도 적합은 없습니다. `src/ice_methodology.py`의 과거 평균은 목표 실제 관측 없이 계산하고 미정의 상태 행의 기상도 포함합니다. 감사는 누적합·시간 경계로 이력을 별도 계산하고 전체 모델의 예측·대표7모델 재적합·11,284개 임계값·4개 선택과10개 정책의 지표를 확인합니다.

`research_ice_methodology.py`·`inspect_ice_methodology_evidence.py`·`fetch_ice_practice_references.py`는 원문·접근 실패·공식 본문의 날짜별 보존 도구이며 기존 영수증이 있으면 중단합니다. 새 날짜의 재조회는 새 출력 버전으로 별도 설정합니다. `inspect_ice_methodology_results.py`는 선택 완료 후에만 진단 CSV를 추가합니다. `plot_ice_methodology.py`는 독립 감사 영수증을 확인한 뒤 집계 그림을 생성하며 기존 그림을 덮어쓰지 않습니다.

`check_ice_methodology_quality.py`는 최종 문서·그림 확인 후 전체 테스트, 추적·새 파일, 로컬 GFM, 실험 서명과 기존47/549고정 파일·세 평가 봉인을 검증해 별도 품질 영수증을 남깁니다. 기존 평가 지점을 새 후보로 다시 채점하는 명령은 이 흐름에 포함하지 않습니다.

추가 온도 범위는 `temperature_pair_blending_20261010_v1`의 감사된 내부/외부 예측을 사용합니다. `evaluate_temperature_uncertainty.py`의 고정 두 후보·경험적90분위수는 새 모델 적합 없이 평가 그룹 밖의 지점 균등 오차로 계산합니다. `audit_temperature_uncertainty.py`가8개 분위수와621,028개 하한/상한·전체/지점/저온/경계 지표를 별도 검산합니다. 완료 폴더는 `outputs/private/temperature_uncertainty_20261010_v1/`이며 이 날짜의 보존 명령을 다시 실행하면 중단합니다. 재실험은 새 출력 버전을 지정하도록 설정해야 합니다. 90% 보장·04 확률로 해석하지 않습니다.

`research_temperature_uncertainty.py`는 관련51쪽 원문과 대표 페이지를 보존합니다. `plot_temperature_uncertainty.py`의 수정본은 기존 범례 겹침 초안을 비공개로 보존한 뒤 확인했습니다. 최종 품질 검사는 분류와 온도 범위의 두 감사 영수증·원문 해시를 함께 확인합니다.

## 방법론 블렌딩 재현

[최신 검토](../research/METHOD_BLENDING_REVIEW_20261010.md)의 완료본은 온도·분류 각각 `outputs/private/method_blending_20261010_v2/`·`score_blending_20261010_v2/`입니다. 기존 첫 겨울23개 개발 지점의 비공개 입력·감사된 모델90개·분류20개와 보조 온도 산출물이 필요합니다. 공개 clone의 데이터 없는 실행과 구별합니다. 완료·실패 폴더는 덮어쓰지 않습니다.

```powershell
python scripts/evaluate_method_blending.py --output outputs/private/reproduction_method_blending_새버전
python scripts/audit_method_blending.py --experiment outputs/private/reproduction_method_blending_새버전
python scripts/evaluate_score_blending.py --output outputs/private/reproduction_score_blending_새버전
python scripts/audit_joint_surface.py --experiment outputs/private/joint_surface_20261009_v1 --output outputs/private/reproduction_score_blending_새버전/component_reaudit.json
python scripts/audit_score_blending.py --experiment outputs/private/reproduction_score_blending_새버전
python scripts/evaluate_temperature_pairs.py --output outputs/private/reproduction_temperature_pairs_새버전
python scripts/audit_temperature_pairs.py --experiment outputs/private/reproduction_temperature_pairs_새버전
```

설정은 `config/method_blending_experiment.json`입니다. 온도는3그룹 제외36개 기본 적합·32개 메타 적합을 만들고 기존1/2그룹 제외 예측을 재사용합니다. 감사는126개 저장 모델의 재예측과 대표9종 재적합,511개 활성 집합으로 가중치 최적값을 검산합니다. 분류는 새 적합 없이4개 점수 평균·2개 논리 판정, 내부403개 임계값을 비교합니다. 기존 평가·보호·다음 겨울 정답을 사용하지 않고 새 정답 API 요청도 없습니다.

`research_method_blending.py`·`inspect_blending_evidence.py`·`fetch_spatial_blending_reference.py`는 이번 날짜의 출처·실패 기록 보존용이며 기존 결과 파일이 있으면 중단합니다. 재조회는 새 버전을 지정하도록 별도 설정이 필요합니다. 이번 원문과 공식 숨김 본문은 기존 출력 폴더에서 읽을 수 있습니다. `plot_method_blending.py`는 세 실험의 독립 검산 영수증을 확인하고 집계 그림을 생성하며 기존 그림은 덮어쓰지 않습니다.

고정 쌍·삼중 결합은 `temperature_pair_blending_experiment.json`과 감사된 `method_blending_20261010_v2`의 예측을 사용합니다. 주 대조군은300회 단독이며 기존100회 대조를 보조로 유지합니다. 새 학습 없이3종 평균과 내부 선택을 검산합니다. `plot_method_blending.py`는 이 세 번째 영수증까지 확인합니다. `check_blending_quality.py`는 세 완료본의 서명·봉인과 전체 테스트·새 파일·GFM을 검사하고 신규 품질 폴더에 Python 종료 코드·환경 버전·파일 해시를 남깁니다.

## 데이터 없는 검증 실행

프로젝트 루트에서 실행합니다.

```powershell
python -m pip install -r requirements-dev.txt
$env:OMP_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
python -m unittest discover -s tests -v
python scripts/check_repository.py
python scripts/check_markdown.py
```

단위 테스트는 합성 데이터로 수행합니다. 노트북 실행과 전체 모델 성능 재현은 비공개 산출물이 필요하므로 데이터 없는 검증 명령에 포함하지 않습니다. GFM은 로컬에서 렌더하며 문서를 외부 렌더 서비스에 전송하지 않습니다.

## 최신 고정 평균·새 호남 평가 — 2026-10-10

[후속 보고서](../research/TEMPERATURE_MEAN_AND_BLIND_REVIEW_20261010.md)의 개발 비교는 기존 감사된 기상14/12 예측을 같은 행에서1:1 평균합니다. 가중치 탐색·추가 모델 적합 없이 같은 내부/외부 그룹에서 평가합니다. 참가자 로컬 비공개 캐시와 앞선 감사가 있는 작업 공간에서 **새 출력 폴더**에 개발 계산만 재현할 수 있습니다.

```powershell
python -X utf8 scripts/evaluate_temperature_mean.py --output outputs/private/temperature_mean_reproduction_v2
python -X utf8 scripts/audit_temperature_mean.py --experiment outputs/private/temperature_mean_reproduction_v2
```

완료된 개발 폴더는 `outputs/private/temperature_mean_20261010_v1/`입니다. `config/temperature_mean_experiment.json`은 같은 분모·고정0.5/0.5·지점 손실5%·저온 비악화 조건을 기록합니다. 보호·개봉8/4/2·완료된 다음 겨울 정답은 새 후보 학습·선택에 쓰지 않습니다.

`temperature_mean_blind_validation.py`의 `prepare/audit/collect/evaluate`는 새 위치 선택→모델/입력/예측 봉인→사전 재학습 검산→첫 겨울 수집→일회 평가 절차입니다. 이번23102·23407은 이미 수집·평가·감사 완료했으므로 **두 지점에서 새 블라인드로 다시 실행하지 않습니다.** `prepare`는 기존 요청 ID를 거부하고 `evaluate`와 `audit_temperature_mean_blind.py`는 기존 결과·감사 덮어쓰기를 거부합니다. 완료 폴더는 `outputs/private/temperature_mean_blind_20261010_v1/`입니다.

현재 해시 확인은 정답 재수집·추가 후보 선택 없이 실행합니다.

```python
from pathlib import Path
from scripts.fresh_station_validation import verify_seal, old_freezes
seal = verify_seal(Path('outputs/private/temperature_mean_blind_20261010_v1'))
print(seal['rows'], seal['stations'], old_freezes())
```

`summary.json`은 저온 오차 증가에 따른 온도 기준 실패, `independent_verification.json`은 원문/예측 검산 일치와 사전 결빙 기준 실패를 기록합니다. 독립 감사는 수집 전에 기록한 `ice_gate`를 별도 계산했습니다. 위치9.1/11.1m는 정적 표기 허용 범위 안이며 두 지점이 전북 밖임을 확인한 별도 지리 검토와 구분합니다. `review_temperature_mean_failure.py`는 완료한 개봉 결과의 기술 표만 만들고 `plot_temperature_mean_review.py`는 감사된 결과만 그립니다. 기존 실패 기술·그림·영수증의 덮어쓰기를 거부합니다.

AWS 서비스403·전체 첫 겨울 관측 확보는 아직 해결되지 않았습니다. 공개 샘플이나 더 가까운 지점 좌표를 실제 관측자료로 교체하지 않습니다. 향후 기상망 확장 비교는 기존 계획4곳 원문·품질 감사가 선행되어야 합니다.

## 직전 거리 제거·기상 지점 이력 검산 — 2026-10-10

[후속 보고서](../research/WEATHER_DISTANCE_AND_NETWORK_REVIEW_20261010.md)의 비교는 원래 첫 겨울 개발23곳만 사용합니다. 봉인된 개봉8/4곳·보호3곳·완료된 다음겨울 정답으로 새 후보를 선택하지 않습니다. 다음 명령은 비공개 원천과 앞선 감사 결과가 있는 로컬 작업 공간에서 기존에 없는 출력 폴더에 실행합니다.

```powershell
python -X utf8 scripts/evaluate_weather_distance.py --output outputs/private/weather_distance_reproduction_v2
python -X utf8 scripts/audit_weather_distance.py --experiment outputs/private/weather_distance_reproduction_v2
```

`config/weather_distance_experiment.json`은 기상14 HGB100의 같은 조건에서 거리2개만 제거하는 후보 하나를 고정합니다. 앞선 온도 입력·기준 모델의 해시를 확인하고 새 후보10개를 학습합니다. 현재 `weather_distance_20261010_v1/`는 실행·별도 재추론 감사까지 완료했으며 덮어쓰기를 거부합니다. 지점 손실 기준 실패와 독립 감사 일치는 서로 다른 결론입니다.

공개 지점 이력 재현은 새 비공개 review 폴더에 `portal_station_lists_v2/AWS.csv`, `ASOS.csv`, 성공 응답의 `portal_station_manifest_v2.json`, 실제 접근 상태의 `aws_probe_manifest.json`을 준비한 뒤 실행합니다. CSV는 기상청 공개 포털에서 받은 cp949 지점 이력이어야 합니다. 관측값이나 대회 정답을 이 CSV에 넣지 않습니다.

```powershell
python -X utf8 scripts/plan_weather_network_expansion.py --review outputs/private/weather_network_reproduction_v2
python -X utf8 scripts/audit_weather_network_expansion.py --review outputs/private/weather_network_reproduction_v2
```

두 명령은 API 요청·관측 수집·모델 학습을 하지 않습니다. 기존 첫 겨울 개발 ID와 정적 위치만 읽으며 생산 필터/순위와 별도 계산을 대조합니다. 현재 `weather_network_review_20261010_v1/metadata_analysis/`는 감사 완료 상태이며 새 영수증 생성·기존 분석 덮어쓰기를 거부합니다. AWS341의관측 기간과 ASOS좌표 차이를 별도 파일로 남깁니다.

`metadata_analysis/aws_expansion_plan.json`은 AWS614·647·730·914 추가만 고정한 후속 계획입니다. 실제 AWS 서비스403을 해결하고 원문·단위·기간·누락·좌표 감사를 완료해야 기상망 확장 비교를 시작할 수 있습니다. 공개 지점 후보나 거리 감소를 실제 관측 확보·성능 개선으로 간주하지 않습니다. `plot_weather_distance_review.py`는 현재 감사 결과로만 그림을 만드는 일회 진입점이며 완료 그림·영수증을 보존합니다.

## 직전 온도·일별 임계값 비교 — 2026-10-10

추가 [미해결 사항 검토](../research/UNRESOLVED_EVIDENCE_REVIEW_20261010.md)는 이미 개봉한 첫 겨울 자료의 좌표·분모·입력 조건을 진단합니다. 원본 예측과 봉인을 보존하고 새 모델 학습·재추론을 하지 않습니다. 로컬 원천이 있는 작업 공간에서 새 폴더로 재현할 수 있습니다.

```powershell
python -X utf8 scripts/review_unresolved_evidence.py --output outputs/private/unresolved_reproduction_v2/analysis
python -X utf8 scripts/audit_unresolved_evidence.py --review outputs/private/unresolved_reproduction_v2
```

기존 `unresolved_review_20261010_v1/analysis/`와 `verification/`에는 실행을 완료했으며 덮어쓰기를 거부합니다. 재현 폴더에 공개 원문 목록이 없으면 관측·평가 계산만 수행합니다. 원문 목록이 있는 경우 해시를 함께 확인합니다. `plot_unresolved_evidence.py`는 고정 원본 진단으로 그림을 만드는 일회 진입점이며 현재 그림·기록이 있으면 재실행을 거부합니다.

[심사 관점 보고서](../research/AWARD_READINESS_REVIEW_20261010.md)의 실험은 수정본의 첫 겨울 23개 지점 고정 입력을 사용합니다. 아래 명령은 참가자의 원본 작업 공간에서 **기존에 없는 새 출력 폴더**에만 실행합니다. 반복 개발 재현이며 새 독립 성능을 만드는 명령이 아닙니다.

```powershell
python -X utf8 scripts/evaluate_temperature_transfer.py --profile thermal --output outputs/private/temperature_transfer_reproduction_v2
python -X utf8 scripts/audit_temperature_transfer.py --experiment outputs/private/temperature_transfer_reproduction_v2
python -X utf8 scripts/evaluate_temperature_transfer.py --profile loss --output outputs/private/temperature_loss_reproduction_v2
python -X utf8 scripts/audit_temperature_transfer.py --experiment outputs/private/temperature_loss_reproduction_v2
python -X utf8 scripts/evaluate_daily_threshold_transfer.py --output outputs/private/daily_primary_reproduction_v2
python -X utf8 scripts/audit_daily_threshold_transfer.py --experiment outputs/private/daily_primary_reproduction_v2
python scripts/check_repository.py --include-untracked
python scripts/check_markdown.py --include-untracked --render-dir outputs/private/markdown_review_20261010
```

`thermal`은 날씨14 잔차·열24 직접/잔차 후보, `loss`는 날씨14 절대 손실100·제곱 손실300·절대 손실300 후보입니다. 중첩 선택은 외부 그룹과 내부 그룹을 모두 학습에서 제외합니다. 입력·모델·실행 소스 스냅샷·선택 기록·유효 분모·기존47/549 고정 파일 검증을 보존합니다.

이번 새4개 지점은 `outputs/private/temperature_blind_20261010_v1/`에 수집·일회 평가·감사까지 완료했습니다. `temperature_blind_validation.py`의 `prepare/audit/collect/evaluate`는 단계별 봉인 파이프라인이며 **현재 네 지점에서 다시 실행하지 않습니다.** 이미 요청한 지점의 새 블라인드 봉인과 기존 결과 덮어쓰기는 차단됩니다. `audit_temperature_blind_validation.py`도 기존 감사 파일이 있으면 덮어쓰지 않고 종료합니다.

봉인 자료의 현재 해시만 확인할 때는 다음 Python 코드를 실행할 수 있습니다. 정답을 수집하거나 지표를 새로 선택하지 않습니다.

```python
from pathlib import Path
from scripts.fresh_station_validation import verify_seal, old_freezes
seal = verify_seal(Path('outputs/private/temperature_blind_20261010_v1'))
print(seal['rows'], seal['stations'], old_freezes())
```

`summary.json`은 사전 온도 채택 조건 실패를, `independent_verification.json`은 원문·지표 검산 일치와 **33407 위치 확인 필요**를 기록합니다. 간격539개 모두1.3초 이상이나 위치 검증까지 통과한 결과가 아닙니다. 비교 그림의 생성 코드는 `plot_temperature_transfer_review.py`이며 기존 그림·영수증을 보존하려고 재생성을 거부합니다.

## 연구 인계물 검산

참가자 본인의 로컬 `outputs/private/research_delivery_20261009_v2/`에 코드·모델·첫 겨울 학습 표·새 8개 지점 고정 입력과 정답·구간 결과·문서를 묶었습니다. 인증키·보호 정답·기존 다음 겨울 9개 지점 정답은 포함하지 않습니다. 제공 자료에서 파생한 파일이 있으므로 외부 업로드용이 아닙니다.

```powershell
python -X utf8 scripts/reproduce_research_delivery.py --delivery outputs/private/research_delivery_20261009_v2 --verify-only
```

전체 패키지 재현은 실제 실행했고 완료 기록을 남겼습니다. 재실행은 기록을 덮어쓰지 않고 거부합니다. 다른 위치에 패키지를 복사해 첫 검산할 때는 패키지 `README.md`의 설치·실행 명령을 따릅니다. 원본 캐시 없이 첫 겨울 23개 지점 회귀 재적합·기존 저장 모델 추론·새 8개 지점 고정 예측·지표를 재현하지만, 전 구간 GIS 원천 재구축까지 재현하는 패키지는 아닙니다.

새 지점 수집·평가는 완료했습니다. `fresh_station_validation.py prepare/collect/evaluate`를 완료 지점에서 다시 실행하지 않습니다. 이미 정답 요청 이력이 있는 8개 지점에 새 블라인드 봉인을 만드는 것도 코드에서 차단합니다. 아래 감사 결과는 원본 폴더의 `independent_verification.json`으로 확인하며, 기존 감사 파일이 있는 재실행은 거부됩니다. 수집 간격 편차와 성능 검산의 구분은 [새 지점 보고서](../research/FRESH_STATION_REVIEW_20261009.md)에 있습니다.

## 보정·상태·구간 진입점

아래 명령은 원본 첫 겨울 학습 입력·고정 모델·링크·기상 캐시가 있어야 실행됩니다. 이미 완료한 원본 폴더를 덮어쓰지 않도록 **새 출력 폴더만** 지정합니다.

```powershell
python -X utf8 scripts/evaluate_score_calibration.py --output outputs/private/score_calibration_reproduction_v2
python -X utf8 scripts/audit_score_calibration.py --experiment outputs/private/score_calibration_reproduction_v2
python -X utf8 scripts/diagnose_state_temperature.py --output outputs/private/state_temperature_reproduction_v2
python -X utf8 scripts/build_segment_exposure.py --winter first --output outputs/private/segment_exposure_reproduction_v2
python -X utf8 scripts/audit_segment_exposure.py --experiment outputs/private/segment_exposure_reproduction_v2
```

두 번째 겨울의 기상 전용 구간 재구축은 `--winter second`와 다른 새 출력 폴더를 사용합니다. 코드가 AWS·ASOS만 읽으며 RWIS 정답을 입력으로 받지 않습니다. `render_segment_review.py`는 감사된 두 원본 겨울 폴더에서 JPG·HTML을 새 `--output`에 생성합니다. 1km는 하위 중앙점 통계의 길이 가중 평균이라는 [필드 정의](../research/SEGMENT_EXPOSURE_REVIEW_20261009.md#필드와-1km-집계-의미)를 함께 읽습니다.

## 직전 상태 분류 진단 재현

온도 교차 추정·이진/다중 상태 실험은 기존 첫 겨울 입력과 감사된 HGB 회귀 모델이 있어야 실행됩니다. **새 출력 폴더만 허용**하며 다음 겨울·보호 지점 정답을 읽지 않습니다. 현재 원본 실험은 두 새 후보 모두 미채택입니다.

```powershell
python scripts/evaluate_joint_surface.py --output outputs/private/joint_surface_reproduction_v2
python scripts/audit_joint_surface.py --experiment outputs/private/joint_surface_reproduction_v2
python scripts/diagnose_joint_surface.py --experiment outputs/private/joint_surface_reproduction_v2
python scripts/plot_joint_surface.py --experiment outputs/private/joint_surface_reproduction_v2 --output outputs/private/joint_surface_reproduction_v2/review.png
```

평가·감사·사후 순위 진단·집계 그림 순서입니다. 입력 파일과 고정 매개변수는 첫 명령의 `paths`·`PLAN`에 명시합니다. 자동 등록된 기존 100단계와 서명된 수정본을 변경하지 않는 별도 개발 실험이며, [최신 보고서](../research/JOINT_SURFACE_REVIEW_20261009.md)에 분모·누수 경계·실패·다음 실행 조건을 정리했습니다.

## 직전 고정 진단 재현

다음 명령은 저장소 루트에서 실행합니다. 필요한 기존 입력은 Git에 포함하지 않습니다.

```powershell
python scripts/evaluate_development_thermal_ice.py --predictions outputs/private/thermal_ice_diagnostics_20261009_v1/predictions.parquet --output outputs/private/thermal_ice_reproduction_v2
```

첫 겨울의 기존 그룹 제외 예측·정답·수분 입력으로 네 고정 기준을 다시 집계합니다. 새 학습·임계값 탐색·모델 선택은 없습니다. 입력에는 `station`, `time`(KST), `state_raw`, `ice`, `baseline_ice`, `baseline_weather`, `selected_weather`, `aws_dewpoint`, `rain15_max_3h`, `asos_snow_cm`이 필요합니다. 이 CLI 자체가 입력의 OOF 생성 과정을 증명하지는 않으므로, 원본 실험의 입력 서명·온도 선택·독립 감사 기록과 함께 사용합니다.

```powershell
python scripts/reproduce_weather_fallback.py --output outputs/private/weather_fallback_reproduction_v2
```

이 명령은 기존 첫 겨울 23개 지점 입력·대회 14개 지점 Ridge·그룹 설정·혼합 정책·고정 평가 서명을 갖춘 환경에서 Ridge/HGB 중첩 비교를 다시 학습합니다. 필요한 경로는 스크립트의 `paths`에 명시돼 있습니다. 원본 실험 설정·입력 경로는 유지하며 **새 결과 폴더만 허용**합니다. 검증 단계가 추가된 저장소 코드의 재현이며, 원본 소스 스냅샷·완료 결과를 덮어쓰지 않습니다. 이번 저장소 정리에서는 전체 회귀를 재학습하지 않았습니다.

## 원본·수정본·완료 평가 관리

| 경로 | 역할·실행 조건 |
| --- | --- |
| 프로젝트 루트 | `20260915` 원본 설정·캐시 보존. 최신 추가 진단의 별도 진입점 실행 |
| `outputs/private/releases/20261007/` | 수정본의 감사·100개 단계·51개 셀 분석 환경. 서명된 코드·산출물 보존 |
| 수정본 `outputs/private/external_reserved_predictions_v1/` | 정답 수집 전 고정한 기존 다음 겨울 예측 |
| 수정본 `outputs/private/external_reserved_assessment_v1/` | 완료한 다음 겨울 일회 평가. 재실행하지 않음 |
| 수정본 `outputs/private/external_reserved_result_audit_v1/` | 완료 평가의 독립 감사. 재실행하지 않음 |
| 수정본 `outputs/private/submission_draft_v1/` | 기존 제출 초안. 공식 제출이나 새 최종 모델이 아님 |

기존 노트북에는 출력과 실행 번호를 저장하지 않습니다. `scripts/check_notebook.py`는 실제 Jupyter 커널을 실행하는 데이터 의존 검사이며, 전체 코드 테스트와 구분합니다. 수정본 원본 단계와 과거 실제 명령은 아래 기록을 참조하되 수집·평가가 ‘대기 중’인 과거 상태를 현재 상태로 해석하지 않습니다.


<details>
<summary>이전 실행 기록 — 당시 수치·가정·진행 상태 보존</summary>


## 고정 온도·수분 가안과 완료된 다음 겨울 감사 — 2026-10-09

원본 `evaluate_thermal_ice_rules_20261009.py`는 그룹 제외 온도 OOF에 사전 고정한 0°C·수분 근거를 적용했다. 같은 폴더의 `test_thermal_ice_rules_20261009.py` 합성 3개와 `verify_thermal_ice_rules_20261009.py` 독립 4개 가안·4,240일별행·347개 사건 검산을 통과했다. `render_thermal_ice_rules_20261009.py` 그림을 확인했다. 원본 결과 `outputs/private/thermal_ice_diagnostics_20261009_v1/`를 읽으며 완료 폴더를 지우거나 덮어써 재실행하지 않는다.

기존 세션 16979의 수집·일회 평가가 종료코드 0으로 끝났다. 원본 `audit_external_reserved_results_20261009.py`도 전체 완료 후 실제 감사에 통과했다. 수정본 `outputs/private/external_reserved_assessment_v1/summary.json`, `outputs/private/external_reserved_result_audit_v1/summary.json`이 기존 고정 평가와 감사 기록이다. 감사 결과가 있으므로 다시 감사·평가를 실행하지 않는다. 예전 prepare-only·수집 중 기록은 당시 상태로 보존한다.

원본 `characterize_completed_reserved_shift_20261009.py`는 완료·감사된 자료에서 두 겨울 상태·온도 분포만 기술했다. 새 예측·학습·선택은 하지 않았다. 결과는 원본 `outputs/private/completed_reserved_shift_20261009_v1/`다. 원본 `docs/research/THERMAL_ICE_AND_RESERVED_REVIEW_20261009.md`를 읽어 새 개발 가안 F1 0.109033과 기존 다음 겨울 F1 0.008725를 구분한다. 현재 새 가안의 독립 성능은 미확인이다. 549개/47개 파일·100단계·51셀 노트북을 유지한다.

## 기상 단독 온도 HGB·관측소 대표성 후속 — 2026-10-09

원본 작업 공간에서 `python -X utf8 outputs/private/train_weather_fallback_20261009.py`를 실행해 같은 변수 14개로 Ridge·HGB의 그룹 제외 비교와 참조 장애 조건 5개를 완료했다. `test_weather_fallback_20261009.py`의 별도 합성 테스트 4개, `verify_weather_fallback_20261009.py`의 모델 32개·장애 지표 220개 검산도 통과했다. 완료 결과가 있으면 재실행을 거부하며 새 후보는 새 버전 폴더를 사용한다.

`audit_sensor_representation_20261009.py`로 첫 겨울의 종류별 라벨·기존 OOF·외부 점수 진단을 생성했다. `interpret_weather_fallback_20261009.py`로 이를 별도 코드 검산하고 온도 개선 그림을 생성했다. 원본 `outputs/private/weather_fallback_20261009_v1/`와 `outputs/private/sensor_representation_20261009_v1/`의 요약·검증 기록을 읽는다. 기상 단독의 9개 지점 개선과 혼합의 33413 악화를 함께 확인한다.

원본 `docs/research/WEATHER_FALLBACK_REVIEW_20261009.md`와 `outputs/private/weather_fallback_followup_plan_20261009.json`을 후속 조건으로 읽는다. 외부 온도 OOF만으로 대회 14개 지점의 보조 입력까지 완료됐다고 보지 않는다. 보조 분류를 학습하기 전에 대회 지점도 포함한 내부 OOF를 만들고 모든 제외 지점을 일관되게 유지한다. 당시 다음 겨울 고정 모델을 새 HGB로 교체하지 않았다. 고정 파일 549개·47개, 등록 단계 100개·노트북 셀 51개도 유지했다.

## 결빙 가중치·후보 선택과 온도 참조 장애 검증 — 2026-10-09

원본 작업 공간에서 `python -X utf8 outputs/private/train_ice_group_balanced_20261009.py`로 첫 겨울 지점/사건 가중치와 F1 선택 비교를 완료했다. 완료 결과가 있으면 재실행과 `--resume`을 모두 거부한다. 새 실험은 별도 버전 경로를 사용하고 기존 폴더·서명을 삭제해 우회하지 않는다. `test_ice_group_balanced_20261009.py`의별도 합성 4개를 통과했다.

`stress_temperature_gate_20261009.py`는 고정된 이전 온도 혼합 가안에 참조 지연·미수신 5조건을 적용했다. `verify_ice_group_balanced_20261009.py`의별도 코드 감사와 `interpret_ice_group_balanced_20261009.py`의사건진단·공식TR1주석·그림도 완료했다. 산출물은 원본 `outputs/private/ice_group_balanced_20261009_v1/`, `outputs/private/temperature_gate_stress_20261009_v1/`에 보존했다. 독립 감사가 통과했더라도 시점 F1 상승과 일별/사건탐지 하락을 함께 읽어 분류 가안을 채택하지 않는다.

원본 `docs/research/ICE_GROUP_BALANCED_REVIEW_20261009.md`와 `outputs/private/ice_followup_after_group_balance_20261009.json`이 다음 개발 조건이다. 기상 단독 HGB·상태 보조 예측은 아직 실행하지 않은 후속 후보로 구분한다. 현재 다음 겨울 평가의 모델·임계값을 교체하지 않는다. 등록 100단계·51셀 노트북·549개/47개 고정 파일을 유지한다.

## 결빙 병목·혼합 가안 진단 — 2026-10-09

원본 작업 공간의 `outputs/private/ice_bottleneck_review_20261009.py`로 첫 겨울 진단, 그룹 제외 임계값 이전, 온도·수분 재분류 모델 16개, 거리·시간대 온도 혼합 가안을 실행했다. 원본 `outputs/private/test_ice_bottleneck_review_20261009.py`의 합성 테스트 4개와 `verify_ice_bottleneck_review_20261009.py`의 별도 코드 검산을 통과했다. `interpret_ice_bottleneck_review_20261009.py`는 가당1교/가당2교, 상수 기준선, 오경보 상태의 진단을 보완했다. 결과는 원본 `outputs/private/ice_bottleneck_review_20261009_v1/`에 있으며 이미 존재하면 재생성을 거부한다.

원본 `docs/research/ICE_BOTTLENECK_REVIEW_20261009.md`와 `outputs/private/ice_vnext_execution_plan_20261009.json`을 다음 개발 버전의 실행안으로 읽는다. 당시 수집 중이던 겨울의 고정 모델을 새 가안으로 교체하거나 수집 중인 정답으로 선택하지 않았다. 등록 단계 100개·노트북 셀 51개·고정 파일 549개·47개를 유지했다. 결빙 가안은 개선 실패, 온도 가안은 개발 MAE 개선과 호남 2개 지점 악화를 함께 기록했다.

## 다음 겨울 완료 평가의 독립 감사 준비 — 2026-10-09

원본 작업 공간에서 `python outputs/private/audit_external_reserved_results_20261009.py --prepare-only`로 정답을 읽지 않고 완료 조건을 확인한다. 기존 세션 16979는 전체 수집 뒤 `evaluate_external_reserved.py`를 일회 실행하도록 구성돼 있다. 실제 평가가 완료된 뒤 원본 작업 공간에서 `python outputs/private/audit_external_reserved_results_20261009.py`를 실행한다. 이미 감사 결과가 있으면 재실행을 거부한다. 기존 평가·감사 폴더를 삭제해 우회하지 않는다.

추가 합성 검증은 `python outputs/private/test_external_reserved_result_audit_20261009.py`이며 현재 3개 테스트를 통과했다. 이는 새 모델 학습이나 실제 다음 겨울 점수 검증이 아니다. 모델 선택·임계값을 바꾸지 않고 원본 47개·외부 예측 549개 파일을 보존한다. 수집 건수가 잠시 그대로여도 전송 캐시가 갱신되는 경우 기존 시간 구간 분할 처리가 진행 중이므로 실제 세션·프로세스를 확인한다.

### 독립 거리 구간 검증과 반복 선형 제한 — 2026-10-09

독립 검증에서 서해안 원본 링크 3190009600의 선형이 단순하지 않음을 확인했다. 원본 길이 15,593.252868m와 노딩한 선형 집합 길이 15,592.602368m 사이에는 0.650500m의 반복이 있었다. 최근접 거리 투영만으로는 일부 반복 조각의 위치가 모호해 첫 가정 검사가 실패했다. 실패 소스·실제 투영 사례는 원본 `outputs/private/bridge_direction_failed_distance_projection_20261009/`에 보존했다.

원본 도형은 수정하지 않고, 검증에서만 노딩한 단순 선형 조각의 거리 구간을 사용했다. 원본과 검증용 집합의 Hausdorff 거리는 0이지만 해당 링크의 엄격한 위상 동등성 검사는 실패했다. 이를 별도로 기록했으며 좌표 대조 허용 오차는 1e-8m다.

실제 교차 조각 1,038개의 거리·좌표 대응을 검증한 뒤 이벤트법으로 배타 클래스 길이 3,600개를 별도 계산했다. 폴리곤 배타 분할 계산과의 최대 차이는 2.20e-10m였고 24개 집계도 일치했다. 이 계산 일치가 실제 도로 구조·시설 시점·원본 반복 선형의 최종 승인을 뜻하지는 않는다. 전북 경계를 확정한 뒤 새 구간 버전에서도 해당 링크의 추적·중첩·방향을 다시 검토한다.

## 도로교 장축·국지 도로 방향 민감도 — 2026-10-09

원본 `outputs/private/audit_bridge_direction_sensitivity_20261009.py`가 도로교 275개와 링크 150개의 방향 민감도를 생성했다. 출력은 수정본 시설 검토 폴더의 `bridge_direction_sensitivity_v1/`이다. 결과가 있으면 재실행을 거부한다. 조합별 CSV 567행의 짝별 길이는 중복될 수 있어 합산하지 않는다. 배타 클래스 링크 CSV와 설정 12개 요약 CSV의 합집합 길이를 읽는다. 장축 비율 1.5·2·3, 국지 방향 길이 10·30m, 각도 15·30도는 분석 민감도 설정이다.

최초 교차 선분 합집합의 실패 소스·진단은 원본 `outputs/private/bridge_direction_failed_clip_union_20261009/`에 있다. 폴리곤 합집합 후 원본 선형과 교차해 복구한 길이 검사 3,600개와 추가 독립 거리 재계산을 확인한다. 당시 검토 노트북은 코드 셀 51개이며 이전 셀 50개 검증 기록은 당시 버전의 기록으로 보존한다. 고정 후 재생성을 건너뛰는 기본 설정, 모델, 서명 파일 549개도 유지한다.

## 제공 설명서 기반 도로교·보도교·철교 구분 — 2026-10-09

원본 `outputs/private/audit_road_bridge_kinds_20261009.py`를 실행해 제공ZIP의 설명서·XML을 보존하고 275개도로교만의 수평 중첩을 계산했다. 출력은 수정본 시설검토 하위 `road_bridge_kind_review_v1/`다. 기존 결과를 삭제하거나 덮어써 재실행하지 않는다. `summary.json`의 원본 멤버 해시·종류 사전·원본 FID/좌표 대조·도로교 길이 보존 6개 검사·미확정 시점 플래그를 확인한다. 원본 전체 교량 중첩과 분류 코드도 유지한다.

검토 노트북 50개 코드 셀에서도로교 결과·영향 링크를 읽는다. 49개 셀 검증 기록은 당시 버전의 기록으로 보존하고 현재 50개 셀은별도 커널 영수증으로 검증한다. 고정 후 자동 테스트/작은 모델 재생성은 건너뛰며 등록 단계 100개와 549개 서명 파일은 변경하지 않는다.

## 시설 폴리곤 중첩·원본 속성 불일치 검토 — 2026-10-09

원본 작업 공간의 `outputs/private/audit_directed_facility_overlap_20261009.py`가 링크 150개·구간 852/426개의 제공 시설 폴리곤 중첩을 생성했다. 기존 결과가 있으면 재실행을 거부한다. 출력은 수정본 `outputs/private/spatial/official_directed_facility_overlap_review_v1/`다. `summary.json`의 원본 ZIP/시설 사이드카 일치·중복 없는 UFID·중첩 길이 보존 12개 검사·미확정 플래그·파일 해시를 확인한다.

`outputs/private/review_facility_overlap_cases_20261009.py`로 노드 원문·불일치 링크·영향 추적 조각·민감도 그림을 생성했고, `render_facility_cases_readable_20261009.py`로 별도 사례 그림을 만들었다. 하위 `diagnostic_review_v1/summary.json`과 `plot_review_verification.json`을 먼저 대조한다. 최초 그림·요약은 보존한다. 두 불일치 링크의 원본 코드 004는 유지하며 고정 모델·임계값을 변경하지 않는다. 새 경계 절단 버전이 생기면 원본 추적과 중첩 검사를 별도 버전에서 다시 수행한다.

검토 노트북은 49개 코드 셀이다. 정답 전 예측 고정 영수증이 있으면 초반 테스트/작은 모델 재생성 셀도 자동 건너뛰고 기존 산출물을 읽는다. `REBUILD_FULL=False`, `RUN_STAGES=[]`를 유지하며 수집 중인 다음 겨울의 부분 정답 성능을 계산하지 않는다. 최신 112개 코어 테스트 통과 기록을 보존했다.

## 방향별 후보의 공식 도로환경 검토 — 2026-10-09

원본 작업 공간에서 `outputs/private/analyze_directed_road_environment_20261009.py`를 실행해 공식 DBF 150개 링크 속성 대조와 후보별 길이 가중 결합을 완료했다. 출력은 수정본의 `outputs/private/spatial/official_directed_environment_review_v1/`다. 기존 결과가 있으면 생성기는 재실행을 거부한다. 원본·기존 결과를 삭제해 우회하지 않는다.

`summary.json`의 150링크 대조·규격별 852/426개 구간·유형별 길이 보존·GPKG 재읽기 근거를 확인한다. `plot_review_verification.json`의 해시를 확인한 뒤 `structure_code_share_by_route_readable.png`를 읽는다. 최초 누적 막대의 레이블 겹침 그림은 보존했다. 원본 속성은 과거 링크의 코드·차로수·최고 제한속도·구축날짜이며 현재 물리적 구조물 경계나 위험점수가 아니다.

코어 모델·정답 전 예측의 549개 서명 파일과 원래 47개 고정 파일은 유지한다. 전북 경계가 확보되면 새 경로 버전의 원본 조각 추적을 만든 뒤 해당 버전으로 환경 속성을 다시 결합한다. 이전 후보의 구간ID와 새 구간ID를 임의로 혼용하지 않는다. 속성 대조·비중 보존·구간 좌표·CSV/GPKG 재읽기를 다시 검증한다.

## 외부 다음 겨울 예측 고정 후 현재 검증 — 2026-10-09

모델 43471·독립 재검산 85601·예측 22579는 정상 종료했다. 현재 세션 16979는 외부 다음 겨울 자료 수집→전체 2,160개 구간 확인→고정 예측 일회 평가를 수행한다. `outputs/private/external_reserved_assessment_pipeline_20261009_recovery.ps1/.json`과 실제 세션을 확인하며 중복 수집하지 않는다. 최초 한글 경로 실패 영수증도 보존했다. 인증 경로는 프로젝트 기준 상대 경로로 해석하고 키값을 로그에 남기지 않는다.

`external_reserved_predictions_v1/predictions_receipt.json`은 9개 지점 155,520행과 549개 파일을 정답 수집 전에 고정했다. 이 영수증의 서명 파일은 수정·재학습·임계값 변경하지 않는다. 전체 수집 완료 전 정답의 부분 성능을 계산해 후속 후보 선택에 이용하지 않는다. 외부 독립 검증으로 보고하고 원래 47개 고정 파일을 유지한다. 평가가 이미 존재하면 스크립트가 반복 평가를 거부한다.

첫 겨울 실제 결과는 `external_nested_audit_v1/`에 있다. 분류는 네 그룹 모두 기준 유지, 온도는 합산 오차 소폭 감소와 개별 4개 지점 악화를 함께 확인했다. 갱신한 47개 코드 셀 검토 노트북은 결과·예측 영수증을 읽는다. 전북 경계 파일 도착 후 공간 검증은 별도로 진행하되 고정한 모델 실험의 서명 파일을 바꾸지 않는다.

## 전체 수집 이후 모델 실행 복구 — 2026-10-09

수집 69298과 파이프라인 67466은 종료했다. 전체 원문 감사와 입력 생성은 통과했으며, 모델의 결측 참조JSON 저장 실패만 수정했다. 실패 폴더 `external_augmentation_nested_v1_failed_json_20261009T060228Z/`의 원본·소스·해시는 보존한다. 회귀 검증을 거쳐 실행한 현재 모델 세션은 43471이며 `external_model_recovery_pipeline_20261009.ps1/.json`에서 두 단계 상태를 확인한다. 아직 살아 있는 실행을 중복 호출하거나 입력·서명 소스를 변경하지 않는다.

전체 품질 스냅샷은 `external_quality/snapshot_33350d92de2095cf/`다. 전체 2,160개 요청을 감사했고, 관측 155,257행·상태 유효 155,118행·Ice 6,611행을 확인했다. 이 수집은 외부 첫 겨울만 포함하며 다음 겨울 정답은 미개봉이다. 모델 결과 완료 뒤 원본 작업 공간의 `outputs/private/audit_external_nested_results_20261009.py`로 선택·OOF 임계값·파일 해시·같은 정답 행·지점별 지표를 재검산한다. 이 감사가 끝나고 모든 9개 지점 다음 겨울 예측·모델·임계값·소스를 고정한 뒤에만 별도 외부 검증 정답을 수집한다.

## 외부 분류 완료 학습 재사용 — 2026-10-09

`evaluate_external_augmentation.py`는 현재 프로세스에서 완료된 동일 학습만 재사용한다. 제외 그룹의 순서가 뒤바뀌어도 입력·정답·행 순서·자료형·후보·실험 서명이 일치해야 한다. 복사 폴더의 `cache_reuse_receipt.json`에서 원본 완료 영수증 해시와 파일별 해시를 확인한다. 후보 선택은 각 외부 제외 그룹에서 여전히 다른 세 그룹으로 독립 수행한다. 파일 변조·불일치나 미완료 결과는 재사용할 수 없다. 실제 모델이 시작된 뒤에는 서명된 코드·설정·자료를 변경하지 않는다.

전체 수집 감사가 `development_download_complete`가 되면 별도의 품질 진단을 실행해 전체 첫 겨울 분포를 보존한다.

```powershell
python scripts/analyze_external_rwis_quality.py
```

기존 품질 스냅샷은 보존한다. 학습·정답 정의를 변경하는 명령이 아니며, 모델 선택·예측 고정 뒤에만 다음 겨울 외부 정답 수집을 진행한다.

## 공식 방향별 500m·1km 후보 검토 — 2026-10-09

수정본에서 `build_official_directed_segment_candidates.py`를 실제 실행해 여섯 경로·500m 852개·1km 426개 후보를 만들었다. 결과가 있으면 재실행은 거부하며 원본이나 기존 결과를 삭제해 우회하지 않는다. `outputs/private/spatial/official_directed_segment_candidates_v1/summary.json`과 노트북에서 방향별 경로·민감도·독립 원본 분할 감사를 확인한다.

서해안선 한 쌍의 원본 6.39m 틈은 명시적 예외로 보존했다. 방향 계산 민감도는 8/9개만 일치하므로 `final_geometry_approved=false`다. 경계 확정 전 후보와 기존 467개 추론 구간을 혼합하거나 후보의 로컬 거리를 공식 이정으로 읽지 않는다. 출력 위험점수는 모두 미산정이다.

참가자에게 요청한 SGIS2024 시도경계 ZIP이 도착하면 파일·출처·기준 시점·좌표계·폴리곤 유효성을 확인한다. 실제 경계로 원본 경로를 먼저 자르고 별도 버전으로 500m/1km 구간을 다시 생성한다. 잘린 선의 진행 순서·단절·경계의 짧은 꼬리 구간·원본 링크 추적을 재검증한다. 기존 후보 v1·서해안 접속부 민감도 증거·47개 고정 파일을 보존한다.

개발 수집·모델 검증 세션 69298·67466은 이 경계 요청과 독립적으로 계속 실행 중이다. 재개 시 실제 프로세스와 완료 목록·진행 영수증을 확인하고, 아직 살아 있는 수집을 중복 실행하지 않는다.

## 수집 기록 오류 복구 후 현재 실행·공식 공간 감사 — 2026-10-09

최신 수집은 세션 69298·PID27848, 분석 대기는세션 67466이다. 이전 83686·71969는 종료했으므로 현재 실행으로 재사용하지 않는다. 완료 목록의 1080번째 기록은 원문·전송·변환·기존 1079개 기록을 검증하고재수집 없이 복구했다. 영구 파일 접근 오류 때완료된 임시 목록을 삭제하거나기존 목록을 무조건 덮어쓰지 않는다. 복구 영수증은 `external/kma_rwis_development_v1/manifest_recovery_20261009T045751Z/receipt.json`이다.

현재 순차 실행 소스는 `outputs/private/external_followup_pipeline_20261009T045904Z.ps1`, 영수증은 같은 이름의JSON이다. 실제수집 프로세스를 기다린 후원문 감사→전체 완료 상태 검사→입력 생성→분류 검증→온도 검증을 수행한다. 예측 고정·다음 겨울 정답 수집·최종 평가는 자동 단계에 넣지 않았다. 재개 전중복 실행 여부와파일 기록을 확인한다.

공식 2024 도로망을 확보한 수정본에서 공간 감사를 실제 실행했다.

```powershell
python scripts/audit_official_nodelink_geometry.py
```

기존결과가 있으면 덮어쓰지 않고 거부한다. 이미 생성된 결과는 `outputs/private/spatial/official_nodelink_review_v1/summary.json`과 45개 셀 검토 노트북에서 확인한다. 결과 폴더나 원문을 삭제해 재실행하지 않는다. 원본 ZIP SHA는 `35efe0871e23dd2967af554d227afd448268d04e20d19933819288dd879b05de`다. 노선번호와노선명, 사용 여부, 연결로 코드, 원본WKT를 함께 확인하며 원본 좌표에EPSG:5179를 단순 지정하지 않는다. 근접도는 25m 샘플과분석자 30/100m 기준의 진단이다. 원래 구간의상하행·공식 이정·정확한 본선 소속을 확정하지 않는다.

다음 공간 작업은 공식 사용·비연결로를 대상으로 노드 연결·분기·방향을 검토하고, 제공 범위와 연결로를 구분해 500m/1km 구간을 구축하는 것이다. 거리표의km를 연결하려면 별도의 공식 이정 기준점과이용 조건 검증이 남는다. 기존 47개 고정 파일은 수정하지 않는다.

## 후속 분석 재개와 정답 없는 입력 캐시 — 2026-10-09

사용자 지시에 따라 884개 구간 이후 수집을 재개했다. 아래 기존 중단 기록은 당시 상태다. 추가 9개 지점 첫 겨울 전체 155,520행의 입력 캐시는 생성·검증되었으며, 63,385개 실제 감사 시각에서 직접 계산과 정확히 일치했다.

```powershell
python scripts/precompute_external_development_inputs.py
```

수정본 `outputs/private/external_development_inputs_v1/manifest.json`은 원천·소스 서명과 지점별 파일 해시를 고정한다. 캐시가 있으면 `build_kma_external_development_features.py`가 정답을 결합하기 전에 검증해 재사용한다. 출처가 달라졌을 때 캐시를 덮어쓰거나 서명만 갱신하지 말고 기존 증거를 보존한다. 부분 자료의 `--snapshot` 실행은 입력 결합 점검만 허용한다.

현재 비공개 `outputs/private/external_followup_pipeline_20261009.ps1`은 수집PID17644의 신원을 확인하고 종료를 기다린 뒤 감사·전체 입력 생성·분류·온도 검증을 순차 실행한다. 수집 완료 여부는 종료 자체가 아니라 감사의 `development_download_complete`로 확인한다. 진행 영수증은 `external_followup_pipeline_20261009.json`이며 PowerShell의 UTF-8 BOM을 포함하므로 Python에서는 `encoding="utf-8-sig"`로 읽는다. 외부 다음 겨울 정답을 여는 단계는 이 실행에 포함하지 않았다.

중복 실행을 막기 위해 새 수집이나 분석을 시작하기 전에 세션 83686·71969와 실제 프로세스·진행 영수증을 확인한다. 마지막 구현 검증은 96개 단위 테스트와 두 노트북 각 44개 셀이다. 최초 보호 평가·고정 파일 47개·제출 초안 v1을 유지하며 아직 실제 성능 개선·최종 제출 완료로 처리하지 않는다.

## 작업 중단 후 재개 — 2026-10-09

현재는 사용자 요청으로 일시 중단했다. 실행 중인 수집은 종료했고, 첫 겨울 884/2,160개 구간을 감사·보존했다. 비공개 `outputs/private/work_pause_checkpoint_20261009.json`에 파일 해시, 종료 확인, 미완료 구간과 기존 검증 근거를 기록했다. **사용자가 후속 작업을 재개한 뒤** 아래 순서로 진행한다.

```powershell
Set-Location -LiteralPath 'D:\프로젝트\icy-road-ai\outputs\private\releases\20261007'
python scripts/download_kma_external_development.py --credentials-file 'D:\프로젝트\icy-road-ai\secret.env'
python scripts/audit_kma_external_development.py
```

완료 캐시를 재사용하고 지점 12408의 2024-12-20 00:00–11:59 KST부터 남은 구간을 이어받는다. 계획 영수증과 고정 계획을 변경하지 않는다. 감사 상태가 `development_download_complete`일 때만 아래 학습 단계를 실행한다.

```powershell
python scripts/build_kma_external_development_features.py
python scripts/evaluate_external_augmentation.py
python scripts/evaluate_external_temperature.py
```

후보 선택 결과를 검토하고 9개 지점 전체의 예측·모델·임계값·입력 및 소스 해시 고정을 완료한 뒤에만 외부 다음 겨울 정답을 연다. 현재 실제 후보 학습·예측 고정·다음 겨울 수집은 수행하지 않았다.

```powershell
python scripts/predict_external_reserved.py
python scripts/download_kma_external_reserved.py --credentials-file 'D:\프로젝트\icy-road-ai\secret.env'
python scripts/evaluate_external_reserved.py
```

다음 겨울 점수를 보고 같은 평가의 모델·임계값을 다시 조정하지 않는다. 기존 공식 보호 평가와 제출 초안 v1은 보존한다. 결과가 나와도 공식 도로 구간·위험도 기준·미확정 제출 규격·최종 패키지 검증을 완료하기 전에는 제출 준비 완료로 처리하지 않는다. 현재 기상 입력 선계산은 미구현 제안이다.

어떤 명령을 어떤 환경에서 실행하는지 안내합니다. 원본 없이 가능한 검증과 대회 원본·중간 산출물이 필요한 분석을 나누어 설명합니다.

[문서 목록·용어 풀이](../README.md) · [프로젝트 소개](../../README.md)

## 물리·지형 고도화 재실행 — 수정본 전용

작업 위치는 `outputs/private/releases/20261007/`이다. 루트의 원본 버전 설정을 그대로 두고 수정본 작업 공간에서 실행한다. 아래는 기존 감사·기상/결빙 특징·분할·센서 메타데이터·공간 복원이 완료된 뒤의 추가 단계다.

```powershell
python scripts/audit_ice_weather_history.py
python scripts/build_physical_features.py
python scripts/evaluate_physical_ice.py
python scripts/compare_physical_ice.py
python scripts/plot_physical_comparison.py
python scripts/build_environment_features.py
python scripts/fetch_copernicus_dem.py
python scripts/fetch_power_radiation.py
python scripts/build_solar_terrain_features.py
python scripts/audit_dem_units.py
python scripts/plot_terrain_evidence.py
python scripts/evaluate_forward_physics.py
python scripts/evaluate_temperature_physics.py
python scripts/evaluate_daily_rank_policy.py
python scripts/evaluate_catboost_forward.py
```

외부 자료 수집 두 단계는 네트워크가 필요하다. 확보한 원천 캐시는 재사용하고 URL·단위·라이선스·해시를 남긴다. 지형 생성에는 `rasterio==1.4.4`가 필요하며 이번 작업에서는 프로젝트 전용 `.venv_research`에 설치했다. 해당 환경의 Python은 `D:\프로젝트\icy-road-ai\.venv_research\Scripts\python.exe`다. 전역 환경을 수정하지 않았고, 동일 환경을 새로 준비할 때는 `requirements.txt`를 사용한다.

CatBoost 비교는 `catboost==1.2.8`을 사용한다. 저장한 폴드별 `.cbm`은 첫 겨울 다른 지점으로 학습한 **개발 검증 모델**이며 최종 제출 모델이 아니다. 일별 개수 제한 정책은 하루 전체 점수에 의존하는 사후 분석이며 이번 비교에서는 악화해 채택하지 않았다.

전체 중첩 모델 검증은 오래 걸릴 수 있다. 폴드별 완료 파일과 입력/코드 서명이 동일하면 재사용하며, 서명이 달라졌을 때 기존 결과를 덮어쓰지 않고 중단한다. 새로운 설정 실험은 별도 출력 위치가 필요하다. NASA 복사 입력은 공개 지연을 가진 사후 분석 전용이며 노트북에는 이 한계를 함께 표시한다.

기준일: 2026-10-07. 현재 경로와 [노트북 단계 설정](../../config/notebook_workflow.json)에 맞춘 실행 안내다. 분석 결과와 과거 가정은 각 보고서에서 확인한다.

## 수정본 작업 위치

10월 7일 자료의 새 실행 루트는 `outputs/private/releases/20261007/`이다. [수정본 검증 보고서](../competition/OFFICIAL_UPDATE_20261007.md)의 재실행 순서를 따른다. 프로젝트 루트의 기본 ZIP·캐시는 20260915 보존본이며 루트 명령으로 새 자료를 실행한 것으로 해석하지 않는다.

## 데이터 없는 검증

프로젝트 루트에서 Python 3.11과 [필요 패키지](../../requirements.txt)를 준비한다.

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/check_repository.py
```

단위 테스트 37개와 추적 파일 검사는 원본 ZIP 없이 가능하다. 저장소 검사는 Git 체크아웃을 기준으로 노트북 출력·금지 파일·문서 링크를 확인한다.

## 참가 권한이 있는 원본 환경

원본은 [data_source.json](../../config/data_source.json)의 파일명·SHA256과 일치해야 한다. ZIP은 루트에 두고 감사·특징·모델·예측 결과는 `outputs/private/`에서 관리한다. 신청서는 실행 입력이 아니다.

```powershell
python scripts/audit_data.py --limit-files 3
python scripts/baseline_asos.py --limit-days 2
```

위 명령은 작은 실행이다. 전체 자료 분석 점수로 해석하지 않는다. ASOS 작은 실행은 `outputs/private/smoke/`로 분리된다. 전체 감사를 먼저 수행한 뒤 전체 특징·학습을 선택한다.

## 노트북 검토와 선택 실행

```powershell
python scripts/check_notebook.py
```

기본 검증은 원본·기존 비공개 집계가 있는 환경에서 Jupyter 커널의 29개 코드 셀을 실행하고 파일에 출력을 저장하지 않는다. 전체 노트북 실행에는 원본·캐시가 필요하다.

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

전체 44개 단계의 정확한 명령·설정·산출물은 [실행 설정](../../config/notebook_workflow.json)을 기준으로 한다. 해석은 [진행 상태](../history/PROJECT_STATUS.md), [검증 규약](../validation/VALIDATION_PROTOCOL.md), [평가 현황](../validation/EVALUATION_STATUS.md)을 참고한다.

## 정정 자료 전환

새 자료는 현재 원본·캐시와 섞지 않고 별도 작업 경로에서 감사한다. 원본 버전 설정과 열·기간·관측소·상태 코드를 대조한 뒤 특징과 모델 산출물을 재생성한다. 기존 캐시를 새 자료의 결과로 취급하지 않는다.

보호 3개 지점은 최종 평가 전까지 학습·모델 조정에서 제외한다. 최종 모델·위험도 지도·데모는 미완료다. [공유 범위](../../.github/PUBLICATION.md)와 데이터 종료 후 폐기 조건을 별도로 유지한다.

## 수정본 센서·안개 후속 검토

아래 명령은 `outputs/private/releases/20261007/`에서 실행한다. 원본 루트의 20260915 배포본에는 안개 자료가 없다. 전체 감사·개발 분할·AWS 대체 결빙 특징과 기본 로지스틱 모델이 선행되어야 한다.

```powershell
python scripts/audit_sensor_availability.py
python scripts/build_fog_features.py
python scripts/build_fog_features.py --delay-minutes 30
python scripts/baseline_ice_logistic.py --variant fog
python scripts/compare_fog_ablation.py
python scripts/audit_spatial.py
python scripts/audit_station_road_alignment.py
python scripts/build_road_segment_scaffold.py
```

등록 ID는 `sensor_availability`, `fog_features`, `fog_logistic`, `fog_comparison`이다. 노트북의 전체 실행은 현재 배포본에 해당하는 단계만 실행하며, 구버전에서 수정본 전용 단계를 직접 지정하면 오류로 알린다. 30분 지연 산출물은 입력 가용성 비교용이며 해당 지연 모델을 학습한 것은 아니다. 공간 구간 도형에는 위험점수를 임의로 채우지 않는다.

## 수정본 구간 추론 재현

아래 명령은 `outputs/private/releases/20261007`에서 실행한다. 원래 루트의 20260915 설정과 혼합하지 않는다. 선행 특징·모델 단계는 `config/notebook_workflow.json`에 등록되어 있다.

```powershell
python scripts/build_moisture_memory.py
python scripts/cache_point_sources.py
python scripts/audit_point_input_parity.py
python scripts/train_temperature_candidate.py
python scripts/train_ice_candidate.py
python scripts/build_segment_environment_inventory.py
python scripts/infer_segment_temperature.py
python scripts/audit_segment_inference.py
python scripts/export_segment_condition_maps.py
```

`infer_segment_temperature.py --limit 2`는 별도 smoke 경로만 사용한다. 전체 실행은 입력 서명이 같은 완료 구간을 재사용하며, 서명이 바뀌면 덮어쓰지 않고 중단한다. `invalid_route_*`는 검증 중 발견한 이전 오류 출력으로 사용 금지다. 새 위치 입력은 모든 과거 관측을 개발 지점으로만 제한한다. 경보 후보 파일은 최종 평가 전 상태다.

## 고정 평가와 제출 검토 초안

2026-10-08 `freeze_assessment.py` → `predict_frozen_holdout.py` → `evaluate_frozen_holdout.py`를 한 번 실행했다. 이미 보호 정답을 평가했으므로 세 명령은 기존 결과가 있으면 중단한다. 같은 지점에 새 모델을 맞춘 뒤 독립 검증이라고 보고하지 않는다. 결과 읽기와 실제 추론 데모는 다음과 같다.

```powershell
python scripts/check_notebook.py
python scripts/demo_inference.py
python scripts/build_demo_video.py
python scripts/refresh_manifests.py
python scripts/build_submission_draft.py
```

제출 초안 생성은 새 `outputs/private/submission_draft_v1` 폴더만 만들며 기존 폴더가 있으면 중단한다. 원본 ZIP·실행에 필요한 유효 캐시·외부 자료 이용 고지·모델·코드·노트북·그림·MP4·실제 실행 로그를 포함한다. 개인정보가 든 신청서·인증정보·Git 이력·무효 구간 출력은 포함하지 않는다. 초안 자체도 비공개 데이터이므로 외부 업로드하지 않았다. `submission_manifest.json`으로 파일별 SHA256을 확인할 수 있다. 새 복사본의 루트에서 데모와 노트북을 실행해 이식성을 검증한다.

결빙 탐지 실패와 미확정 공식 이정/방향, 제출 규격·참가자 직접 기여를 확인하기 전 제출 완료라고 간주하지 않는다.


## 비공개 이정 교차 검토 및 완료 감사 — 2026-10-09

수정본 작업 루트에서 아래를 실행한다. 비공개 `external/uos_chainage_reference/` 및 `external/official_cctv_anchors/`의 출처 기록과 파일이 필요하다. 공식 보호 정답이나 모델을 변경하지 않는다.

```powershell
python scripts/audit_chainage_reference.py
python scripts/plot_chainage_review.py
python scripts/audit_official_chainage_anchors.py
python scripts/audit_completion.py
python scripts/check_notebook.py
```

기하 통과, 공식 기준점 후보 일치, 공식 전체 도로 이정/방향 확인은 서로 다른 단계다. 현재 마지막 단계는 미완료다. 원자료와 파생물은 재배포 조건이 확인되기 전까지 제출 패키지에서 제외하며, 검증된 기존 v1 초안은 그대로 보존한다. 현재 실행 설정은 81단계·노트북 33개 코드 셀이고 위의 과거 단계 수는 각 기록 시점의 값이다.


## 단기 냉각 누적 개발 비교 — 2026-10-09

수정본 작업 루트에서 `python scripts/evaluate_antecedent_forward.py`를 실행한다. `physical_features/`와 기존 `forward_physics/` 결과가 필요하다. 원천 AWS·다른 지점의 과거 노면온도만 입력으로 쓰며 공간 제외 지점과 공식 보호 지점은 참조에서 차단한다. 첫 겨울 내부 OOF에서 임계값을 선택하고 다음 겨울 제외 지점과 동일 행으로 비교한다. 기존 고정 모델·제출 초안을 갱신하는 명령이 아니다. 설정과 runner 해시가 바뀌면 이전 결과 재사용을 거부한다. 워크플로 82단계·노트북 34개 코드 셀이다.


## 규제 모델 비교와 전체 재추론 감사 — 2026-10-09

수정본 작업 루트에서 다음을 실행한다. 기존고정모델·보호평가·제출 초안은 덮어쓰지 않는다.84개 등록 단계와 35개 노트북 코드 셀로 연결했다.

```powershell
python scripts/evaluate_regularized_forward.py
python scripts/audit_regularized_forward.py
python scripts/check_notebook.py
```

각 외부 지점 폴더에 내부OOF·임계값trace·다음 겨울예측·저장모델·표준화계수가 기록된다. 감사는 28개 모델을 재로딩하고 모든 검증 행의 입력을 다시 만들어 점수를 비교하며, 내부 임계값 선택과 공간·시간 분리도 확인한다. 저장 계수는 설명용 비교 자료이며 검증된 위험도 가중치로 사용하지 않는다.


## 과거 주변 노면상태 추가 비교 — 2026-10-09

수정본 작업 루트에서 다음을 실행한다. 기존 41개 열·수분 입력에 23개 과거 상태 입력을 추가하는 단일 후보이며 기존고정모델·보호평가·제출 초안은 유지한다. 실행 목록 86단계·노트북 36개 코드 셀에 연결했다.

```powershell
python scripts/evaluate_surface_state_forward.py
python scripts/audit_surface_state_forward.py
python scripts/check_notebook.py
```

현재 상태 입력은 같은 노선에서 자기·검증 제외·보호 지점 외의 가장 가까운 개발 지점을 참조하며 목표 시각보다 과거·30분 이내여야 한다.60/180분 상태 비율은 관측 커버리지 80%를 요구한다.결측·미정의 상태를 건조나 음성으로 채우지 않는다.14개 지점의 다음 겨울 제외 검증은 반복 연구한 개발 비교다.


고정 평균 비교: `python scripts/evaluate_surface_state_ensemble.py` → `python scripts/audit_surface_state_ensemble.py`. 현재 실행 목록 88단계·노트북 37개 코드 셀이다. 첫 겨울OOF의 대상 일치와 소스 격리를 확인한 뒤 0.5 산술/기하 평균을 비교한다. 출력은 수정본 비공개 폴더에만 저장된다.


교차 적합 추정온도 비교: `python scripts/evaluate_estimated_temperature_forward.py` → `python scripts/audit_estimated_temperature_forward.py`. 각 내부/외부 단계에서 온도 학습 지점의 정렬 3그룹을 고정하며 전처리도 해당 학습 그룹 안에서 적합한다.88단계 이후 추가한 2단계로 현재 90단계·노트북 38개 코드 셀이다. 기존 온도 혼합 60분과 다른 30분 참조 조건을 함께 기록한다.


추가 실행: `audit_kma_rwis_catalog.py`는 공식PDF의 정적 목록만 처리한다. 상태 의미 수정은 `evaluate_surface_state_v2_forward.py` → `audit_surface_state_v2_forward.py`, 결합 비교는 `evaluate_surface_state_v2_ensemble.py` → `audit_surface_state_v2_ensemble.py`이다. 현재 95단계·노트북 41개 코드 셀이다. KMA 관측자료 인증 설정명은KMA_AUTH_KEY이며 값을 로그·노트북·Git에 기록하지 않는다. 아직 관측 API 호출·추가 독립 평가를 수행하지 않았다.


## 외부 첫 겨울 관측 수집과 검증 — 2026-10-09

수정본 작업 루트에서 실행한다. 인증 파일은 원래 프로젝트 루트에 보존하며 수정본이나 패키지로 복사하지 않는다. `KMA_AUTH_KEY`가 실행 환경에 있으면 이를 읽고, 없으면 명시한 파일을 읽는다. 키 값은 인자·출력·기록에 쓰지 않는다.

```powershell
python scripts/download_kma_external_development.py --credentials-file "D:\프로젝트\icy-road-ai\secret.env"
python scripts/audit_kma_external_development.py
# 전체 첫 겨울 수집 및 감사가 완료된 뒤에만 학습용 입력을 생성한다.
python scripts/build_kma_external_development_features.py
# 부분 자료의 입력 연결 확인은 학습에 쓸 수 없는 별도 스냅샷으로만 만든다.
python scripts/build_kma_external_development_features.py --snapshot
```

`--start`, `--end`, `--stations`로 개발 기간 일부를 요청할 수 있다. 기본 12시간 구간, 최소 호출 간격 1.2초이며 완성된 캐시를 재사용한다. 범위는 사전 계획의 첫 겨울·9개 지점으로 한정한다. 다음 겨울과 기존 대회 지점 요청은 수집기가 거부한다. `summary.json`의 status가 `development_download_complete`여야 모델 개발용 특징 생성이 가능하다. 계속 수집 중인 파일을 검사할 때는 검사한 manifest 스냅샷을 별도로 남긴다.

현재 실행 목록 96단계·노트북 42개 코드 셀이다. 관측 확보·품질 감사·입력 연결은 완료 범위별로 표시하며 모델 성능 개선이나 추가 독립 평가 완료를 의미하지 않는다.


2026-10-09 수집 오류 대응 추가: 12시간 요청에서도 간헐적 504가 발생해 실패 구간만 자동 이분할하는 전송기를 추가했다. 첫 겨울 11월 8일 한 구간은 실제로 2개 짧은 요청으로 수집됐고, 각 원래 응답·SHA256·시각 경계와 결합 자료를 전수 대조했다. 완료된 108개 구간은 재사용했고 수집을 이어가고 있다. 최신 감사 스냅샷 144개 구간은 매분 103,680건, 정확한 10분 10,368건, 유효 상태 10,305건이며 미정의 63건과 Ice 0건이다. 아직 따뜻한 11월 초 자료이며 모델 개선은 평가 전이다. 단위 테스트 78개, 두 작업 공간의 실제 Jupyter 42개 셀, Python 154개 구문, 기존 고정 파일 47개 검증을 완료했다.

후속 342개 구간 감사에서는 시각 결측 2,635행을 원문에 보존하고 제외했으며 10분 24,361건·유효 상태 24,298건을 검증했다. 원본 CSV의 시각 공백은 파싱할 때만 제거한다. `0` 등 시각 결측을 행 순서로 채우지 않는다. 재시작 전 기존 수집 프로세스가 종료됐는지 확인하고, 실행 중인 프로세스와 같은 자료를 중복 수집하지 않는다.

수집 완료 전 준비 상태 확인과 전체 완료 후 후보 비교는 다음과 같다.

```powershell
python scripts/evaluate_external_augmentation.py --prepare-only
# 전체 첫 겨울 수집·감사·학습용 특징 생성 완료 후
python scripts/evaluate_external_augmentation.py
```

`config/external_augmentation_experiment.json`의 고정 후보를 4개 외부 공간 그룹에서 중첩 비교한다. 각 평가 그룹은 후보 선택에서도 제외하며 다른 3개 그룹에서FP·FN이 모두 감소해야 증강 후보를 선택한다. 임계값 보정은 첫 겨울 기존 14개 개발 지점만 사용한다. 전체 84개 테스트에 합성자료 실행 검증이 포함된다. 이후 추가한 온도·다음 겨울 평가 연결은 아래 절을 따른다.

## 외부 온도 후보 선택과 고정 다음 겨울 평가

수정본 루트에서 첫 겨울 전체 수집·감사·학습용 특징 생성이 끝난 뒤 다음 순서로 실행한다. 준비 상태 확인은 각 명령에 `--prepare-only`를 붙인다. 준비 확인은 API 요청·모델 학습·정답 읽기를 수행하지 않는다.

```powershell
python scripts/evaluate_external_augmentation.py
python scripts/evaluate_external_temperature.py
python scripts/predict_external_reserved.py
python scripts/download_kma_external_reserved.py --credentials-file "D:\프로젝트\icy-road-ai\secret.env"
python scripts/evaluate_external_reserved.py
```

온도 후보는 기존 14개 기상·시간 입력의Ridge α=100과 과거 60분 주변 온도 0.5 혼합이다. 각 평가 그룹을 제외하고 나머지 3개 그룹에서MAE·RMSE가 모두 개선되어야 보강 후보를 선택한다. 동적 참조는 기존 14개 개발 지점으로 한정하고 기상·수분 센서 가용성은 첫 겨울에 고정한다.

다음 겨울 예측은 9개 지점 전체 10분 격자로 먼저 저장한다. 학습 당시 코드·입력·모델 해시를 대조하고 `external_reserved_predictions_v1/predictions_receipt.json`에 고정한다. 기존 첫 겨울 수집기는 계속 다음 겨울 요청을 거부한다. 별도 다음 겨울 수집기는 이 영수증과 모든 해시가 맞아야 작동하며, 기존 대회 19개 지점은 요청하지 않는다. 첫 겨울 계획 파일을 다음 겨울 날짜로 수정하지 않는다.

평가는 모든 계획 구간이 수집된 뒤 한 번만 완료한다. 원문·전송 응답·10분 변환을 다시 대조하고 동일 유효 행에서 분류·온도·일별 커버리지를 보고한다. 평가 중단 후에는 동일한 예측·코드·자료로만 복구할 수 있다. 완료 결과에서 모델·임계값을 다시 선택하지 않는다. 이 외부 9개 지점 점수를 공식 3개 지점 점수로 표현하지 않는다. 현재는 코드와 합성 응답 연결만 검증했으며 실제 다음 겨울은 미개봉 상태다.

검증된 실제 성능·산출물·출처를 정리한 뒤 향후 새 검토 초안은 `python scripts/build_submission_draft.py --output outputs/private/submission_draft_v2`처럼 지정할 수 있다. 출력은 비공개 폴더의 새 `submission_*` 하위 폴더로 한정한다. 기존 폴더는 덮어쓰지 않으며 현재 생성은 수행하지 않았다. 참가자 확인 기록을 읽어 기여 확인 상태를 반영하되 최종 모델 선택·제출 검토와 구분한다. 수집 중 자료를 최종 재현 패키지로 확정하지 않는다.

## 추가 관측 표본 편중·상태/온도 진단

수정본에서 `python scripts/analyze_external_rwis_quality.py`를 실행한다. 먼저 `audit_kma_external_development.py`의 원문 감사가 필요하다. 입력·감사 manifest·첫 겨울 비교자료·실행 소스를 불변 스냅샷에 복사하고 지점별 커버리지, Ice 슬롯 수, 연속 관측 구간, 온도 분포를 저장한다. 같은 데이터·코드의 스냅샷이 있으면 덮어쓰지 않는다. 최신 결과의 위치와 해시는 `external_quality/latest.json`이며 등록 단계는 `external_rwis_quality`다. 노트북 43번째 코드 셀에서 표와 그림을 확인한다.

온도 진단·보강 학습의 대회 정답은 분류 특징 파일에 섞지 않고 `point_sources/rwis.parquet`의 허용된 14개 지점에서 지점·시각으로 따로 결합한다. 시각이 정확히 일치하지 않으면 결측으로 남긴다. 공식 04 양성·13/15 음성·0/-999 미정의 규칙을 유지한다. 온도에 따른 정답 삭제나 센서 오류 확정은 하지 않는다. 전체 첫 겨울 비교와 추가 자료의 같은 시각 집합 비교는 서로 다른 표본으로 명시한다.

추가 수집 대응: 서버 오류·읽기 시간 초과로 실패하면 15분 구간까지 이분할하고, 짧은 구간도 재시도 후 실패하면 종료한다. 종료 여부를 실제 프로세스 핸들로 확인한 뒤 같은 명령으로 완료 캐시를 재사용할 수 있다. 수집기·파서·전송기 소스 버전을 SHA256별로 자동 보존한다. 관측 시간이나 상태를 만들거나 실패 응답을 정상 자료로 기록하지 않는다.


</details>
