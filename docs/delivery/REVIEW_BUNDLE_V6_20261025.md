# v6 검토 묶음: 핵심 요약과 한 번에 실행하는 검사

v6는 **온도 v3·결빙 v2 모델을 유지하면서 결과를 이해하고 재현하는 경로를 보완한 비공개 묶음**입니다. 기존 v5 ZIP은 보존하고 새 폴더·ZIP을 만듭니다. 모델 성능 개선이나 대회 접수 완료를 뜻하지 않습니다.

[현재 상태](../STATUS.md) · [처음 읽는 안내](../START_HERE.md) · [최신 연구와 출처](../research/RESIDUAL_AND_INFORMATION_20261025.md) · [CSV 규약](CSV_CONTRACT.md)

## 처음 검토하는 순서

1. 묶음 루트 `README.md`에서 범위와 실행 조건을 확인합니다.
2. `reports/review_brief_v6.pdf`의 2쪽에서 현재 성과·미채택 이유·자료 한계·검사 명령을 확인합니다.
3. 현재 상태와 최신 연구를 읽고, 필요하면 이전 8쪽 보고서의 모델 개발 근거로 이동합니다.
4. 아래 명령으로 파일이 바뀌지 않았는지, 포함 예측과 실행 결과가 같은지 확인합니다.
5. `demo/review/index.html`과 CSV에서 1,266개 구간의 추정 결과·입력 가용 범위를 탐색합니다.

지도는 기상 조건과 모델 추정의 탐색 도구입니다. 검증된 사고 확률·현장 운영용 위험등급이 아닙니다. 결측 NA는 비결빙과 구별합니다.

## 무엇을 추가하고 보존했는가

| 구분 | 내용 |
| --- | --- |
| 새 검토 자료 | 2쪽 PDF, 최신 잔차·시간 보정·입력 정보량 연구, 원문 이상 진단과 새 4지역 평가 문서 |
| 새 검사 도구 | `scripts/review_submission_bundle.py`: 전체 파일 크기·SHA-256·경로·예상 밖 파일 검사와 선택적 실행 확인 |
| 최신 근거 | `research/latest/`의 계획·요약·선택·감사 기록, 22:58 KST 공식 확인 요약, XGBoost 3.0.1 라이선스 |
| 그대로 보존 | 기존 모델·입력·전체 예측·CSV·그림·실행 코드·8쪽 보고서·노트북·데모·기존 라이선스 |
| 이전 기록 | `README_v5.md`, `AI_USAGE_v5.md`, `provenance/v5_manifest.json`, 이전 ZIP 영수증 |
| 작업 공간에 남는 것 | 전체 연구 원자료·미채택 모델·전량 연구 점수·인증정보. ZIP이나 GitHub에 추가하지 않음 |

추가 연구는 안정적 성능 개선을 통과하지 못했습니다. 사후 최고 F1 상승만으로 모델을 교체하지 않았고, 연구용 XGBoost는 제출 추론 의존성에 추가하지 않았습니다. 앞선 새 4지역 평가도 사건 손실·관측 품질 조건에 실패했습니다.

## 실제 실행 방법

Python 3.11 환경에서 ZIP을 새 폴더에 풀고 그 폴더를 작업 위치로 사용합니다. 포함 의존성을 설치하는 데는 패키지 접근이 필요합니다. 설치 이후 아래 추론과 예제 노트북은 포함 자료를 사용합니다.

```powershell
python -m pip install -r requirements-notebook.txt
python scripts/review_submission_bundle.py
python scripts/review_submission_bundle.py --smoke --output local_review/smoke.json
```

첫 명령의 기본 결과는 `local_review/verification.json`입니다. 같은 결과 파일을 덮어쓰지 않으므로 재검사할 때 `--output local_review/새이름.json`을 지정합니다. `local_review/`는 사용자 실행 결과를 위한 폴더로 원래 manifest에 포함하지 않습니다.

