# 공식 자료·선행연구 목록

같은 날 후속으로 [미탐 원인에 맞춘 추가 관측·제설 자료·모델링 근거](ADDITIONAL_ICING_SOURCES_20261025.md)를 검토했습니다. RoadSurf·형태 제한 HGB·날짜별 학습 비중은 실제 비교에 연결했고, 제설·재분석·RSCD는 원천 조건과 미확보 범위를 구분했습니다. [50모델 비교 결과](ICING_GAP_AND_SYNOPTIC_20261025.md)에서 실제 효과를 확인합니다.

10월 25일에는 [결빙 상태 전이·임계값의 논문과 공개 구현](ICING_REFERENCES_20261025.md)을 추가 검토했습니다. 공식 규정의 현재 기준은 [최신 원문 대조](../competition/OFFICIAL_UPDATE_20261025.md)입니다. 아래 목록은 주제별·시기별 근거를 보존합니다.

10월 24일 추가 검토: [최신 공개 논문·코드·가중치의 적용과 대회 조건](OPEN_SOURCE_REVIEW_20261024.md). 자료별 실제 열람 범위·라이선스 확인·적용 및 보류 근거를 구분합니다.

공식 규격·관측 정의·모델·공간 처리의 근거를 정리합니다. 각 출처의 실제 적용과 한계를 함께 표시하며 문헌의 성능·계수를 이 프로젝트의 결과로 옮기지 않습니다.

[문서 목록](../README.md) · [최신 평균·새 호남 검증](TEMPERATURE_MEAN_AND_BLIND_REVIEW_20261010.md) · [거리·기상망 검토](WEATHER_DISTANCE_AND_NETWORK_REVIEW_20261010.md)

## 단순 기준선과 집계·CSV 재현성 — 2026-10-16

[기준선·재현성 검토](../delivery/REVIEW_RESPONSE_20261016.md)에 다음 1차 자료를 적용했습니다. 원문 응답 5개를 보존했고 날짜·지점 평균에 관한 일반 논의와 이번 고정 개발 결과를 구별했습니다.

