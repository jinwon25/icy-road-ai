# 최종 제출 실행 소스

최종 모델자료 ZIP에 들어 있는 Python 코드·Notebook·환경 명세 77개 파일을 원본과 같은 바이트로 보관한다. 연구용 스크립트와 구별해 실제 실행 패키지의 코드를 검토하기 위한 사본이다. 파일별 SHA-256과 원본 모델자료 ZIP의 SHA-256은 [소스 명세](source_manifest.json)에 기록했다.

| 경로 | 역할 |
| --- | --- |
| [source/code/](source/code/) | 실제 학습·추론·지표 및 공간 근거 재현 진입점 |
| [source/src/](source/src/) | 실행 패키지의 모형·평가·계측 후보 선정 보조 모듈 |
| [source/notebooks/analysis.ipynb](source/notebooks/analysis.ipynb) | 최종 분석·추론·재집계 흐름, 코드 셀 12개 |
| [source/notebooks/training.ipynb](source/notebooks/training.ipynb) | 학습 흐름, 코드 셀 3개 |
| [source/weather/](source/weather/) | 기온·습도·풍속 실행과 재학습 코드 |
| [source/requirements.txt](source/requirements.txt) | 최종 기본 실행 환경 |

Notebook의 출력과 실행 번호는 비어 있다. 원자료·학습된 모형·행 단위 결과·데이터가 포함된 데모와 PDF·영상·ZIP·인증정보는 이 사본에 넣지 않았다. 전체 실행에는 참가 권한이 있는 로컬 제출본의 자료와 모형이 필요하다.

로컬 완성물은 `outputs/private/competition_submission/icy_road_model/`에 있다. 그 폴더의 `README.md`에 설치·학습·추론 명령을 제공한다. 이 소스 사본을 추가하는 과정에서 제출 ZIP·모형·예측값은 변경하지 않았다. 생성·편집 단계의 연구 코드는 루트 `src/`, `scripts/`, `config/`에서 확인할 수 있다.

[최종 보고서 원고](../docs/delivery/FINAL_ANALYSIS_REPORT.md) · [결과 읽는 순서](../docs/START_HERE.md) · [공유 범위](../.github/PUBLICATION.md)
