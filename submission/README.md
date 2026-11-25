# 최종 제출 실행 소스

2026년 11월 6일 제출한 모델자료에서 Python 코드·노트북·환경 명세 77개를 원본 바이트 그대로 보관했습니다. [소스 명세](source_manifest.json)의 파일별 SHA-256은 공개 사본을 검증하는 값입니다. `model_archive_sha256`은 제출 당시 전체 ZIP의 값입니다.

| 경로 | 역할 |
| --- | --- |
| [source/code/](source/code/) | 실제 학습·추론·지표 및 공간 근거 재현 진입점 |
| [source/src/](source/src/) | 실행 패키지의 모형·평가·계측 후보 선정 보조 모듈 |
| [source/notebooks/analysis.ipynb](source/notebooks/analysis.ipynb) | 최종 분석·추론·재집계 흐름, 코드 셀 12개 |
| [source/notebooks/training.ipynb](source/notebooks/training.ipynb) | 학습 흐름, 코드 셀 3개 |
| [source/weather/](source/weather/) | 기온·습도·풍속 실행과 재학습 코드 |
| [source/requirements.txt](source/requirements.txt) | 최종 기본 실행 환경 |

공개 노트북은 출력과 실행 번호를 비웠습니다. 코드의 학습·추론·집계 흐름을 읽을 수 있고, 저장소 루트에서는 [합성 자료 테스트](../README.md#프로젝트-실행)를 실행할 수 있습니다.

11월 25일 로컬 최종 모델자료 ZIP을 관측·학습 표 23개를 제외한 정리본으로 교체했습니다. 나머지 기존 파일 323개는 원래 바이트와 대조했고 보존 안내를 추가했습니다. 원자료가 필요한 전체 학습·검산은 이 사본으로 재실행할 수 없습니다. 문서자료 ZIP은 제출 영수증의 해시와 일치합니다.

[최종 보고서 원고](../docs/delivery/FINAL_ANALYSIS_REPORT.md) · [결과 읽는 순서](../docs/START_HERE.md) · [공유 범위](../.github/PUBLICATION.md)