| 자료 | 실제 적용 |
| --- | --- |
| [Lipton 등, 2014](https://arxiv.org/abs/1402.1892) | 정보 없는 분류기에서 전부 양성 예측이 F1 최적이 될 수 있다는 이론적 사례. 이번 집계 순위의 직접 증명으로 확대하지 않음 |
| [Reinke 등, Nature Methods 2024](https://www.nature.com/articles/s41592-023-02150-0) | 날짜·지점·시점 집계와 미정의 분모를 함께 표시 |
| [Saito·Rehmsmeier, PLOS ONE 2015](https://doi.org/10.1371/journal.pone.0118432) | 불균형 자료에서 Precision·Recall·혼동행렬을 함께 검토 |
| [scikit-learn 1.6.1 DummyClassifier](https://scikit-learn.org/1.6/modules/generated/sklearn.dummy.DummyClassifier.html) | 입력을 무시하는 상수 기준선의 명시적 비교 |
| [pandas 2.2.3 read_csv](https://pandas.pydata.org/pandas-docs/version/2.2.3/reference/api/pandas.read_csv.html) | round_trip 파서와 실제 분기 경계 회귀 검증 |

## 결빙점 가중 학습과 보고서 개편 — 2026-10-14

[새 모델·보고서 검토](../delivery/MODEL_REPORT_UPGRADE_20261014.md)에서 다음 자료의 적용 조건과 실제 결과를 정리했습니다.

| 자료 | 적용 |
| --- | --- |
| [도로온도 XGBoost 보정, 2026](https://doi.org/10.1175/JAMC-D-25-0189.1) | 결빙점 부근 가중 학습의 동기. 자체 고정 가중식으로 공간 제외 실험 |
| [Ma 등 국내 LSTM, 2026](https://doi.org/10.3390/app16199487) | 과거 노면온도가 필요한 지점별 예측과 현재 미관측 위치 추정의 입력 차이 |
| [Li 등 LSTM·스태킹, 2026](https://doi.org/10.5194/gmd-19-9035-2026) | OOF 결합과 시간 이력의 조건, 주변 구간으로의 전이 한계 |
| [RoadSurf 1.1, 2024](https://doi.org/10.5194/gmd-17-4837-2024) | 열·수분 저장량과 현지 도로 물성의 필요성 |
| [SURFEX-TEB 교통 영향, 2025](https://doi.org/10.5194/gmd-18-9945-2025) | 교통의 열·복사·난류 경로. 관측 없이 계수를 적용하지 않음 |
| [scores 블록 재표집](https://scores.readthedocs.io/en/stable/tutorials/Block_Bootstrapping.html) | 날짜의 연속성과 여러 지점의 동시 기상 상관을 고려한 민감도 |
| [FHWA 겨울 도로 운영 지침](https://www.fhwa.dot.gov/publications/research/safety/95202/002.cfm) | 기상·노면·순찰·처리 이력을 함께 확인하는 운영 판단 |

공식 문제·Q&A·제출 공지·참가 서약도 다시 확인했습니다. 출판사 HTTP 403 및 대체 열람 범위는 `outputs/private/report_references_20261014_v1/review_receipt.json`에 기록했습니다. 직접 열지 못한 전문을 읽은 것으로 표시하지 않았습니다.

## 새 Q&A633와 일별 분모 확인 — 2026-10-13

[633의 새 댓글](https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=633)은10월13일 답변입니다. 미탐일Precision은 평균에서 제외하고 Recall·F1은0으로 반영합니다. [556의 지점별 평균](https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=556), [555의 무결빙·무예측 제외](https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=555)와 함께 적용했습니다.39공개 응답·비교·원문 해시는 `official_updates_20261013_v2/`이며 이전 스냅샷을 보존합니다.

[일반524](https://aida.kisti.re.kr/competition/main/selectQna.do?bbsId=BBSMSTR_BBBBBBBBBBBB&nttId=524)의11월25일 발표·시상은 세부 추후 안내를 전제로 한 계획입니다. [일반547](https://aida.kisti.re.kr/competition/main/selectQna.do?bbsId=BBSMSTR_BBBBBBBBBBBB&nttId=547)의 보고서·발표자료 안내는 다른 어선 문제 질문이므로 그 결과 열·확장 구현을 결빙 규격으로 옮기지 않습니다. [후속 계산·분모·미정 항목](../competition/OFFICIAL_QNA_20261013.md)을 같이 확인합니다.

## 기상 이력 온도·공간 오차 범위 후속 연구 — 2026-10-13

[새 보고서](WEATHER_MEMORY_REVIEW_20261013.md)는 각 방법의 실제 적용·평가 결과와 조건 차이를 정리합니다. 공개 원문·PDF5개·시각·해시는 `outputs/private/weather_memory_references_20261013_v1/`에 보존합니다.

| 일차 문헌 | 적용과 한계 |
| --- | --- |
| [Li 등2026, LSTM·스태킹](https://gmd.copernicus.org/articles/19/9035/2026/) | 다시간 열 이력·OOF 결합 검토. 과거 대상RST와 미래 시간 예보를 이번 미관측 도로 상태 추정에 그대로 적용하지 않음 |
| [Jiang·Xie2026, LSCP](https://proceedings.mlr.press/v306/jiang26at.html) | 공간 이질성과 지점별 포함률 검토. 논문 방법·교환가능성·mixing 가정 재현을 주장하지 않음 |
| [Tibshirani 등2019](https://arxiv.org/abs/1904.06019) | 밀도비·공변량 이동 조건이 없는 단순 가중 경험범위의 보장 한계 |
| [Gneiting·Raftery2007](https://sites.stat.washington.edu/raftery/Research/PDF/Gneiting2007jasa.pdf) | 식43의 interval score로 폭과 범위 밖 오차를 함께 평가 |
| [Cawley·Talbot2010](https://jmlr.org/papers/v11/cawley10a.html), [HGB 공식1.6](https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html) | 반복 개발·내부 선택·고정 후보 구별과 동일 HGB300 조건의 MSE/MAE 비교 |

익명10건 중9건200, METRo 출판사 원문403을 기록했습니다. 실패 응답을 읽은 논문으로 계산식에 사용하지 않았습니다. 공식 목록·제출564·633 재조회는 새 마감 날짜나 답변을 확인하지 못한 상태입니다.

## 공식 사이트 추가 정보 — 2026-10-13

[최신 대조](../competition/OFFICIAL_UPDATE_20261013.md)의 근거는 공식 공개 응답27건·내장 이미지10개·이전/신규 HWP 본문입니다. 원문·시각·해시는 `outputs/private/official_updates_20261013_v1/`에 보존합니다.

| 공식 출처 | 실제 확인 | 반영·한계 |
| --- | --- | --- |
| [FAQ639](https://aida.kisti.re.kr/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId=639) | 10월12일 새 공지. 자필서명·제안서·로그인·신청 처리·팀원·제출 안내 | 다른 문제의 화면 예시를 해당 결빙 CSV 규격으로 이식하지 않음 |
| [제출 준비564](https://aida.kisti.re.kr/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId=564), [일반632](https://aida.kisti.re.kr/competition/main/selectQna.do?bbsId=BBSMSTR_BBBBBBBBBBBB&nttId=632) | 준비 안내·접수 전·추후 일정 공지·23:59 한국 시간 | 참가신청 종료11월6일과 결과물 제출 마감 날짜를 구별 |
| [일반 AI618](https://aida.kisti.re.kr/competition/main/selectQna.do?bbsId=BBSMSTR_BBBBBBBBBBBB&nttId=618), [문제588](https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=588) | 설계·개발 AI 지원 허용·검토 내역 제출, 외부 API 직접 분석/예측 원칙 제한과 공개 기상자료 학습 허용 | 캐시 로컬 추론 검증. 평가 중 원자료 조회 세부는 미확정 |
| [문제·현재 양식](https://aida.kisti.re.kr/competition/main/problem/PROB_000000000004604/detail.do) | 두 실제 본문 SHA 동일, 새HWP222,720바이트·자필서명 안내 추가 | 제공 ZIP을 재다운로드하지 않아 전체 바이트 동일성 주장 없음. 기존 신청서 변경 없음 |
| [일별 질문633](https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=633) | 여전히 미답변, 기존5건 공식 댓글도 본문 동일 | 기존 지표·잠정 정책·개봉 평가 보존 |

## 결빙 학습 대안·과거 기상·도로관리 사례 — 2026-10-10

[결빙 방법론 보고서](ICE_METHODOLOGY_REVIEW_20261010.md)는 학습 길이·거리 제거·기상 이력·클래스 가중치·CatBoost·2단계 비건조 분류를 같은 공간 분할에서 실제 비교합니다.

| 일차 자료 | 적용·확인 | 한계 |
| --- | --- | --- |
| [scikit-learn1.6 HGBClassifier](https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html) | 학습 자료의 클래스 빈도로 계산하는 균형 가중치와 고정 HGB 설정 | 가중 점수를 보정된 확률로 해석하지 않음 |
| [scikit-learn 과거 시계열 입력](https://scikit-learn.org/1.6/auto_examples/applications/plot_time_series_lagged_features.html) | 과거 입력의 시간 경계·공백·평가 목표를 명시 | 같은 겨울의 공간 검증을 미래 시간 검증으로 전용하지 않음 |
| [CatBoost2018 원 논문](https://papers.neurips.cc/paper_files/paper/2018/file/14491b756b3a51daac41c24863285549-Paper.pdf), [공식 설정](https://catboost.ai/en/docs/references/training-parameters/common) | 11쪽 원문·대표4쪽 렌더 확인, 수치20개·Plain·400회·고정 가중치 | Ordered·범주형 목표 통계와 이번 실행을 구별 |
| [FHWA Anti-icing Manual](https://www.fhwa.dot.gov/reports/mopeap/mop0296a.htm) §2.2·3.2·4.1, [RWIS FAQ](https://ops.fhwa.dot.gov/weather/faq.htm) | 노면 열응답 지연·강수·습기·처리 조건과 노면 결빙점·화학 농도의 관측 구분 | 현재는 기상 이력만 추가. 실제 제설·염분·센서 이력 미확보 |
| [Baldwin·Reeves·Rosenow2023 NOAA 소개](https://repository.library.noaa.gov/view/noaa/56154), DOI10.1175/WAF-D-23-0137.1 | 웹 초록·서지에서 동결 강수 조건의 별도 평가와 강수 형태 입력 필요성 확인 | AMS·NOAA PDF 로컬403, 웹 PDF 크기 제한. 전문·계수·성능 수치 전용 없음 |
| [Roberts등2017](https://www.biom.uni-freiburg.de/mitarbeiter/dormann/roberts-et-al-2017-ecography.pdf/at_download/file), [Cawley·Talbot2010](https://jmlr.org/papers/v11/cawley10a.html) | 공간 그룹 전체 제외·반복 개발의 선택 편향을 구별 | 새 위치·다음 겨울·공식 성능 보증 아님 |

익명 HTTP17건 중13건 성공·4건 실패, 공식 숨김 본문·Q&A633 미답변과 같은 해시의 참가서약을 `outputs/private/ice_methodology_references_20261010_v1/`에 보존했습니다. MDPI 원문403·NSSL 연결 실패도 남겼습니다. 2단계 비건조는 이번 자체 가설이며 다른 문헌에서 효과가 입증된 기법으로 소개하지 않습니다.

추가 오차 범위는 Angelopoulos·Bates의 [A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification](https://arxiv.org/abs/2107.07511),2022 공개 원고51쪽에서 별도 보정 자료·주변적/조건부 포함률·분포 변화 논의를 참고했습니다. 원문·대표5/15쪽 렌더는 `outputs/private/temperature_uncertainty_references_20261010_v1/`에 보존했습니다. 실행한 것은 지점 가중 경험분위수이며 현재 공간/시간 교환가능성과 보정/최종 모델의 동일 분포가 입증되지 않아 conformal 보장을 주장하지 않습니다.

## 방법론 블렌딩·세 단계 공간 검증 — 2026-10-10

[블렌딩 보고서](METHOD_BLENDING_REVIEW_20261010.md)에 실제 적용·실패·검증 조건을 정리했습니다. 논문 이론의 가정과 현재4공간그룹·반복 개발의 차이를 유지합니다.

- Breiman, L. (1996), [Stacked Regressions](https://statistics.berkeley.edu/sites/default/files/tech-reports/367.pdf), Machine Learning24:49–64. 16쪽 저자기관 PDF에서 교차 검증 예측·비음수 최소제곱·합1 논의를 확인했습니다. 합1 제약과 지점별 동일 비중은 이번 고정 설계이며 재표본 적합 점수를 검증 성능으로 표현하지 않습니다.
- van der Laan·Polley·Hubbard (2007), [Super Learner](https://biostats.bepress.com/ucbbiostat/paper222/)와 Polley·van der Laan (2010), [Super Learner In Prediction](https://biostats.bepress.com/ucbbiostat/paper266/). Berkeley 작업문헌의 초록·교차 검증 선택 논의를 참고했습니다. 점근적 oracle 결과를 현재 공간 전이 보증으로 전용하지 않습니다.
- [Wang등 예측 결합 검토](https://arxiv.org/abs/2205.04216), [Cawley·Talbot 선택 편향](https://jmlr.org/papers/v11/cawley10a.html): 균등 평균·단독 모델 대조·반복 개발의 한계를 적용했습니다.
- Roberts등 (2017), [구조적 교차 검증 원문](https://www.biom.uni-freiburg.de/mitarbeiter/dormann/roberts-et-al-2017-ecography.pdf/at_download/file), Ecography40:913–929. Wiley403·WSL404는 실패 기록으로 보존하고 저자 대학의17쪽 원문을 확보했습니다. 초록·검증 구조와 예측 목표의 논의를 읽고 공간 블록 적용을 검토했습니다.
- [scikit-learn1.6 StackingRegressor](https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.StackingRegressor.html)·[VotingClassifier](https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.VotingClassifier.html): prefit 동일 학습행의 과적합과 soft voting의 보정 조건을 반영했습니다. 새 평균 점수에 기존 보정 모델을 이식하지 않았습니다.

원문·요청시각·해시는 `outputs/private/method_blending_references_20261010_v1/`에 보존합니다. 공식 제출 공지·서약·Q&A633을 재조회했으며 서약은 이전 원문과 같은 해시이고633은 미답변입니다. 공개 허용·제출 의무를 구별합니다.

## 고정 평균·새 공간 검증의 근거 — 직전 2026-10-10

[평균 후보 보고서](TEMPERATURE_MEAN_AND_BLIND_REVIEW_20261010.md)에 문헌에서 채택한 판단과 실제 실패를 연결했습니다. 문헌의 예제 성능·효과 크기를 이 프로젝트의 결과로 옮기지 않습니다.

- Clemen, R. T. (1989), [Combining forecasts: A review and annotated bibliography](https://scholars.duke.edu/publication/765653), International Journal of Forecasting5(4):559–583. 저자 소속기관의 초록·서지에서 단순 결합의 비교 가치를 확인했습니다. 전문 전체를 읽었다고 주장하지 않습니다.
- Wang, X., Hyndman, R. J., Li, F., Kang, Y. (2023), [Forecast combinations: An over 50-year review](https://robjhyndman.com/publications/combinations/), International Journal of Forecasting39(4):1518–1547, DOI10.1016/j.ijforecast.2022.11.005. 실제 읽은 자료는 [2022 공개 원고](https://arxiv.org/abs/2205.04216)의56쪽PDF이며 파일5/6쪽을 렌더해 확인했습니다. 단순 평균·가중치 추정 오차·성분 오차 상관을 검토했습니다. 저자 소개 페이지의 로컬403과 공개 원고 성공을 함께 보존했습니다.
- Hyndman·Athanasopoulos, [Forecasting: Principles and Practice3, §13.4](https://otexts.com/fpp3/combinations.html), [scikit-learn1.6 VotingRegressor](https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.VotingRegressor.html). 고정 평균의 정의를 참고했으며 새로운 가중치 탐색·VotingRegressor 재적합을 사용하지 않았습니다. 다른 예측 대상의 수치를 전용하지 않습니다.
- [Cawley·Talbot2010](https://jmlr.org/papers/v11/cawley10a.html), [Roberts등2017](https://doi.org/10.1111/ecog.02881). 이미 개봉된 반복 개발과 새 지점의 사전 봉인·일회 평가를 구분했습니다. 거리 상한·공간 그룹만으로 전북 목표 영역의 적용 범위가 입증됐다고 주장하지 않습니다.
- [기상청 AWS 안내](https://apihub.kma.go.kr/apiList.do?seqApi=2&seqApiSub=239), [기상자료개방포털 AWS](https://data.kma.go.kr/data/grnd/selectAwsRltmList.do?pgmNo=56). 실제AWS733 확인 요청403·정상CSV 로그인 분기·익명 세션 상태를 확인했습니다. 계정 로그인·활용신청·AWS 확장 원문 확보는 하지 않았습니다.
- [날씨누리 AWS](https://www.weather.go.kr/w/weather/land/aws-obs.do), [국립환경과학원 기상자료](https://www.data.go.kr/data/15150439/fileData.do). 전자는 필요한 첫 겨울 전체 제공을 확인하지 못했고 후자는2024년8,783행 샘플로 명시됩니다. 전체 AWS 관측 대체자료로 사용하지 않았습니다.

원문·URL·시각·해시는 `outputs/private/temperature_mean_references_20261010_v1/`에, 정상 포털 접근 분기와 대체자료6개 공개 응답·익명 상태 기록은 별도 manifest에 보존했습니다. 인증키·인증 URL·계정 정보는 기록하지 않습니다. 공식 문제·공지·참가서약 재확인에서도 Q&A633은 미답변이며 수집·평가·공개 허용을 혼동하지 않습니다.

## 거리 변수 제거·기상 관측망 확대의 근거

[후속 보고서](WEATHER_DISTANCE_AND_NETWORK_REVIEW_20261010.md)에 실제 실험·공개 지점 자료·미확보 관측값을 구분했습니다. 확인일은 2026-10-10입니다.

| 일차 자료 | 이번 확인·적용 | 한계 |
| --- | --- | --- |
| [Roberts 등2017, Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure](https://doi.org/10.1111/ecog.02881), Ecography40:913–929 | 구조가 있는 자료의 무작위 분할 문제, 공간 이전 목적에 맞는 그룹 제외와 외삽 해석 | 웹 본문을 확인. 로컬 다운로드는 HTTP 오류였으며 원문 저장 성공으로 표시하지 않음 |
| [Dumitrescu2026, A deep learning framework for gridding daily climate variables from a sparse station network](https://gmd.copernicus.org/articles/19/8895/2026/), GMD19:8895–8913, 2026-09-21 | 루마니아2020–2023년 기온·강수 격자화. 사전 고정 테스트26곳·학습130곳 및 관측망/지형 대표성 점검 참고 | 일평균 기온·강수 보간이며10분 노면온도·Ice 과제가 아님. 신경망 구현·논문 성능 이전 없음 |
| [기상청 관측지점정보](https://data.kma.go.kr/tmeta/stn/selectStnList.do?pgmNo=123) | 공개 CSV의 AWS2,619·ASOS148 이력, 날짜 경계·좌표·기간 안정 후보 검산 | 날짜 단위의 시작/종료일이며 실제 관측 가용성·센서 정상·정확한 변경 시각을 입증하지 않음 |
| [기상청 지상관측 지점정보 API](https://apihub.kma.go.kr/apiList.do?seqApi=2&seqApiSub=317) | 기준 시각의 지점정보 의미·활용 조건 확인 | 실제 인증 요청403. 공개 CSV 확보와 API 사용 승인을 구별 |
| [기상청 AWS 매분자료 API](https://apihub.kma.go.kr/apiList.do?seqApi=2&seqApiSub=239) 및 공식 첨부 명세서21쪽 | KST·WS10/WS1·15분 누적강수·결측/오류 값·단일지점 최대24시간·403/401 오류 표 확인. 핵심3쪽 렌더 | 개발 AWS733의11분 확인 요청403. 추가4곳 실제 자료·확장 모델은 미완료 |

기상청 명세서는 새 API 자료의 -50 이하를 오류/결측으로 설명합니다. 기존 대회 원본 유효 범위·결측 규칙에 소급 적용하지 않았습니다. 날짜/시간·풍속 평균·강수 누적 단위가 다르면 가까운 관측소를 추가해도 같은 입력 비교가 아니므로 원본 AWS 헤더와 대조했습니다. 공개 원문·포털 CSV·실패/성공 다운로드·PDF 해시는 비공개 `weather_network_review_20261010_v1/`에 있습니다. 인증키는 포함하지 않습니다.

앞서 확인한 Cawley·Talbot의 모델 선택 편향과 scikit-learn1.6 HGB 문서를 재사용해, 같은100회 모델·같은 행에서 거리2개만 제거했습니다. 문헌은 비교 설계의 근거이며 현재 후보 채택 또는 새 독립 성능의 증거가 아닙니다.

## 미해결 사항의 추가 근거

[순차 검토 보고서](UNRESOLVED_EVIDENCE_REVIEW_20261010.md)에 위치·지표 분모·입력 범위·지도 적용 조건을 연결했습니다. 공식 페이지와 논문 원문19개의 수집 시각·URL·해시는 비공개 `unresolved_review_20261010_v1/source_manifest.json`에 보존했습니다.

| 1차 자료 | 실제 반영 | 적용 한계 |
| --- | --- | --- |
| [도로기상 API 공식 설명](https://apihub.kma.go.kr/apiList.do?seqApi=971&seqApiSub=293), [기상청 지점 메타데이터](https://data.kma.go.kr/tmeta/stn/selectStnList.do?pgmNo=123), [MTMS 가입 화면](https://mtms.kma.go.kr/registUser.do) | 관측 좌표·정적 목록과 실제 설치/교정 이력을 구별. 소속기관·업체 및 승인 구조 확인 | 공개 화면에서 실제 도로 지점 대장을 확보한 것은 아님 |
| [FHWA ESS 추가 고려사항](https://ops.fhwa.dot.gov/publications/ess05/ess0505.htm) | 위치·노출·유지관리·변경 이력의 확인 항목 | 미국 일반 지침이며 한국 지점 이설의 증거가 아님 |
| [scikit-learn 1.6.1 F1](https://scikit-learn.org/1.6/modules/generated/sklearn.metrics.f1_score.html), [평가 지표](https://scikit-learn.org/1.6/modules/model_evaluation.html) | P 또는 R 미정의여도 F1이0인 실패일 보존. 96개 분모/미정의 조건 검산 | 대회 Q&A633의 미확정 세부 규정을 대신하지 않음 |
| [Li 등 ILES 2026](https://gmd.copernicus.org/articles/19/9035/2026/), DOI10.5194/gmd-19-9035-2026 | 2026-09-24 발표. 3.5·4.4절의 대상 과거 온도와 지점별 재학습 확인 | 현재 무관측 공간 이전 성능과 직접 비교 불가. ILES는 구현하지 않음 |
| [Meyer·Pebesma AOA](https://arxiv.org/abs/2005.07939), DOI10.1111/2041-210X.13650 | 학습 범위와 새 지점 입력 조건 차이를 점검 | 이번 개별 변수 범위/백분위 비교는 다변량 AOA 구현이 아님 |
| [Barber 등 비교환 자료 conformal](https://arxiv.org/abs/2202.13415), DOI10.1214/23-AOS2276 | 시간·공간 변화에서 민감도와 오차 보장을 구별 | conformal 구간·90% 보장을 구현/검증한 것은 아님 |

## 최신 전이·현장 운영 근거 — 2026-10-10

[후속 연구 보고서](AWARD_READINESS_REVIEW_20261010.md)에 출처별 실제 구현·평가·한계를 연결했습니다. 온도6개 후보와 일별 임계값 정책을 구현했으며 새4개 지점의 봉인 평가에서 채택 조건 실패를 확인했습니다.

- [2026 공식 대회 소개](https://aida.kisti.re.kr/competition/main/overview.do): 창의성20·우수성50·효과성30을 현재 심사 관점 검토에 사용했습니다. 2025년 내용이 남은 과거 상세 페이지와 구별하며 자체 판단을 공식 점수로 표현하지 않습니다.
- [Cawley & Talbot 2010, JMLR](https://jmlr.org/papers/v11/cawley10a.html): 모델 선택과 반복 검증의 편향 근거. 새 정답 요청 전에 입력·모델·전슬롯 예측을 봉인하는 절차에 반영했습니다.
- [scikit-learn 1.6 HGBRegressor](https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html), [임계값 선택](https://scikit-learn.org/1.6/modules/classification_threshold.html): 날씨14·열24·잔차 비교, 제곱/절대 손실 및100/300회, 학습과 다른 그룹의 일별 선택을 구현했습니다. 개발 최저 오차를 새 독립 성능이라고 보고하지 않습니다.
- [2024 MDSS 독립 평가 보고서](https://rosap.ntl.bts.gov/view/dot/81833), FHWA/IN/JTRP-2024/31: 독립 기상·마찰·차량·제설 기록과 사건별 운영 판단 비교. PDF28쪽의 파일4·17·23쪽을 중점 검토했습니다. 이 프로젝트에 해당 현장 자료가 확보됐다는 의미는 아닙니다.
- [2026 Mobile RWIS Phase II](https://rosap.ntl.bts.gov/view/dot/92061), FHWA-ICT-26-008, DOI10.36501/0197-9191/26-008: 센서 교정·연결·운영 인력·단계적 확장과 제설 사용량 평가. PDF97쪽의 파일60·81~83쪽을 중점 검토하고 권고 페이지를 렌더해 확인했습니다. 해외 절감률·비용 효과를 국내 결과로 전용하지 않았습니다.
- [FHWA 교량 결빙 사례](https://ops.fhwa.dot.gov/weather/resources/publications/tech_briefs/cs037.htm): 노면·기상·수분/약품 측정과 현장 판단의 연결을 검토했습니다. 현재 지도의 위험 등급이나 사고 감소를 증명하는 자료는 아닙니다.
- [기상청 지상기상관측지침2024.10](https://data.kma.go.kr/resources/images/publication/%EC%A7%80%EC%83%81%EA%B8%B0%EC%83%81%EA%B4%80%EC%B8%A1%EC%A7%80%EC%B9%A8.pdf): 도로기상 장 파일186–196쪽을 읽고 파일190쪽을 렌더해 확인했습니다. 취약 위치·차로 대표성, 위치 변화·광학 센서 점검과MTMS 기록 확인 경로를 반영했습니다. 실제 지점의 이설·장비 불량 대장은 확보하지 못했습니다.

RoadSurf2024와 METRo2001의 적용 한계는 아래에 이어 기록합니다. 이번 METRo 직접 조회는 접근 제한이 있어 전문을 모두 재검토했다고 주장하지 않습니다. 최신 공식·논문·PDF 원문과 해시는 `outputs/private/judge_followup_20261009_v1/`에 있습니다. 발견한33407 좌표 차이는 원문 데이터 증거이며 문헌만으로 이동·센서 고장 원인을 확정하지 않습니다.

## 최신 보정·관측 대표성·전북 구간 — 2026-10-09

[점수 보정 보고서](SCORE_CALIBRATION_REVIEW_20261009.md)와 [구간·환경 보고서](SEGMENT_EXPOSURE_REVIEW_20261009.md)에 실제 적용과 한계를 연결했습니다. 앞선 문서의 ‘보정 미실행’은 당시 상태이며 이번에는 중첩 sigmoid·사전 비율 점수 보정을 구현·검산하고 미채택했습니다. 원 논문의 성능·계수·배점을 가져오지 않았습니다.

| 1차 자료 | 이번 적용·확인 | 한계 |
| --- | --- | --- |
| [RoadSurf, Karsisto 2024](https://gmd.copernicus.org/articles/17/4837/2024/) | 열수지·수분/눈/얼음 저장량 구분, 단순 저온·수분 가안 해석 | 완전한 물리 모델·제빙 과정 구현 아님 |
| [Vaisala 센서 공식 설명](https://docs.vaisala.com/r/M211607EN-AA/en-US/GUID-8FB4E70E-7340-403E-BD77-6ED1D7F3AA0A) | 광학/매립·관측 영역·상태/온도 불일치 가설 검토 | 실제 설치 장비 모델·오라벨 확인 불가 |
| [Lipton·Wang·Smola 2018](https://proceedings.mlr.press/v80/lipton18a.html), [scikit-learn 보정](https://scikit-learn.org/1.6/modules/generated/sklearn.calibration.CalibratedClassifierCV.html) | 클래스 조건부 분포 가정·모델 학습/보정 분리 | 순수 label shift를 가정하지 않음. BBSE는 구현하지 않음 |
| [SGIS 통계경계 설명](https://sgis.mods.go.kr/view/pss/openDataIntrcn), [경계 API](https://sgis.mods.go.kr/developer/html/newOpenApi/api/dataApi/addressBoundary.html) | EPSG:5179, 2024년 전북 경계(코드 35)의 자기 영역 조회·해시 확인 | API 표현 경계와 원문 출처 보존. 법정 측량 경계·재배포 권한을 확정한 것은 아님 |
| [국토교통부 2023 표준노드링크 기준](https://www.codil.or.kr/filebank/moct2014/202301/MOCT3000_1.PDF?nserialno=3000), [FHWA ESS 입지](https://ops.fhwa.dot.gov/publications/ess05/ess0503.htm) | ROADTYPE 003·004, LANES·MAXSPD·UPDATEDATE 해석과 지역·국지 대표성 구분 | 과거 링크 코드가 구조물의 정확한 경계와 같다는 뜻은 아님. 현행 제한속도나 한국 구간의 효과 크기를 확인한 자료도 아님 |

공식 문제·자료 본문·Q&A 6건·공지·참가 서약 재조회 원문은 `outputs/private/final_review_20261009_v1/`에 SHA256와 함께 보존했습니다. SGIS 원천 응답·조회 조건은 `outputs/private/sgis_boundary_2024_v1/`에 보존했습니다. 키·인증 응답·요청 토큰은 출처 문서에 넣지 않습니다. 시간 블록 재표집은 자체 정의한 고정 지점 민감도 계산이며 원 논문의 엄밀한 신뢰구간 구현이라고 주장하지 않습니다.

## 온도 교차 추정·상태 분류·점수 이전 — 2026-10-09

이 절은 보정 실험 전 검토 기록입니다. 이후 수행한 보정의 결과는 위 최신 절과 [보정 보고서](SCORE_CALIBRATION_REVIEW_20261009.md)에서 확인합니다. BBSE는 구현하지 않았습니다.

[최신 실험 보고서](JOINT_SURFACE_REVIEW_20261009.md)에 출처별 실제 적용과 한계를 연결했습니다. 원문 URL·수집 시각·SHA256는 비공개 검토 폴더에 보존합니다.

- Karsisto, V. E. (2024), [RoadSurf 1.1: open-source road weather model library](https://gmd.copernicus.org/articles/17/4837/2024/), GMD 17, 4837–4853, DOI 10.5194/gmd-17-4837-2024. 온도 에너지수지와 물·눈·얼음·착빙 저장량을 구분하는 근거입니다. 이번 데이터 모델을 RoadSurf 구현이나 검증된 물리 모델로 부르지 않습니다.
- [Vaisala RWS200 Surface state and temperature sensors](https://docs.vaisala.com/r/M211607EN-AA/en-US/GUID-8FB4E70E-7340-403E-BD77-6ED1D7F3AA0A), 문서 M211607EN-AA. 광학·매립 방식과 수분·약품·동결점·측정 면적·설치 영향을 해석하는 공식 기술 자료입니다. 대회 지점의 실제 장비 모델이나 센서 오류를 확인한 근거는 아닙니다.
- [scikit-learn 1.6 StackingClassifier](https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.StackingClassifier.html)와 [HGBClassifier](https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html). 같은 학습 행의 보조 예측 재사용이 초래하는 과적합 위험, 교차 검증 예측과 이진/다중 손실을 확인했습니다. 여기서는 공간 그룹을 직접 제외해 온도를 입력으로 만들었습니다.
- Lipton, Z. C., Wang, Y.-X., Smola, A. J. (2018), [Detecting and Correcting for Label Shift with Black Box Predictors](https://proceedings.mlr.press/v80/lipton18a.html), ICML, PMLR 80, 3122–3130. 양성 비율 이동의 추정·보정에는 클래스 조건부 입력 분포 유지와 혼동행렬의 가역성 등 조건이 필요합니다. 지점별 정답 비율이 다르다는 사실만으로 이 조건이 성립한다고 판단하지 않습니다.
- [scikit-learn 1.6 CalibratedClassifierCV](https://sklearn.org/1.6/modules/generated/sklearn.calibration.CalibratedClassifierCV.html). 모델 학습과 보정 자료의 분리, 작은 자료의 isotonic 과적합 한계를 확인했습니다. 보정과 BBSE는 후속 실행 가설이며 이번에 수행한 모델 성과가 아닙니다.

공식 문제·데이터 본문·제출 공지·참가 서약과 여섯 Q&A를 이번 작업에서도 재확인했습니다. 직전 원문과 일치하며 633번 답변은 여전히 없습니다. 확정 답변과 [미확정 규격](../competition/QUESTIONS_FOR_ORGANIZER.md)을 구분합니다.

## 제공 설명서 기반 도로교·보도교·철교 구분 — 2026-10-09

제공 `other_spatial.zip` 내부의 **국토지리정보원 전국 연속수치지형도 데이터베이스설계서 v5.1.1(2014-12-30)를** 직접 확인했다. 3쪽은 N3A 교량·터널 면 레이어와 1:5,000 목록, 21쪽은 교량 KIND·QUAL 코드와 EYMD 설치 연도, 22·27쪽은 FMTA 제작 정보 참조(SL_PRODUCT_INFO), 27쪽은 터널 필드·통합 코드다. 제공 버전의 속성 의미를 해석하는 근거이며 최신 고시·현재 구조물 현황·치수 단위·실제 차로 소속을 증명하지 않는다.

제공 XML의 EPSG:5179·선형 미터·생성일 20230215·수정/동기화일 20240419를 기록했으나 처리일을 시설 관측일로 바꾸지 않았다. 설명서·XML 원본과 검토 페이지는 수정본 시설 검토 폴더 `road_bridge_kind_review_v1/`에 멤버명·SHA256와 함께 보존한다. 수평 중첩·재질 코드에서 결빙 위험 배점이나 열계수를 만들지 않았다. 도로교·보도교·철교는 종류 코드로 구분하되 층위 교차·인접 차로의 불확실성은 남는다.

## 방향별 구간의 공식 도로환경 해석 — 2026-10-09

[국토교통부 공식 구축기준 전문](https://www.codil.or.kr/filebank/moct2014/202301/MOCT3000_1.PDF?nserialno=3000)의 11쪽에서 LANES=차로수, MAX_SPD=최고 제한속도, UPDATEDATE=구축 날짜를 확인했다. 보존한 2024-03-25 ZIP의 원본 DBF 150개 링크를 직접 대조해 500m·1km 후보별 유형 코드의 길이 비중과 차로수·속도 범위를 연결했다. 이 2023년 기준은 과거 자료 해석의 근거다. 링크 코드가 정확한 물리적 구조물 경계와 같다는 검증은 별도로 남는다.

[FHWA ESS 센서 배치 지침, 2005년](https://ops.fhwa.dot.gov/publications/ess05/ess0503.htm)은 지역 대표 관측과 교량·그늘 등 국지 취약 지점 관측의 목적을 구분한다. 센서 위치가 관측의 대표성에 영향을 주며, 서로 다른 기상 조건에서 열 지도 조사를 설명한다. 이는 추가 9개 지점의 표본 편중·공간 전이 한계를 해석하고 도로환경별 검증을 요구할 근거다. 최신 한국 운영 규정이나 이 프로젝트의 검증된 효과 크기로 취급하지 않는다.

[FHWA 관측 요구사항](https://ops.fhwa.dot.gov/publications/ess05/ess0510.htm)은 노면온도·노면상태·동결점·약품농도 등 관측을 구분한다. [Met Office의 노면온도 안내](https://www.metoffice.gov.uk/services/transport/road/independent-gritting)는 노면온도와 기온이 다를 수 있음을 설명한다. 기온이나 교량 코드 하나로 Ice 정답·운영 위험 등급을 대체하지 않는다. 세 원문HTML·수집일·URL·SHA256는 수정본 비공개 `external/road_environment_references_20261009/source_manifest.json`에 보존했다. Met Office 예보 상품은 구독하거나 모델 입력으로 수집하지 않았다.

실험 설계·결과 해석에 참고한 공식 자료와 원 논문을 정리합니다. 참고 자료를 읽은 것과 외부 데이터를 모델 입력으로 수집한 것을 구분합니다.

[문서 목록·용어 풀이](../README.md) · [프로젝트 소개](../../README.md)

2026-10-08에는 문헌 검토에 더해 **NASA POWER 시간별 복사량과 Copernicus GLO-30 공개 DSM을 수집**했다. 원천 URL·단위·해시·이용 고지는 수정본 작업 공간의 `outputs/private/external/`에 보존했다. NASA 자료는 공개 지연 때문에 사후 추정 실험 전용이다. 논문의 수치를 이 프로젝트의 기대 성능이나 위험도 배점으로 전용하지 않는다.

## 물리·지형 입력 고도화 — 2026-10-08

| 1차 자료 | 확인 및 적용 | 한계 |
| --- | --- | --- |
| [RoadSurf 1.1 논문, FMI, 2024](https://gmd.copernicus.org/articles/17/4837/2024/gmd-17-4837-2024.html), [공식 MIT 소스](https://github.com/fmidev/RoadSurf) | 복사·노면 에너지 수지와 물·얼음 저장량이 중요한 과정임을 확인. 냉각·수분·운량·복사·차폐 특성의 설계 근거 | 완전한 RoadSurf를 이식하거나 제빙제·물 저장량을 재현한 모델은 아님. 소스 열람만 했으며 코드 복제 없음 |
| [METRo, Crevier & Delage, 2001](https://journals.ametsoc.org/view/journals/apme/40/11/1520-0450_2001_040_2026_manmfr_2.0.co_2.xml) | 노면 열수지·수분과 관측 결합의 근거 | METRo의 검증 수치를 본 프로젝트에 전용하지 않음 |
| [Sensors 26(13), 4225, 2026](https://www.mdpi.com/1424-8220/26/13/4225) | 국내 무관측 도로 결빙 예방 연구의 입력·정답·분할을 검토 | 규칙 생성 예방 위험 3분류 및 무작위 분할의 높은 F1을 실제 Ice·공간 제외 검증과 비교할 수 없음 |
| [기상청 ASOS 설명](https://data.kma.go.kr/data/grnd/selectAsosRltmList.do?pgmN=) | 겨울철 강수 관측 간격과 QC·결측 설명 확인 | 빈 강수·적설·일사 값을 무조건 0으로 대체하지 않음 |
| [NOAA 태양 위치 수식](https://gml.noaa.gov/grad/solcalc/solareqns.PDF) | KST UTC+9, 날짜·좌표에서 태양 고도와 방위각 계산 | 대기 굴절·실측 차광·건물 상세는 미보정 |
| [NASA POWER Hourly API](https://power.larc.nasa.gov/docs/services/api/temporal/hourly/), [자료 FAQ](https://power.larc.nasa.gov/docs/faqs/data/) | UTC를 명시해 단파·장파 복사량 수집. 단위 Wh/m², 완전히 끝난 시간 구간만 연결 | 복사자료 공개 지연 5–7일, 약 1도 공간 규모. 실시간 입력 또는 도로별 실측 복사량으로 해석 금지 |
| [Copernicus 공개 AWS 자료](https://registry.opendata.aws/copernicus-dem/), [COG 설명](https://copernicus-dem-30m.s3.amazonaws.com/readme.html), [제품 설명서 v5.0](https://dataspace.copernicus.eu/sites/default/files/media/files/2024-06/geo1988-copernicusdem-spe-002_producthandbook_i5.0.pdf), [이용 조건](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf) | 공개 GLO-30 4개 타일. 설명서 10·13쪽에서 미터·EGM2008 수직 기준 확인. 지형 상대고도·16방위 지평선 후보 생성 | DSM은 수목·건물을 포함. 도로 상판 표고·도로 종단경사가 아니며, 수집 시기와 현 도로 환경의 차이 가능 |
| [scikit-learn 1.6 HGB 공식 문서](https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html) | 결측 처리·class_weight·조기종료 동작 확인 | 20배 양성 가중치는 사전 고정 비교 후보이며 이론적 최적값이 아님 |
| [Lipton et al., F1 임계값 연구, 2014](https://arxiv.org/abs/1402.1892) | F1과 분포·임계값의 관계 및 희귀 클래스의 원치 않는 판정 사례를 검토 | 본 점수는 보정 확률이 아니어서 논문의 확률 임계값 공식을 그대로 적용하지 않음. 일별 개수 제한은 프로젝트 자체 가설이며 실험에서 미채택 |
| [CatBoost 공식 학습 설정](https://catboost.ai/en/docs/references/training-parameters/common), [결측 처리](https://catboost.ai/en/docs/concepts/algorithm-missing-values-processing) | 수치 NaN, 고정 class_weights, 대칭 트리·정규화·조기종료 설정 확인 | 보호 지점/다음 겨울 정답을 early stopping이나 임계값 선택에 사용하지 않음 |

NASA 출처: NASA Langley Research Center POWER Project, NASA Earth Science Directorate Applied Science Program. Copernicus의 원본·가공물 저작권 및 책임 고지는 `external/copernicus_dem/manifest.json`과 `eula_F.pdf`에 유지하며, 해당 자료를 포함한 외부 배포물에도 이어 붙여야 한다. 원시 외부 자료도 현재 Git에 포함하지 않는다.

| 자료 | 확인한 내용 | 적용 범위 |
| --- | --- | --- |
| [기상청 AWS 관측자료 항목 설명](https://www.weather.go.kr/wnuri_help/html/observation/aws-table.jsp) | 강수 15·강수 60은 선택 시각 이전의 누적량, 일강수는 00:01에 초기화. 풍향·풍속의 과거 1·10분 평균 설명 | AWS 15분 강수를 사용하고 일 누적량의 단순 차분을 초기 특징에서 제외. 제공 ZIP의 변수명·단위는 별도 대조 |
| [기상청 ASOS 자료 설명](https://data.kma.go.kr/data/grnd/selectAsosRltmList.do?pgmN=) | ASOS 시간 자료는 매 정시, 품질 플래그 정보가 있을 수 있음 | 1시간 원천과 10분 RWIS의 시각 차이·가용성을 명시. 제공 ZIP에 QC 플래그가 있는지는 독립 점검 |
| [미국 FHWA RWIS 안내](https://ops.fhwa.dot.gov/weather/resources/publications/tech_briefs/rwis.htm) | 기온·노면온도·강수·제빙제 정보를 구분해 도로 상태 판단에 활용 | 노면온도 회귀와 결빙 판정을 분리하고 제빙 관련 상태를 무비판적으로 Ice에 합치지 않음 |
| [Roberts et al. (2017), *Ecography*](https://www.wsl.ch/lud/biodiversity_events/papers/Roberts_et_al-2017-Ecography.pdf) | 공간·시간 구조가 있는 자료의 무작위 행 분할은 새 위치 일반화 평가에 부적합할 수 있음 | RWIS 관측소 단위 LOSO와 겨울 간 시간 검증을 별도 유지 |
| [Ji et al. (2023), 교량 노면온도 추정 연구](https://www.gljtkj.com/EN/abstract/article/1002-0268/10011) | 교량별 환경 차이와 기상 인자의 관계를 보고하고 다른 교량으로의 전이 문제를 다룸 | 교량·지형 특징을 다음 단계의 검증 가설로만 사용. 해당 연구 성능을 이 데이터와 직접 비교하지 않음 |

KMA 웹 도움말은 일반 관측망 설명이다. 이번 대회 제공 CSV의 가공 시점·발표 지연·ASOS 시각대는 별도 메타데이터가 확인될 때까지 잠정 가정이다. 해당 불확실성은 [운영진 질문](../competition/QUESTIONS_FOR_ORGANIZER.md)과 [검증 규약](../validation/VALIDATION_PROTOCOL.md)에 유지한다.

## 후속 실험 사례의 추가 1차 자료 — 2026-09-23 확인

| 자료 | 확인한 내용 | 이 프로젝트의 적용 범위와 한계 |
| --- | --- | --- |
| [FHWA RWIS 관측소 입지 지침 §2](https://ops.fhwa.dot.gov/publications/ess05/ess0502.htm), 2005 | 지역 대표 관측소와 특정 교량·짧은 구간을 대표하는 국지 관측소를 구분하고 다른 관측망의 보완 활용을 설명 | AWS 2·3순위 대체와 RWIS 대표성 검증의 설계 근거. 대체 AWS가 자동으로 정확하다는 증거는 아님 |
| [FHWA 입지 지침 §3](https://ops.fhwa.dot.gov/publications/ess05/ess0503.htm), [§4](https://ops.fhwa.dot.gov/publications/ess05/ess0504.htm), 2005 | 저지대·교량·음영 및 센서 설치 위치·물고임에 따른 관측 영향 | 단일 시각 Ice 사건의 품질 검토와 정적 특징의 근거. 원시 정답을 자동 제외하는 기준은 아님 |
| [FHWA, Michigan Finds a Solution for Icy Bridges](https://ops.fhwa.dot.gov/weather/resources/publications/tech_briefs/cs037.htm), FHWA-SA-96-045 | 교량 상판이 인접 도로보다 먼저 얼 수 있고 RWIS로 노면온도·습윤 상태·기상을 함께 관측한 사례 | 교량 특징 실험 가설. 전북도 교량의 효과 크기나 위험 배점으로 전용하지 않음 |
| [FHWA, Nebraska Bridge Prioritization](https://ops.fhwa.dot.gov/publications/fhwahop16093/ch7.htm), 제 7.5절 | 사고·교통·기상·교량·유지관리 자료를 결합한 제빙 설비 우선순위 사례 | 사고·교통 정보가 없는 본 프로젝트의 결빙 취약도와 사고 위험을 구분할 근거 |
| [Bogren, Gustavsson & Postgård, International Journal of Climatology 20 (2000)](https://rmets.onlinelibrary.wiley.com/doi/abs/10.1002/%28SICI%291097-0088%28200002%2920%3A2%3C151%3A%3AAID-JOC460%3E3.0.CO%3B2-U) | 국지 노면온도 차이와 지형·구름·바람·일사 조건의 관계를 분석한 원 논문 | DEM 기반 상대고도와 기상 조건 상호작용 가설. 스웨덴 계수·임계값을 직접 사용하지 않음 |
| [Bogren 등, Meteorological Applications 7 (2000)](https://rmets.onlinelibrary.wiley.com/doi/10.1017/S135048270000150X) | 차광 노면과 일사 노출 노면의 온도 차이와 해 진 뒤 지속을 분석한 원 논문 | 실제 계산 가능한 음영 특징이 확보될 때만 시험 |
| [기상청 2023.11.15 도로살얼음 발생 가능 정보 보도자료](https://www.weather.go.kr/kma/servlet/NeoboardProcess?bid=press&callback=https%3A%2F%2Fwww.kma.go.kr%2Fkma%2Fnews%2Fpress.jsp&fno=3&k=ATC202311150847023_69dc0f63-f58c-4954-aeca-7ff79d4b4293.pdf&mode=download&num=1194292&ses=USERSESSION) | AWS 강수·도로기상 기온·노면상태 등을 융합해 관심/주의/위험 정보를 제공한 공식 서비스 사례 | 정보 활용 예시일 뿐, 본 대회 Ice 코드·일별 F1·구간 위험도 기준과 동일하지 않음 |

위 9월 23일 작업 당시에는 문헌 열람만 수행했다. 10월 8일 외부 자료 추가 현황은 이 문서 상단과 [후속 실험 근거](FOLLOWUP_EVIDENCE.md)에 별도로 기록했다. 외부 업로드·공개는 하지 않았다.


## 이정·좌표의 독립 교차 검토 자료 — 2026-10-09

- [한국도로공사 본선 도로관리용 CCTV 현황 20260423](https://www.data.go.kr/data/15102134/fileData.do): 노선명·CCTV명·이정·방향 등 2,999행. 포털 이용허락범위 제한 없음. 좌표 및 공통 CCTV ID가 없어 별도 지도와 유일한 이름 후보만 교차 점검한다.
- [한국도로공사 ROADPLUS](https://www.roadplus.co.kr/main)와 [공개 CCTV GeoJSON](https://www.roadplus.co.kr/geojson/EX_CCTV.geojson): 홈페이지가 쓰는 3,838개 좌표. 이름 중복과 잘못된 위치 가능성을 점검하고 재배포 조건 미확인으로 비공개 검증에만 사용한다.
- [서울시립대 교통안전 DB 연구 지도](https://traffic-viewer.urbanscience.uos.ac.kr/): 공개 UI 소스의 100m급 RoutePath를 기하 참조로만 사용. 단위·노선명 오류와 공식 기준점 이정 차이를 발견하여 공식 선형으로 채택하지 않았다.

자료 수집 날짜 2026-10-09와 해시는 수정본 비공개 출처 manifest 및 기준점 summary에 기록했다. 공식 현재 CCTV 현황은 과거 두 겨울의 선형이나 제공 도형의 차로·상하행을 검증하지 않는다.


## 최근 냉각 누적의 추가 개발 비교 — 2026-10-09

[Yi·Seo(2026), Early warning of road icing from antecedent meteorological conditions without consistent critical slowing down](https://arxiv.org/abs/2609.33528), 2026-09-27 공개 프리프린트. [저자 공개 코드](https://github.com/yunam-seo/road-icing-forced-threshold)는 MIT 라이선스이며 검토 커밋은 `5552934b22dc25be07839fc53fe757a7d136b072`다. 원자료는 저장소에서 재배포되지 않는다. 저자 관측자료를 새 독립 검증 자료로 확보했다고 주장하지 않는다.

최근 냉각·서리점 대비 온도차·영도 교차를 지수 감쇠 누적으로 나타내는 개념에서 착안했다. 우리 구현은 20·60분 감쇠, 10분 간격의 구간 상수 입력 정확 적분, 유효 관측 가중 커버리지 80% 조건과 공백 시 교차 연결 차단을 사용한다. 이는 논문의 1분 발생 예보와 다르고, 자기 관측 대신 다른 개발 지점의 과거 관측을 쓴다. 대회 04 양성 정의를 유지하며 논문의 04/15 양성·사건 병합·온도 품질 필터를 대회 정답에 적용하지 않았다. 논문 성능 수치는 우리 성능으로 옮기지 않는다.

원본 공개 코드·LICENSE·고정 URL/해시는 수정본 비공개 `external/antecedent_reference/manifest.json`에 보존했다. 수치 결과는 `antecedent_forward/summary.json`과 [진행 보고](../history/PROJECT_STATUS.md)를 확인한다.


## 규제 선형·가법 스플라인 비교의 구현 근거 — 2026-10-09

설치된scikit-learn1.6.1의 [LogisticRegression 공식 문서](https://scikit-learn.org/1.6/modules/generated/sklearn.linear_model.LogisticRegression.html)와 [SplineTransformer 공식 문서](https://scikit-learn.org/1.6/modules/generated/sklearn.preprocessing.SplineTransformer.html)를 확인했다. L2 규제C=0.1·양성 가중치 20을 사전에 고정하고, 같은 40개 열·수분 입력에서 선형과 4변수의 가법 스플라인을 비교한다. 스플라인은 2차·5개 물리 단위 매듭·선형 외삽이며, 매듭은 검증 정답이나 분포에서 선택하지 않았다. 중앙값 대체·결측 표시·스케일링은 각 학습 분할 안에서 처리하고 수렴 경고는 실패로 취급한다.

고도를 제외했으므로 41입력의 기존 HGB와의 차이를 모두 분류기 구조 효과로 주장하지 않는다. 선형/스플라인 사이는 같은 입력이다. 가중 학습 점수와 상관된 입력의 계수는 실제 결빙 확률이나 독립 물리 효과가 아니다. 결과는 수정본 `regularized_forward/summary.json`과 [진행 보고](../history/PROJECT_STATUS.md)에 기록한다.


## 다른 지점의 과거 노면상태 추가 입력 — 2026-10-09

[공식 답변 588](https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=588)과 [공식 답변 555](https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=555)를 다시 확인했다. 정답은 Ice만 양성이고 0/-999는 제외한다. 보호 지점의 추정 대상 실측값을 학습·예측 입력으로 사용하지 않는다. 최신 목록은 620·603·588·556·555와 같았으며 재확인 원문·해시는 원본 작업 루트의 비공개 `official_review_20261007/*surface_state*`에 보존했다.

[Yi·Seo(2026)](https://arxiv.org/abs/2609.33528)의 초기 상태·수분 공급 논의에서 착안하되, 다른 지점의 과거 상태가 현재 대상의 상태를 설명하는지는 별도 가설로 검증한다. 현재 상태별 10개 표시, 60/180분 관측 상태 비율 및 커버리지, 최근 관측 Ice의 경과시간을 합친 23개 입력이다. 대상·내부/외부 제외·보호 지점은 상태 참조에서 차단한다.13·15는 별도 입력으로 구분하고 양성 정답으로 바꾸지 않는다. 관측 비율은 실제 결빙 지속시간이나 위험 확률이 아니다.


## 온도 추정의 분류 입력 연결 — 2026-10-09

[캐나다 BC 교통부 RWIS 정의](https://www.th.gov.bc.ca/RWIS/dataDef.htm)는 노면온도보다 이슬점이 높을 때 수분 침착이 가능함을 설명한다. 이 물리 관계를 추정 노면온도−AWS 이슬점 입력의 근거로 사용한다. 다른 국가의 센서·염수 동결점·마찰 경보 기준을 대회 04 정답 정의나 한국 도로 위험 등급으로 옮기지 않는다. 온도 추정 오류와 AWS의 공간 대표성이 남으므로 이 차이 자체를 Ice 정답으로 간주하지 않는다.

[scikit-learn1.6 StackingRegressor](https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.StackingRegressor.html)는 최종 모델 학습에 기본 모델의 교차검증 예측을 사용하며 같은 학습 행의 적합값을 그대로 쓰는 과적합 문제를 설명한다. 본 구현은 기본 StackingRegressor 호출이 아니라 지점 단위 3그룹 및 내부/외부 제외 지점 제한을 직접 구현한 온도→분류 입력 연결이다. 분류 학습 행도 자기 지점 그룹의 온도 정답·전처리에서 제외한다. 두 겨울 중 첫 겨울 공간OOF 단계이므로 각 10분 행의 미래 예보를 재현한 연구라고 주장하지 않는다.


## 기상청 공식 도로관측 API·SFS·지점 목록 — 2026-10-09

[도로기상관측정보 API](https://apihub.kma.go.kr/apiList.do?seqApi=971&seqApiSub=293)는 2024-01-01 이후 조회가 가능하되 지점별 제공 시작이 다르다고 설명한다. 지점 지정mode=1,var=지점번호는 최대 24시간 구간 조회이고, 전체 지점/노선/종류 조회는 시작시각 한 시점만 반환한다. 도로관측의 조회 노선번호 12/23/33과 다른 도로위험정보의 015/025/035는 다른 번호 체계다. 관측 시각은KST이고 도로위험정보ZIP의기준시각UTC와 다르다. 후자의 예측/위험 산출물을 독립 관측 정답으로 사용하지 않는다.

공식 첨부 `도로기상관측지점 목록.pdf`6쪽 전체와 `노면상태 코드.pdf`1쪽의 표를 추출·렌더링해 확인했다. 정적 366개 지점 목록은 관측 기간·과거 센서 상태를 입증하지 않는다.12 chemical wet과 13 critical wet의 설명은 서로 달라, 이전V1의 12/13 통합deicing 요약을 수정한V2를 별도 검증했다.04 양성, 13/15 음성이라는 대회 정답은 바꾸지 않았다. V1은 이전 비교·결합의 재현용으로 보존하며 통합 변수의 이름을 실제 제빙 상태로 해석하지 않는다.

[기상청 출처표시 안내](https://apihub.kma.go.kr/notice.do?seqNotice=57)와 자료 제공 조건을 확인할 위치를 기록했다. 실제 추가 관측자료는 인증키가 없어 받지 않았고, 대회·보호 지점의 추가 동적 관측은 조회하지 않았다. 정적 지점·상태코드 PDF의 공식 URL·SHA256은 수정본 비공개 `external/kma_rwis_reference/manifest.json`에 보존한다.

이 절의 미수집 상태는 API 승인 전 기록이다. 이후 참가자가 `secret.env`에 승인 키를 설정하여 비대회 9개 지점의 첫 겨울을 실제 수집 중이다. 키를 로그·출처 기록·제출 묶음에 넣지 않는다. 원본 관측 응답·정확한 10분 변환·계획 영수증·해시는 수정본 비공개 `external/kma_rwis_development_v1/`에 기록한다. 다음 겨울과 기존 대회 19개 지점은 요청하지 않는다.

## 외부 공간 그룹의 중첩 후보 선택 — 2026-10-09

[Cawley·Talbot(2010), On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation](https://jmlr.org/papers/v11/cawley10a.html), JMLR11(70):2079–2107. 유한 표본의 검증 점수로 반복 선택하면 성능 추정에도 선택 편향이 생길 수 있다는 방법론적 근거다. [scikit-learn1.6 공식 중첩 검증 예제](https://scikit-learn.org/1.6/auto_examples/model_selection/plot_nested_cross_validation_iris.html)도 후보 선택과 외부 평가의 분리를 설명한다.

이를 참고해 첫 겨울 추가 9개 지점의 4개 공간 그룹 중 평가 그룹을 학습·임계값 보정·후보 선택에서 제외하는 절차를 직접 구현했다. 내부 후보 비교에도 해당 내부 검증 그룹을 제외한다. 임계값은 기존 14개 개발 지점의 첫 겨울 공간OOF로 선택하고, 동적 참조는 기존 14개 지점으로 제한한다. 다른 3개 그룹의 동일 정답 행에서FP·FN을 모두 감소시키지 못하면 기준 모델로 돌아간다. 논문과 공식 예제는 이 프로젝트의 도로 결빙 성능 개선을 검증한 자료가 아니다. 실제 증강 모델 학습과 별도 다음 겨울 평가는 아직 수행하지 않았다.

추가 확인: [한국도로공사 공간정보노선현황](https://www.data.go.kr/data/15062048/openapi.do)은 시·종점과 주요 경유지의 기본 좌표를 설명하며 별도 인증이 필요하다. 공개 설명만으로 전체 100m 이정·상하행·과거 선형을 제공한다고 확정할 수 없어 공식 균등구간 근거로 채택하지 않았다. [기상청 도로위험기상정보 안내](https://apihub.kma.go.kr/apiList.do?seqApi=971&seqApiSub=293)는 위험정보ZIP의 서비스 시작을 2025-12-15, 기준시각을UTC로 표시한다. 첫 겨울 전체를 대체하는 관측자료나 실측 Ice 정답으로 사용하지 않는다. 현재 수집하는 매분 도로관측 API와 구분한다.
