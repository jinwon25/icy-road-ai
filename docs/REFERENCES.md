# 외부 1차 자료·선행연구 — 2026-09-23 확인

아래는 해석과 실험 설계에 참고한 공개 자료다. **외부 관측 데이터는 수집하거나 모델 입력에 추가하지 않았다.** 논문의 수치를 이 프로젝트의 기대 성능이나 위험도 배점으로 전용하지 않는다. 이용 조건은 실제 데이터를 수집할 때 별도 확인한다.

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

문헌 링크는 참고용으로 열람했으며 외부 데이터 수집·모델 입력·업로드는 없었다. 원 논문의 서지 정보와 초록으로 확인한 내용은 [후속 실험 설계](FOLLOWUP_EVIDENCE.md)의 가설에만 반영했다.
