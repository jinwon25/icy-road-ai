# 기준선 비교와 제출 후보 재현성 보완

> **읽는 범위:** 아래 내용은 해당 문서의 작성·실험 시점 기록입니다. 현재 모델·마감·완료 상태는 [진행 현황](../STATUS.md)을 기준으로 읽고, 약어와 지표는 [처음 읽는 안내](../START_HERE.md)에서 확인합니다.

현재 후보는 단순 기준선보다 일별 F1이 낮습니다. 온도 오차 개선과 결빙 성능을 구별하고, 누락된 비교와 저장소·모델 카드·패키징의 오류를 수정했습니다. 실행 모델은 검증 자료로 보존하며 성능 적합 판정과 미사용 지점의 독립 검증은 남아 있습니다.

[현재 현황](../STATUS.md) · [공식 사이트 확인](../competition/OFFICIAL_UPDATE_20261016.md) · [이전 보고서](MODEL_REPORT_UPGRADE_20261014.md)

## 단순 기준선과 같은 규약으로 비교

허용된 첫 겨울 개발 9곳의 기존 공간 제외 예측을 사용했습니다. 새 학습·임계값 탐색·보호 및 이미 개봉한 평가 정답 재열람은 수행하지 않았습니다.

| 방법 | 일별 지점 평균 F1 | F1 날짜/유효 지점 | FP | FN |
| --- | --- | --- | --- | --- |
| 현재 온도·수분 후보 | 0.030633 | 365/9 | 20,255 | 4,952 |
| 이전 온도 3종·수분 | 0.030231 | 380/9 | 20,889 | 4,982 |
| 항상 비결빙 | 0.000000 | 124/8 | 0 | 6,611 |
| 항상 결빙 | 0.055216 | 1,060/9 | 148,507 | 0 |
| ASOS 기온 ≤0°C | 0.071122 | 786/9 | 57,912 | 811 |
| 추정 노면온도 ≤0°C | 0.063867 | 707/9 | 44,682 | 2,280 |

일별 지표는 144개 유효 관측이 있는 1,060개 지점일에서 날짜 평균 후 지점 평균을 구합니다. 예정 지점일은 1,080개입니다. FP/FN은 부분 날짜를 포함한 유효 상태 155,118행의 합계입니다. 실제·예측 결빙이 모두 없는 날은 F1 평균에서 제외되어 방법별 날짜 분모가 달라집니다. 항상 비결빙의 F1은 유효 8개 지점의 평균이며 9개 전체 평균은 미정의입니다.

단순 기온 규칙의 입력 부족은 기존 고정 개발 판정과 같은 0 관례를 사용했습니다. 부족 21행은 모두 비결빙 라벨이며 제출 추론은 계속 null을 출력합니다. 정식 지표와 별도로 같은 관측일의 양쪽 무결빙 F1을 0으로 두는 민감도도 저장했고, 공식 정책을 바꿔 순위를 선택하지 않았습니다.

144·130·72·1 관측량 조건의 24개 보고서, 일별 25,920행과 지점 216행을 별도 NumPy 참조 계산으로 검산했습니다. 결과는 `outputs/private/baseline_benchmark_20261016_v1/`에 있습니다. ASOS 규칙은 F1과 FN에서 유리하지만 FP가 현재 후보의 약 2.86배여서 자동 승격하지 않았습니다.

## 지점 편중과 판단 범위

Ice 6,611행 중 6,340행(95.9%)이 33408에 있습니다. 현재 후보의 시점 합산 Recall은 25.1%, 해당 지점을 제외한 271개 양성의 Recall은 97.8%입니다. 제외 후 Precision은 1.39%여서 오경보 문제는 남습니다. 지점 제외나 라벨 삭제로 성능을 개선하지 않습니다.

현재 후보와 항상 결빙의 시점별 선형 비용이 같은 미탐/오경보 비용 비율은 약 25.90입니다. 경보 묶음·제설 비용을 측정한 값이 아니므로 운영 기준으로 사용하지 않습니다. 센서 범위·제설·염분·유지보수 이력 확인과 새 지점의 고정 평가가 필요합니다.

## 재현 경로의 수정