`--smoke`는 명령줄 예측 144행을 생성하고 포함 기준 예측과 모든 열을 비교한 뒤, 실제 노트북의 5개 코드 셀을 실행합니다. 실행 로그와 실패 원인도 `local_review/`에 남깁니다. 파일 무결성은 실행 전후에 확인합니다. 경로 이탈·심볼릭 링크·변조·예상 밖 파일은 실패로 처리합니다.

이 검사는 포함 추론과 예제 노트북의 재현 확인입니다. 공식 보호 지점 정답을 새로 열거나 미채택 연구 모델을 다시 선택하지 않습니다. ZIP 안에 모든 연구 입력을 넣지는 않았으므로 모든 연구 스크립트의 완전 재학습을 보장하는 명령도 아닙니다.

## 검증 근거와 한계

전체 합성 테스트 388개·하위 검사 7개가 통과했습니다. 새 테스트는 잔차 시작값·미래 관측 변경 불변성·시간 단절·지점 분리·입력 중복의 작은 전수 비교·묶음 변조와 경로 이탈을 다룹니다. 기존 pandas의 자료형 경고 1건은 실패와 구별해 로그에 보존합니다.

새 PDF는 두 페이지를 렌더링해 실제 글자·표·여백·페이지 수를 확인했습니다. PDF 생성 입력의 해시와 검수 기록을 `validation/v6_brief_source.json`, `validation/v6_brief_visual.json`에 넣습니다. 기존 보고서를 덮어쓰지 않습니다.

첫 패키지 검증은 제한된 실행 환경에서 노트북 커널 연결이 진행되지 않아 중단했습니다. 로컬 Jupyter 통신이 가능한 환경에서 같은 노트북의 5개 코드 셀이 통과했고, 파일별 재시도 이름을 사용해 전체 검증을 다시 수행했습니다. 이전 예측·로그는 덮어쓰지 않습니다. 최종 예측·노트북 로그와 환경별 시도 기록은 `validation/v6_prediction.log`, `validation/v6_notebook.log`, `validation/v6_execution_environment.json`으로 포함합니다.

묶음 검증은 v5에서 보존할 파일 전부의 해시를 대조하고, Markdown의 표·내부 링크, 새 검사 명령의 예측·노트북 실행, 이전 보호 봉인 47+549개와 새 4지역 평가의 보존을 확인합니다. 상세 결과는 묶음의 `validation/v6_delivery.json`, ZIP 전체 파일 대조는 옆의 `.receipt.json`에 기록합니다. 파일 목록과 각 해시는 ZIP 내부 `manifest.json`에서 확인합니다. 해시는 파일의 변경 여부를 확인하는 수단이며 외부 전자서명은 아닙니다.

v6의 코드·문서는 Git 인덱스의 스냅샷을 사용합니다. 기존 사용자 미커밋 수정·로그는 보존하고 이 묶음에 섞지 않습니다. `provenance/source_index_snapshot.json`은 실제 포함 파일의 해시를 기록하며 커밋 전 스냅샷을 커밋 SHA라고 표현하지 않습니다.

| 로컬 경로 | 내용 |
| --- | --- |
| `outputs/private/submission_candidate_20261025_v6/` | 실행·검수한 묶음 폴더 |
| `outputs/private/submission_candidate_20261025_v6.zip` | 같은 manifest로 파일 전체를 대조한 ZIP |
| `outputs/private/submission_candidate_20261025_v6.receipt.json` | ZIP SHA-256·크기·파일 수·확인 시각 |
| `outputs/private/submission_review_v6_20261025/` | PDF 생성 원본·페이지 PNG·시각 검수 기록 |

이 경로는 로컬 전용입니다. GitHub에서 저장소만 내려받으면 원자료·모델·ZIP이 생기지 않습니다. 제공 자료의 승인받지 않은 제3자 열람·배포를 허용하지 않으며, 결과물 제출 날짜·경로는 [최신 공식 공지 확인](../competition/OFFICIAL_UPDATE_20261025.md)의 미확정 상태를 유지합니다.
