# 변수 사전과 품질 요약

원본 변수의 이름·단위·처리 방식과 결측 현황을 확인하는 사전입니다. 원본 열 이름은 코드와 대조할 수 있도록 그대로 유지했습니다.

아래 수치는 `20260915` 배포본의 초기 품질 점검 결과입니다. `20261007` 수정본의 관측소·분모·결측 변화는 [수정본 검토](OFFICIAL_UPDATE_20261007.md)에서 확인합니다. ‘수치 입력/추정 후보’는 원본 변수의 분류이며, 목표 지점의 실측 노면온도·상태를 그 지점의 예측 입력으로 사용한다는 뜻은 아닙니다.

[문서 목록·용어 풀이](README.md) · [프로젝트 소개](../README.md)

## 표를 읽는 방법

- **원본형 / 처리형:** 원본을 읽은 자료형과 분석할 때의 자료형입니다. `string`은 문자열, `float64`는 실수, `datetime`은 날짜·시각입니다. `candidate`는 사용 후보, `provisional`은 잠정 가정입니다.
- **분모 / 결측토큰 / 숫자 오류:** 점검한 행 수 / 누락을 뜻하는 값의 개수 / 숫자로 바꾸지 못한 값의 개수입니다. 빈 칸은 0이 아니라 해당 통계를 적용하지 않은 항목입니다.
- **KST:** 한국 표준시입니다. `datetime (KST provisional)`은 해당 자료의 시각대를 아직 잠정 가정으로 처리한다는 뜻입니다.

## 변수별 현황

원본 CSV 첫 파일의 실제 열 이름을 기준으로 작성했다. 결측토큰과 숫자 오류는 개발용 RWIS 14개소, ASOS·AWS 전체 행에서 집계했다. 정적 메타데이터 열에는 동적 품질 통계를 적용하지 않았다.

| 자료 | 원본 열 | 원본형 | 처리형 | 역할 | 표기 단위 | 분모 | 결측토큰 | 숫자 오류 |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| RWIS | 관측시각 (KST) | string | datetime (KST provisional) | 시각 | KST |  |  |  |
| RWIS | 관측 지점번호 | string | string | 관측소 ID | 미표기 |  |  |  |
| RWIS | 관측 지점명 | string | string | 관측소명 | 미표기 |  |  |  |
| RWIS | 고속도로 | string | string | 노선 | 미표기 |  |  |  |
| RWIS | 관측소 위도 | string | float64 | 좌표 | 위경도(도) |  |  |  |
| RWIS | 관측소 경도 | string | float64 | 좌표 | 위경도(도) |  |  |  |
| RWIS | 노면상태 | string | string | 분류 정답 | 코드 | 483840 | 35 |  |
| RWIS | 노면온도 (광학) | string | float64 candidate | 수치 입력/추정 후보 | 미표기(광학 센서) | 483840 | 35 | 0 |
| RWIS | 시정 (m) | string | float64 candidate | 수치 입력/추정 후보 | m | 483840 | 35 | 0 |
| RWIS | 습도 (%) | string | float64 candidate | 수치 입력/추정 후보 | % | 483840 | 35 | 0 |
| RWIS | 일 누적 강수량 (mm) | string | float64 candidate | 수치 입력/추정 후보 | mm | 483840 | 35 | 1219 |
| RWIS | 적설 (cm) | string | float64 candidate | 수치 입력/추정 후보 | cm | 483840 | 35 | 1534 |
| RWIS | 기온 (C) | string | float64 candidate | 수치 입력/추정 후보 | C | 483840 | 35 | 1268 |
| RWIS | 1분 풍향 (Degree) | string | float64 candidate | 수치 입력/추정 후보 | Degree | 483840 | 35 | 1223 |
| RWIS | 1분 풍속 (m/s) | string | float64 candidate | 수치 입력/추정 후보 | m/s | 483840 | 35 | 1306 |
| RWIS | 최대순간풍향 (Degree) | string | float64 candidate | 수치 입력/추정 후보 | Degree | 483840 | 35 | 1228 |
| RWIS | 최대순간풍속 (m/s) | string | float64 candidate | 수치 입력/추정 후보 | m/s | 483840 | 35 | 1280 |
| RWIS | 해면기압 (hPa) | string | float64 candidate | 수치 입력/추정 후보 | hPa | 483840 | 35 | 0 |
| RWIS | 운고 1 | string | float64 candidate | 수치 입력/추정 후보 | 미표기 | 483840 | 35 | 0 |
| RWIS | 운고 2 | string | float64 candidate | 수치 입력/추정 후보 | 미표기 | 483840 | 35 | 0 |
| RWIS | 운고 3 | string | float64 candidate | 수치 입력/추정 후보 | 미표기 | 483840 | 35 | 0 |
| RWIS | 운량 | string | float64 candidate | 수치 입력/추정 후보 | 미표기 | 483840 | 35 | 0 |

