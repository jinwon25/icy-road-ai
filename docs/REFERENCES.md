# 공식 자료·선행연구 목록

## 제공 설명서 기반 도로교·보도교·철교 구분 — 2026-10-09

제공 `other_spatial.zip` 내부의 **국토지리정보원 전국 연속수치지형도 데이터베이스설계서 v5.1.1(2014-12-30)를** 직접 확인했다. 3쪽은N3A 교량/터널 면 레이어와1:5,000 목록,21쪽은교량 KIND/QUAL 코드 및EYMD설치연도,22·27쪽은FMTA제작정보 참조(SL_PRODUCT_INFO),27쪽은터널 필드/통합코드다. 해당 공급 버전의 속성 의미를 해석하는 근거이며 최신 고시·현재 구조물 현황·치수 단위·실제 차로 소속의 증명이 아니다.

제공XML의EPSG5179·선형미터·생성20230215·수정/동기화20240419를 기록했으나 처리일을 시설 관측일로 바꾸지 않았다. 설명서·XML 원본과 검토 페이지는 수정본 시설 검토 하위 `road_bridge_kind_review_v1/`에멤버명·SHA256와함께 보존한다. 수평중첩·재질 코드에서 결빙 위험 배점이나 열계수를 만들지 않았다. 원래 도로교·보도교·철교는종류 코드로구분하되층위 교차·인접 차로 불확실성은남는다.

## 방향별 구간의 공식 도로환경 해석 — 2026-10-09