| 문제 | 수정·확인 |
| --- | --- |
| 저장소 CLI의 기본 CSV 파서 | `read_weather`로 통일해 `float_precision='round_trip'` 적용. 저장소 CSV·ZIP CSV·Parquet의 실제 144행과 기존 기대 예측이 정확히 일치 |
| 모델 카드 MAE 명칭 | 전체 행 `1.2005309458295894`, 지점 균등 `1.2004399738726252`를 포함 예측에서 계산. 생성 코드와 새 카드에 두 필드·집계 정의 기록 |
| 과거 데모를 현재 후보로 소개 | 현재 2모델 평균은 `python -m src.submission_runtime`으로 안내. `demo_inference.py`는 과거 Ridge·HGB 기준선으로 표시 |
| 삭제된 해제 폴더 의존 | 보존 ZIP의 외부 SHA-256·내부 파일 해시를 검증해 새 폴더로 복원. 중복 멤버·경로 탈출·변조·덮어쓰기 거부 |
| 입력 ID·시각 검증 빈틈 | `12207`·`12207.0` 정규화 후 중복 확인. 기상 관측 나이 0 이하와 10분 경계의 나노초 편차 거부 |

모델 카드의 Recall 지점 평균과 시점 합산 Recall도 구별합니다. 기존 `0.774688`은 유효 지점의 일별 Recall 평균이며 전체 시점 Recall `0.250945`와 다른 값입니다.

새 후보는 `outputs/private/submission_candidate_20261016_v1.zip`입니다. 이전 ZIP은 그대로 보존하고 925개 해시를 확인한 뒤 복원했습니다. 새 후보의 실행 모델·전체 `data/`·가중 연구 자료 355개 파일은 이전 해시와 같습니다. 모델 카드에는 기준선과 `performance_qualified=false`를 추가했습니다.

보고서는 앞 4쪽에 최신 비교·편중·재현성 정정을 놓고 기존 12쪽 분석 원문을 이어 보존한 16쪽 구성입니다. 기존 연구의 조건과 당시 쪽번호를 유지합니다. 편집 원고와 전체 검산 코드도 묶었습니다.

## 실행과 다음 판단

```powershell
python -m src.submission_archive --archive outputs/private/submission_candidate_20261016_v1.zip --output outputs/private/candidate_work_20261016
python -m src.submission_runtime --input outputs/private/candidate_work_20261016/data/weather_example.csv --models outputs/private/candidate_work_20261016/model --output outputs/private/new_candidate_prediction.csv
```

원본 작업 공간에서 새 후보를 만들 때는 다음 순서를 따릅니다. 각 단계는 기존 결과가 있으면 중단합니다. PDF 생성 후 페이지를 렌더링해 검토한 기록이 있어야 최종 묶음 생성이 가능합니다.

```powershell
python scripts/repair_submission_candidate_20261016.py --stage prepare
python scripts/build_review_report_20261016.py
python scripts/repair_submission_candidate_20261016.py --stage finalize
```

이 명령은 보존된 10월 14일 ZIP과 로컬 연구 자료를 사용합니다. 제출 ZIP 내부의 `code/reproduce_baselines.py --output validation/new_baselines.json`은 포함 자료만으로 24개 비교 보고서를 접속 없이 재현합니다. 원본 자료·모델·예측·PDF·제출 ZIP은 Git에 올리지 않습니다.

후속 모델은 먼저 단순 기준선과 같은 지표·분모에서 비교하고 FP/FN·지점 손실·기존 사건을 함께 확인해야 합니다. 이미 개봉한 정답으로 계속 선택하기보다 후보·기준을 고정한 다음 미사용 적격 지점에서 한 번 평가하는 것이 다음 검증입니다.

## 적용한 문헌

- [Lipton·Elkan·Narayanaswamy, 2014](https://arxiv.org/abs/1402.1892): 정보 없는 분류기의 F1 최적화가 전부 양성을 택할 수 있다는 이론적 사례. 이번 날짜·지점 집계 순위의 직접 증명은 아닙니다.
- [Reinke 등, 2024](https://www.nature.com/articles/s41592-023-02150-0): 집계 단위·분모·빈 집단의 함정을 점검해 지점별 결과와 날짜 분모를 함께 표시했습니다.
- [Saito·Rehmsmeier, 2015](https://doi.org/10.1371/journal.pone.0118432): 불균형 자료의 Precision/Recall 해석을 참고했습니다. 해당 논문의 ROC 비교를 이번 고정 판정의 성능 입증으로 사용하지 않았습니다.
- [scikit-learn 1.6.1 DummyClassifier](https://scikit-learn.org/1.6/modules/generated/sklearn.dummy.DummyClassifier.html): 입력을 사용하지 않는 상수 기준선을 비교에 포함했습니다.
- [pandas 2.2.3 read_csv](https://pandas.pydata.org/pandas-docs/version/2.2.3/reference/api/pandas.read_csv.html): 무손실 부동소수점 파서를 저장소와 제출 경로에 통일했습니다.

5개 원문 응답은 모두 HTTP 200으로 확인해 `outputs/private/baseline_references_20261016_v1/`에 보존했습니다.