| 자료 | 원본 열 | 원본형 | 처리형 | 역할 | 표기 단위 | 분모 | 결측토큰 | 숫자 오류 |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| ASOS | Unnamed: 0 | string | string | 원본 행 인덱스 | 미표기 |  |  |  |
| ASOS | 시간 | string | datetime (KST provisional) | 시각 | 미표기 |  |  |  |
| ASOS | 지점 | string | string | 관측소 ID | 미표기 |  |  |  |
| ASOS | 지점명 | string | string | 관측소명 | 미표기 |  |  |  |
| ASOS | 위도 | string | float64 | 좌표 | 위경도(도) |  |  |  |
| ASOS | 경도 | string | float64 | 좌표 | 위경도(도) |  |  |  |
| ASOS | 기온(°C) | string | float64 candidate | 수치 입력/추정 후보 | °C | 57600 | 54 | 0 |
| ASOS | 강수량(mm) | string | float64 candidate | 수치 입력/추정 후보 | mm | 57600 | 54347 | 0 |
| ASOS | 풍속(m/s) | string | float64 candidate | 수치 입력/추정 후보 | m/s | 57600 | 106 | 0 |
| ASOS | 풍향(16방위) | string | float64 candidate | 수치 입력/추정 후보 | 16방위 | 57600 | 106 | 0 |
| ASOS | 습도(%) | string | float64 candidate | 수치 입력/추정 후보 | % | 57600 | 113 | 0 |
| ASOS | 증기압(hPa) | string | float64 candidate | 수치 입력/추정 후보 | hPa | 57600 | 114 | 0 |
| ASOS | 이슬점온도(°C) | string | float64 candidate | 수치 입력/추정 후보 | °C | 57600 | 115 | 0 |
| ASOS | 현지기압(hPa) | string | float64 candidate | 수치 입력/추정 후보 | hPa | 57600 | 77 | 0 |
| ASOS | 해면기압(hPa) | string | float64 candidate | 수치 입력/추정 후보 | hPa | 57600 | 79 | 0 |
| ASOS | 일조(hr) | string | float64 candidate | 수치 입력/추정 후보 | hr | 57600 | 30650 | 0 |
| ASOS | 일사(MJ/m2) | string | float64 candidate | 수치 입력/추정 후보 | MJ/m2 | 57600 | 44074 | 0 |
| ASOS | 적설(cm) | string | float64 candidate | 수치 입력/추정 후보 | cm | 57600 | 50069 | 0 |
| ASOS | 3시간신적설(cm) | string | float64 candidate | 수치 입력/추정 후보 | cm | 57600 | 57522 | 0 |
| ASOS | 전운량(10분위) | string | float64 candidate | 수치 입력/추정 후보 | 10분위 | 57600 | 100 | 0 |
| ASOS | 중하층운량(10분위) | string | float64 candidate | 수치 입력/추정 후보 | 10분위 | 57600 | 355 | 0 |
| ASOS | 운형(운형약어) | string | string | 범주 입력 | 운형약어 | 57600 | 54744 |  |
| ASOS | 최저운고(100m) | string | float64 candidate | 수치 입력/추정 후보 | 100m | 57600 | 30511 | 0 |
| ASOS | 시정(10m) | string | float64 candidate | 수치 입력/추정 후보 | 10m | 57600 | 203 | 0 |
| ASOS | 현상번호(국내식) | string | string | 범주 입력 | 국내식 | 57600 | 56133 |  |
| ASOS | 지면온도(°C) | string | float64 candidate | 수치 입력/추정 후보 | °C | 57600 | 310 | 0 |
| ASOS | 5cm 지중온도(°C) | string | float64 candidate | 수치 입력/추정 후보 | °C | 57600 | 46087 | 0 |
| ASOS | 10cm 지중온도(°C) | string | float64 candidate | 수치 입력/추정 후보 | °C | 57600 | 46109 | 0 |
| ASOS | 20cm 지중온도(°C) | string | float64 candidate | 수치 입력/추정 후보 | °C | 57600 | 46087 | 0 |
| ASOS | 30cm 지중온도(°C) | string | float64 candidate | 수치 입력/추정 후보 | °C | 57600 | 46109 | 0 |