[국토교통부 공식 구축기준 전문](https://www.codil.or.kr/filebank/moct2014/202301/MOCT3000_1.PDF?nserialno=3000)의11쪽에서 LANES=차로수, MAX_SPD=최고 제한속도, UPDATEDATE=구축날짜를 확인했다. 보존한2024-03-25 ZIP의 원본 DBF150링크를 직접 대조해500m/1km 후보별 유형 코드 길이 비중과 차로수·속도 범위를 연결했다. 이2023년 기준은 과거 자료 해석의 근거다. 링크 코드가 정확한 물리적 구조물 경계와 같다는 검증은 별도로 남는다.

[FHWA ESS 센서 배치 지침,2005년](https://ops.fhwa.dot.gov/publications/ess05/ess0503.htm)은 지역 대표 관측과 교량·그늘 등 국지 취약 지점 관측의 목적을 구분한다. 센서 위치가 관측의 대표성에 영향을 주며, 서로 다른 기상 조건에서 열 지도 조사를 설명한다. 이는 추가9지점의 표본 편중·공간 전이 한계를 해석하고 도로환경별 검증을 요구할 근거다. 최신 한국 운영 규정이나 이 프로젝트의 검증된 효과 크기로 취급하지 않는다.

[FHWA 관측 요구사항](https://ops.fhwa.dot.gov/publications/ess05/ess0510.htm)은 노면온도·노면상태·동결점·약품농도 등 관측을 구분한다. [Met Office의 노면온도 안내](https://www.metoffice.gov.uk/services/transport/road/independent-gritting)는 노면온도와 기온이 다를 수 있음을 설명한다. 기온이나 교량 코드 하나로 Ice 정답·운영 위험등급을 대체하지 않는다. 세 원문HTML·수집일·URL·SHA256는 수정본 비공개 `external/road_environment_references_20261009/source_manifest.json`에 보존했다. Met Office 예보 상품은 구독하거나 모델 입력으로 수집하지 않았다.

실험 설계·결과 해석에 참고한 공식 자료와 원 논문을 정리합니다. 참고 자료를 읽은 것과 외부 데이터를 모델 입력으로 수집한 것을 구분합니다.

[문서 목록·용어 풀이](README.md) · [프로젝트 소개](../README.md)

2026-10-08에는 문헌 검토에 더해 **NASA POWER 시간별 복사량과 Copernicus GLO-30 공개 DSM을 수집**했다. 원천 URL·단위·해시·이용 고지는 수정본 작업 공간의 `outputs/private/external/`에 보존했다. NASA 자료는 공개 지연 때문에 사후 추정 실험 전용이다. 논문의 수치를 이 프로젝트의 기대 성능이나 위험도 배점으로 전용하지 않는다.

## 물리·지형 입력 고도화 — 2026-10-08

| 1차 자료 | 확인 및 적용 | 한계 |
| --- | --- | --- |
| [RoadSurf v7.0 논문, FMI, 2024](https://gmd.copernicus.org/articles/17/4837/2024/gmd-17-4837-2024.html), [공식 MIT 소스](https://github.com/fmidev/RoadSurf) | 복사·노면 에너지 수지와 물·얼음 저장량이 중요한 과정임을 확인. 냉각·수분·운량·복사·차폐 특성의 설계 근거 | 완전한 RoadSurf를 이식하거나 제빙제·물 저장량을 재현한 모델은 아님. 소스 열람만 했으며 코드 복제 없음 |
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
| [기상청 AWS 관측자료 항목 설명](https://www.weather.go.kr/wnuri_help/html/observation/aws-table.jsp) | 강수15·강수60은 선택 시각 이전의 누적량, 일강수는 00:01에 초기화. 풍향·풍속의 과거 1·10분 평균 설명 | AWS 15분 강수를 사용하고 일 누적량의 단순 차분을 초기 특징에서 제외. 제공 ZIP의 변수명·단위는 별도 대조 |
| [기상청 ASOS 자료 설명](https://data.kma.go.kr/data/grnd/selectAsosRltmList.do?pgmN=) | ASOS 시간 자료는 매 정시, 품질 플래그 정보가 있을 수 있음 | 1시간 원천과 10분 RWIS의 시각 차이·가용성을 명시. 제공 ZIP에 QC 플래그가 있는지는 독립 점검 |
| [미국 FHWA RWIS 안내](https://ops.fhwa.dot.gov/weather/resources/publications/tech_briefs/rwis.htm) | 기온·노면온도·강수·제빙제 정보를 구분해 도로 상태 판단에 활용 | 노면온도 회귀와 결빙 판정을 분리하고 제빙 관련 상태를 무비판적으로 Ice에 합치지 않음 |
| [Roberts et al. (2017), *Ecography*](https://www.wsl.ch/lud/biodiversity_events/papers/Roberts_et_al-2017-Ecography.pdf) | 공간·시간 구조가 있는 자료의 무작위 행 분할은 새 위치 일반화 평가에 부적합할 수 있음 | RWIS 관측소 단위 LOSO와 겨울 간 시간 검증을 별도 유지 |
| [Ji et al. (2023), 교량 노면온도 추정 연구](https://www.gljtkj.com/EN/abstract/article/1002-0268/10011) | 교량별 환경 차이와 기상 인자의 관계를 보고하고 다른 교량으로의 전이 문제를 다룸 | 교량·지형 특징을 다음 단계의 검증 가설로만 사용. 해당 연구 성능을 이 데이터와 직접 비교하지 않음 |

KMA 웹 도움말은 일반 관측망 설명이다. 이번 대회 제공 CSV의 가공 시점·발표 지연·ASOS 시각대는 별도 메타데이터가 확인될 때까지 잠정 가정이다. 해당 불확실성은 [운영진 질문](QUESTIONS_FOR_ORGANIZER.md)과 [검증 규약](VALIDATION_PROTOCOL.md)에 유지한다.

## 후속 실험 사례의 추가 1차 자료 — 2026-09-23 확인

| 자료 | 확인한 내용 | 이 프로젝트의 적용 범위와 한계 |
| --- | --- | --- |
| [FHWA RWIS 관측소 입지 지침 §2](https://ops.fhwa.dot.gov/publications/ess05/ess0502.htm), 2005 | 지역 대표 관측소와 특정 교량·짧은 구간을 대표하는 국지 관측소를 구분하고 다른 관측망의 보완 활용을 설명 | AWS 2·3순위 대체와 RWIS 대표성 검증의 설계 근거. 대체 AWS가 자동으로 정확하다는 증거는 아님 |
| [FHWA 입지 지침 §3](https://ops.fhwa.dot.gov/publications/ess05/ess0503.htm), [§4](https://ops.fhwa.dot.gov/publications/ess05/ess0504.htm), 2005 | 저지대·교량·음영 및 센서 설치 위치·물고임에 따른 관측 영향 | 단일 시각 Ice 사건의 품질 검토와 정적 특징의 근거. 원시 정답을 자동 제외하는 기준은 아님 |
| [FHWA, Michigan Finds a Solution for Icy Bridges](https://ops.fhwa.dot.gov/weather/resources/publications/tech_briefs/cs037.htm), FHWA-SA-96-045 | 교량 상판이 인접 도로보다 먼저 얼 수 있고 RWIS로 노면온도·습윤 상태·기상을 함께 관측한 사례 | 교량 특징 실험 가설. 전북도 교량의 효과 크기나 위험 배점으로 전용하지 않음 |
| [FHWA, Nebraska Bridge Prioritization](https://ops.fhwa.dot.gov/publications/fhwahop16093/ch7.htm), 제7.5절 | 사고·교통·기상·교량·유지관리 자료를 결합한 제빙 설비 우선순위 사례 | 사고·교통 정보가 없는 본 프로젝트의 결빙 취약도와 사고 위험을 구분할 근거 |
| [Bogren, Gustavsson & Postgård, International Journal of Climatology 20 (2000)](https://rmets.onlinelibrary.wiley.com/doi/abs/10.1002/%28SICI%291097-0088%28200002%2920%3A2%3C151%3A%3AAID-JOC460%3E3.0.CO%3B2-U) | 국지 노면온도 차이와 지형·구름·바람·일사 조건의 관계를 분석한 원 논문 | DEM 기반 상대고도와 기상 조건 상호작용 가설. 스웨덴 계수·임계값을 직접 사용하지 않음 |
| [Bogren 등, Meteorological Applications 7 (2000)](https://rmets.onlinelibrary.wiley.com/doi/10.1017/S135048270000150X) | 차광 노면과 일사 노출 노면의 온도 차이와 해 진 뒤 지속을 분석한 원 논문 | 실제 계산 가능한 음영 특징이 확보될 때만 시험 |
| [기상청 2023.11.15 도로살얼음 발생 가능 정보 보도자료](https://www.weather.go.kr/kma/servlet/NeoboardProcess?bid=press&callback=https%3A%2F%2Fwww.kma.go.kr%2Fkma%2Fnews%2Fpress.jsp&fno=3&k=ATC202311150847023_69dc0f63-f58c-4954-aeca-7ff79d4b4293.pdf&mode=download&num=1194292&ses=USERSESSION) | AWS 강수·도로기상 기온·노면상태 등을 융합해 관심/주의/위험 정보를 제공한 공식 서비스 사례 | 정보 활용 예시일 뿐, 본 대회 Ice 코드·일별 F1·구간 위험도 기준과 동일하지 않음 |

위 9월 23일 작업 당시에는 문헌 열람만 수행했다. 10월 8일 외부 자료 추가 현황은 이 문서 상단과 [후속 실험 근거](FOLLOWUP_EVIDENCE.md)에 별도로 기록했다. 외부 업로드·공개는 하지 않았다.


## 이정·좌표의 독립 교차 검토 자료 — 2026-10-09

- [한국도로공사 본선 도로관리용 CCTV 현황 20260423](https://www.data.go.kr/data/15102134/fileData.do): 노선명·CCTV명·이정·방향 등2,999행. 포털 이용허락범위 제한 없음. 좌표 및 공통 CCTV ID가 없어 별도 지도와 유일한 이름 후보만 교차 점검한다.
- [한국도로공사 ROADPLUS](https://www.roadplus.co.kr/main)와 [공개 CCTV GeoJSON](https://www.roadplus.co.kr/geojson/EX_CCTV.geojson): 홈페이지가 쓰는3,838개 좌표. 이름 중복과 잘못된 위치 가능성을 점검하고 재배포 조건 미확인으로 비공개 검증에만 사용한다.
- [서울시립대 교통안전 DB 연구 지도](https://traffic-viewer.urbanscience.uos.ac.kr/): 공개 UI 소스의100m급 RoutePath를 기하 참조로만 사용. 단위·노선명 오류와 공식 기준점 이정 차이를 발견하여 공식 선형으로 채택하지 않았다.

자료 수집 날짜2026-10-09와 해시는 수정본 비공개 출처 manifest 및 기준점 summary에 기록했다. 공식 현재 CCTV 현황은 과거 두 겨울의 선형이나 제공 도형의 차로·상하행을 검증하지 않는다.


## 최근 냉각 누적의 추가 개발 비교 — 2026-10-09

[Yi·Seo(2026), Early warning of road icing from antecedent meteorological conditions without consistent critical slowing down](https://arxiv.org/abs/2609.33528), 2026-09-27 공개 프리프린트. [저자 공개 코드](https://github.com/yunam-seo/road-icing-forced-threshold)는 MIT 라이선스이며 검토 커밋은 `5552934b22dc25be07839fc53fe757a7d136b072`다. 원자료는 저장소에서 재배포되지 않는다. 저자 관측자료를 새 독립 검증 자료로 확보했다고 주장하지 않는다.

최근 냉각·서리점 대비 온도차·영도 교차를 지수 감쇠 누적으로 나타내는 개념에서 착안했다. 우리 구현은20·60분 감쇠, 10분 간격의 구간 상수 입력 정확 적분, 유효 관측 가중 커버리지80% 조건과 공백 시 교차 연결 차단을 사용한다. 이는 논문의1분 발생 예보와 다르고, 자기 관측 대신 다른 개발 지점의 과거 관측을 쓴다. 대회04 양성 정의를 유지하며 논문의04/15 양성·사건 병합·온도 품질 필터를 대회 정답에 적용하지 않았다. 논문 성능 수치는 우리 성능으로 옮기지 않는다.

원본 공개 코드·LICENSE·고정 URL/해시는 수정본 비공개 `external/antecedent_reference/manifest.json`에 보존했다. 수치 결과는 `antecedent_forward/summary.json`과 [진행 보고](PROJECT_STATUS.md)를 확인한다.


## 규제 선형·가법 스플라인 비교의 구현 근거 — 2026-10-09

설치된scikit-learn1.6.1의 [LogisticRegression 공식 문서](https://scikit-learn.org/1.6/modules/generated/sklearn.linear_model.LogisticRegression.html)와 [SplineTransformer 공식 문서](https://scikit-learn.org/1.6/modules/generated/sklearn.preprocessing.SplineTransformer.html)를 확인했다. L2 규제C=0.1·양성 가중치20을 사전에 고정하고, 같은40개 열·수분 입력에서 선형과4변수의 가법 스플라인을 비교한다. 스플라인은2차·5개 물리 단위 매듭·선형 외삽이며, 매듭은 검증 정답이나 분포에서 선택하지 않았다. 중앙값 대체·결측 표시·스케일링은 각 학습 분할 안에서 처리하고 수렴 경고는 실패로 취급한다.

고도를 제외했으므로41입력의 기존HGB와의 차이를 모두 분류기 구조 효과로 주장하지 않는다. 선형/스플라인 사이는 같은 입력이다. 가중 학습 점수와 상관된 입력의 계수는 실제 결빙 확률이나 독립 물리 효과가 아니다. 결과는 수정본 `regularized_forward/summary.json`과 [진행 보고](PROJECT_STATUS.md)에 기록한다.


## 다른 지점의 과거 노면상태 추가 입력 — 2026-10-09

[공식 답변588](https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=588)과 [공식 답변555](https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=555)를 다시 확인했다. 정답은Ice만 양성이고0/-999는 제외한다. 보호 지점의 추정 대상 실측값을 학습·예측 입력으로 사용하지 않는다. 최신 목록은620·603·588·556·555와 같았으며 재확인 원문·해시는 원본 작업 루트의 비공개 `official_review_20261007/*surface_state*`에 보존했다.

[Yi·Seo(2026)](https://arxiv.org/abs/2609.33528)의 초기 상태·수분 공급 논의에서 착안하되, 다른 지점의 과거 상태가 현재 대상의 상태를 설명하는지는 별도 가설로 검증한다. 현재 상태별10개 표시,60/180분 관측 상태 비율 및 커버리지, 최근 관측Ice의 경과시간을 합친23개 입력이다. 대상·내부/외부 제외·보호 지점은 상태 참조에서 차단한다.13·15는 별도 입력으로 구분하고 양성 정답으로 바꾸지 않는다. 관측 비율은 실제 결빙 지속시간이나 위험 확률이 아니다.


## 온도 추정의 분류 입력 연결 — 2026-10-09

[캐나다 BC 교통부 RWIS 정의](https://www.th.gov.bc.ca/RWIS/dataDef.htm)는 노면온도보다 이슬점이 높을 때 수분 침착이 가능함을 설명한다. 이 물리 관계를 추정 노면온도−AWS 이슬점 입력의 근거로 사용한다. 다른 국가의 센서·염수 동결점·마찰 경보 기준을 대회04 정답 정의나 한국 도로 위험등급으로 옮기지 않는다. 온도 추정 오류와 AWS의 공간 대표성이 남으므로 이 차이 자체를 Ice 정답으로 간주하지 않는다.

[scikit-learn1.6 StackingRegressor](https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.StackingRegressor.html)는 최종 모델 학습에 기본 모델의 교차검증 예측을 사용하며 같은 학습 행의 적합값을 그대로 쓰는 과적합 문제를 설명한다. 본 구현은 기본 StackingRegressor 호출이 아니라 지점 단위3그룹 및 내부/외부 제외 지점 제한을 직접 구현한 온도→분류 입력 연결이다. 분류 학습 행도 자기 지점 그룹의 온도 정답·전처리에서 제외한다. 두 겨울 중 첫 겨울 공간OOF 단계이므로 각10분 행의 미래 예보를 재현한 연구라고 주장하지 않는다.


## 기상청 공식 도로관측 API·SFS·지점 목록 — 2026-10-09

[도로기상관측정보 API](https://apihub.kma.go.kr/apiList.do?seqApi=971&seqApiSub=293)는2024-01-01 이후 조회가 가능하되 지점별 제공 시작이 다르다고 설명한다. 지점 지정mode=1,var=지점번호는 최대24시간 구간 조회이고, 전체 지점/노선/종류 조회는 시작시각 한 시점만 반환한다. 도로관측의 조회 노선번호12/23/33과 다른 도로위험정보의015/025/035는 다른 번호 체계다. 관측 시각은KST이고 도로위험정보ZIP의기준시각UTC와 다르다. 후자의 예측/위험 산출물을 독립 관측 정답으로 사용하지 않는다.

공식 첨부 `도로기상관측지점 목록.pdf`6쪽 전체와 `노면상태 코드.pdf`1쪽의 표를 추출·렌더링해 확인했다. 정적366지점 목록은 관측 기간·과거 센서 상태를 입증하지 않는다.12 chemical wet과13 critical wet의 설명은 서로 달라, 이전V1의12/13 통합deicing 요약을 수정한V2를 별도 검증했다.04 양성,13/15 음성이라는 대회 정답은 바꾸지 않았다. V1은 이전 비교·결합의 재현용으로 보존하며 통합 변수의 이름을 실제 제빙 상태로 해석하지 않는다.

[기상청 출처표시 안내](https://apihub.kma.go.kr/notice.do?seqNotice=57)와 자료 제공 조건을 확인할 위치를 기록했다. 실제 추가 관측자료는 인증키가 없어 받지 않았고, 대회·보호 지점의 추가 동적 관측은 조회하지 않았다. 정적 지점·상태코드 PDF의 공식 URL·SHA256은 수정본 비공개 `external/kma_rwis_reference/manifest.json`에 보존한다.

이 절의 미수집 상태는 API 승인 전 기록이다. 이후 참가자가 `secret.env`에 승인 키를 설정하여 비대회9지점의 첫 겨울을 실제 수집 중이다. 키를 로그·출처 기록·제출 묶음에 넣지 않는다. 원본 관측 응답·정확한10분 변환·계획 영수증·해시는 수정본 비공개 `external/kma_rwis_development_v1/`에 기록한다. 다음 겨울과 기존 대회19지점은 요청하지 않는다.

## 외부 공간 그룹의 중첩 후보 선택 — 2026-10-09

[Cawley·Talbot(2010), On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation](https://jmlr.org/papers/v11/cawley10a.html), JMLR11(70):2079–2107. 유한 표본의 검증 점수로 반복 선택하면 성능 추정에도 선택 편향이 생길 수 있다는 방법론적 근거다. [scikit-learn1.6 공식 중첩 검증 예제](https://scikit-learn.org/1.6/auto_examples/model_selection/plot_nested_cross_validation_iris.html)도 후보 선택과 외부 평가의 분리를 설명한다.

이를 참고해 첫 겨울 추가9지점의4개 공간 그룹 중 평가 그룹을 학습·임계값 보정·후보 선택에서 제외하는 절차를 직접 구현했다. 내부 후보 비교에도 해당 내부 검증 그룹을 제외한다. 임계값은 기존14개 개발 지점의 첫 겨울 공간OOF로 선택하고, 동적 참조는 기존14개 지점으로 제한한다. 다른3개 그룹의 동일 정답 행에서FP·FN을 모두 감소시키지 못하면 기준 모델로 돌아간다. 논문과 공식 예제는 이 프로젝트의 도로 결빙 성능 개선을 검증한 자료가 아니다. 실제 증강 모델 학습과 별도 다음 겨울 평가는 아직 수행하지 않았다.

추가 확인: [한국도로공사 공간정보노선현황](https://www.data.go.kr/data/15062048/openapi.do)은 시·종점과 주요 경유지의 기본 좌표를 설명하며 별도 인증이 필요하다. 공개 설명만으로 전체100m 이정·상하행·과거 선형을 제공한다고 확정할 수 없어 공식 균등구간 근거로 채택하지 않았다. [기상청 도로위험기상정보 안내](https://apihub.kma.go.kr/apiList.do?seqApi=971&seqApiSub=293)는 위험정보ZIP의 서비스 시작을2025-12-15, 기준시각을UTC로 표시한다. 첫 겨울 전체를 대체하는 관측자료나 실측Ice 정답으로 사용하지 않는다. 현재 수집하는 매분 도로관측 API와 구분한다.
