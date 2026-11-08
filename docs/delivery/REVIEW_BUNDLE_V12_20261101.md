# v12 검토 묶음과 재현 범위

풍속의 추가 개선·관측망 입력 점검·24쪽 보고서를 v11 보존 위에 통합한 비공개 로컬 묶음입니다. [현재 원고](ANALYSIS_REPORT_V12_20261101.md) · [풍속 실행](WIND_NETWORK_20261101.md) · [설계·수치·출처](../research/WEATHER_NETWORK_20261101.md)

## 현재 진입점

`outputs/private/submission_candidate_20261101_v12`와 `outputs/private/submission_channels_20261101_v12/submission_receipt.json`을 기준으로 확인합니다. 문서자료·모델자료 ZIP은 각각 한 개 최상위 폴더로 압축하며 실제 대회 업로드 완료본과 구별합니다.

24쪽 보고서는 최신 풍속 수치로 초록을 갱신하고, 기존 2–22쪽 21개를 픽셀 수준으로 보존하며 13·14장 두 쪽을 추가했습니다. 기존 보고서·실행 자산·모형·예측·지도는 덮어쓰지 않습니다. 기본 진입 노트북은 기존 5코드셀의 `notebooks/submission_review_v11.ipynb`이며, 최신 비교·감사·입력 화면은 `notebooks/weather_network_review_20261101.ipynb`의 3코드셀에서 확인합니다.

새 풍속은 `research/wind_network_supplement`에서 CLI·전체 재학습을 별도로 실행합니다. 기존 기온·습도·노면온도·결빙과 843구간 지도는 보존합니다. 기존 지도 풍속을 새 모형의 결과라고 표시하지 않습니다. 입력 관측망 화면은 `research/latest/weather_network_viewer_20261101_v2/index.html`이며, 앞선 843구간 화면도 함께 포함합니다.

## 검증 기록

- `validation/v12_delivery.json`: 기본 144행·5셀, 새 3셀, 복사된 풍속 CLI 432행, 복사 화면 1,840조합·다운로드·모바일과 보존 해시의 실제 상태.
- `validation/wind_network_full_refit.json`: 별도 위치 API·CLI·전체 447,628행 재학습의 예측 432행 일치.
- `research/latest/weather_network_20261101_v1`: 계획·36분할과 특성 27,809,075개·예측 1,650,312개·지표 1,464건·대표 6재학습의 독립 검산.
- `research/latest/weather_network_viewer_qa_20261101_v3`: 원천 1,472행·표시값 12,880개·1,840조합, 외부 요청·JavaScript 오류 0건, 390px 시각 검토.

모든 연구 원문·36개 모형·전체 10분 공간 캐시를 포함하지는 않았습니다. 원천 재구축과 모든 탐색 재학습은 원 비공개 작업 공간이 필요합니다. 기본 추론과 최종 풍속 전체 재학습은 포함 자료로 실행합니다. 보호 정답·인증정보를 포함하지 않으며, 원자료·모형·예측·ZIP은 비공개 GitHub에도 올리지 않습니다.

## 해석

풍속은 반복 개발 4지역의 평가이며 새로운 독립 성능이나 공식 성적이 아닙니다. 기상 정확도 개선과 결빙 성능을 구별합니다. 기존 v2 결빙 F1은 기온 기준선보다 낮고 센서·제설 이력과 공식 마감 상세 확인은 남아 있습니다. 사용자 제공 11월 6일을 작업 마감으로 적용합니다. AI의 실행·시각 검토를 참가자의 수동 확인으로 기재하지 않습니다.