| 자료 | 원본 열 | 원본형 | 처리형 | 역할 | 표기 단위 | 분모 | 결측토큰 | 숫자 오류 |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| AWS | 시간(KST) | string | datetime (KST provisional) | 시각 | KST |  |  |  |
| AWS | 지점 번호 | string | string | 관측소 ID | 미표기 |  |  |  |
| AWS | 지점명 | string | string | 관측소명 | 미표기 |  |  |  |
| AWS | 위도 | string | float64 | 좌표 | 위경도(도) |  |  |  |
| AWS | 경도 | string | float64 | 좌표 | 위경도(도) |  |  |  |
| AWS | 1분 평균 풍향(degree) | string | float64 candidate | 수치 입력/추정 후보 | degree | 1077128 | 285823 | 0 |
| AWS | 1분 평균 풍속(m/s) | string | float64 candidate | 수치 입력/추정 후보 | m/s | 1077128 | 285824 | 0 |
| AWS | 최대 순간 풍향(degree) | string | float64 candidate | 수치 입력/추정 후보 | degree | 1077128 | 285825 | 0 |
| AWS | 최대 순간 풍속(m/s) | string | float64 candidate | 수치 입력/추정 후보 | m/s | 1077128 | 285825 | 0 |
| AWS | 10분 평균 풍향(degree) | string | float64 candidate | 수치 입력/추정 후보 | degree | 1077128 | 285825 | 0 |
| AWS | 10분 평균 풍속(m/s) | string | float64 candidate | 수치 입력/추정 후보 | m/s | 1077128 | 285829 | 0 |
| AWS | 1분 평균 기온(°C) | string | float64 candidate | 수치 입력/추정 후보 | °C | 1077128 | 285829 | 0 |
| AWS | 강수감지(0-무강수) | string | float64 candidate | 수치 입력/추정 후보 | 0-무강수 | 1077128 | 285830 | 0 |
| AWS | 15분 누적 강수량(mm) | string | float64 candidate | 수치 입력/추정 후보 | mm | 1077128 | 285835 | 0 |
| AWS | 60분 누적 강수량(mm) | string | float64 candidate | 수치 입력/추정 후보 | mm | 1077128 | 285836 | 0 |
| AWS | 12시간 누적 강수량(mm) | string | float64 candidate | 수치 입력/추정 후보 | mm | 1077128 | 285838 | 0 |
| AWS | 일 누적 강수량(mm) | string | float64 candidate | 수치 입력/추정 후보 | mm | 1077128 | 285841 | 0 |
| AWS | 1분 평균 상대습도(%) | string | float64 candidate | 수치 입력/추정 후보 | % | 1077128 | 285846 | 0 |
| AWS | 1분 평균 현지기압(hPa) | string | float64 candidate | 수치 입력/추정 후보 | hPa | 1077128 | 285847 | 0 |
| AWS | 1분 평균 해면기압(hPa) | string | float64 candidate | 수치 입력/추정 후보 | hPa | 1077128 | 285851 | 0 |
| AWS | 이슬점온도(°C) | string | float64 candidate | 수치 입력/추정 후보 | °C | 1077128 | 285858 | 0 |

노면상태 코드의 원본 정의: 01 건조(Dry), 02 젖음(Wet), 03 눈(Snow), 04 결빙(Ice), 10 저시정, 11 노면 위 물 고임, 12 Chemically wet(노면온도 1.5°C 미만·수막이 Damp 이상이며 제빙제 등의 사용으로 결빙 안 됨), 13 Critically wet(노면온도 1.5°C 미만·수막이 Damp 이상이며 결빙이 시작됨), 14 습윤(Damp), 15 물·얼음 판별 불가. 공식 설명에 따라 04만 Ice 양성으로 둔다. 13·15는 별도 비결빙 상태로 유지하고, 빈 값·미정의 코드는 평가에서 제외한다. 2026-10-09 기상청 공식 SFS 표를 재확인해 이전 13 설명에 포함됐던 ‘제빙제 사용으로’ 표현을 바로잡았다. 정답·모델·특징 파일을 변경한 것은 아니다.

RWIS 시정은 m, ASOS 시정은 10m 표기다. ASOS 풍향은 16방위 표기와 수치 값의 관계가 미확인이다. RWIS 노면온도의 광학 표기는 센서 방식이며 온도 단위는 원본 헤더에 명시되지 않았다. 누적 강수량은 자정 초기화를 고려해야 한다.

세부 오류 문자열과 건수는 Git에서 제외된 `outputs/private/full/variable_quality.csv`에 보존했다. 이 사전은 원본 값을 변경하지 않는다.
