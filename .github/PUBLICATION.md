# 저장소 공유 범위

`jinwon25/icy-road-ai`는 2026 DATA·AI 분석 경진대회 전북 고속도로 결빙 과제의 연구 코드 저장소다. 결과물 제출(2026년 11월 6일 마감)과 발표 평가 대상 발표(11월 18일)가 끝난 뒤인 2026년 11월 21일에 공개 전환을 위해 규정과 저장소 내용을 다시 검토했다.

[프로젝트 소개](../README.md) · [문서 안내](../docs/README.md) · [최신 공식 기준 대조](../docs/competition/OFFICIAL_RULES_AND_RUBRIC_20261106.md)

## 반영하는 자료

코드·설정·출력과 실행 번호가 없는 Notebook·집계 문서·집계 도표만 반영한다. 원자료·행 단위 파생자료·예측·학습된 모형·참가 신청서·인증정보·제출 ZIP은 넣지 않는다. 제출 PDF·데모·실행 자료는 로컬 `outputs/private/competition_submission/`에서 관리했다.

## 2026년 11월 21일 공개 전 검토

| 항목 | 확인 결과 |
| --- | --- |
| 대회 진행 | [개최 공지](https://aida.kisti.re.kr/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId=523)의 대회 기간은 2026년 8월 11일–11월 25일이다. [발표 평가 공지](https://aida.kisti.re.kr/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId=822)의 이 과제 발표 대상 3팀에 로드투인사이트는 포함되지 않았다. |
| 참가 서약 | 승인받지 않은 제3자에게 제공 데이터를 열람·제공하지 않고 대회 완료 후 폐기한다. 수상작 공개 협조 조항은 수상하지 않은 이 저장소에 적용되지 않는다. 심사 점수 비공개 조항에 따라 공식 점수를 적지 않았다. |
| 결과물 제출 공지 | [공지 564](https://aida.kisti.re.kr/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId=564)는 개인정보·API Key 등의 제외와 외부 자료 이용조건 확인을 요구한다. 결과물 공개를 금지하는 문구는 없다. |
| 현재 파일 | 추적 파일 1,302개에 원자료·모형 형식(CSV·Parquet·ZIP·pickle 등)이 없고 Notebook 15개의 출력이 모두 비어 있다. 로컬 인증키 문자열, 로컬 사용자 경로, 전화번호·개인 메일 형식은 검출되지 않았다. |
| Git 이력 | 커밋 22개에서 추가된 파일 1,348개의 확장자는 py·md·json·png·ipynb·txt·html 등이다. 이력 전체에서 로컬 인증키 문자열이 검출되지 않았다. |
| 도표 | 지점별 관측·추정 노면온도 밀도도, 날짜별 결빙 달력 등 집계 그림이다. 원래 관측 행을 복원할 수 있는 표는 넣지 않았다. |

코드 제출 의무와 공개 허용은 같은 뜻이 아니다. 규정상 공개를 금지하는 조항은 확인되지 않았고 보호 대상인 제공 데이터는 포함하지 않았다. 다만 대회 기간이 11월 25일까지이므로 발표 평가가 끝난 뒤 공개하는 편이 가장 보수적이다.

## 로컬 자료 폐기

참가 서약에 따라 대회 완료 후 로컬의 제공 데이터 ZIP 2개와 `outputs/private/`의 원자료·파생자료를 폐기한다. 폐기 전에 남길 집계 결과와 제출 기록을 확인한다. 이 문서 작성 과정에서는 삭제하지 않았다.
