"""검증된 도로 기상 추정·구간 적용을 기존 통합 보고서에 덧붙인다."""
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read


WEATHER='''## 4. 미관측 도로의 기온·습도·풍속 추정

노면온도와 별도로 도로에서 관측한 기온·상대습도·1분 풍속을 추정하였다. 허용 23곳 중 실제 세 기상 정답을 제공하는 곳은 13곳이다. 평가 네 지역의 모든 지점을 두 겨울 모두 학습에서 제외했으며, 종합 기상관측이 있는 개발 4곳에서 오차를 비교했다. 보호 3곳과 이미 개봉한 별도 4곳의 정답은 사용하지 않았다.

ASOS 13변수·AWS 5변수와 관측 경과 시간·거리·태양 위치 등을 34특성으로 구성했다. AWS는 15분 이내일 때 우선하고 없으면 ASOS로 대체한다. 이 기준값의 잔차를 절대오차 HGB 300회로 학습했다. 지점·겨울별 총 가중치를 같게 했고, 직접 추정 대조를 포함한 24모형을 고정 비교했다. 지점 번호·해당 도로의 과거 기상 정답·노면온도·Ice는 입력에 없다.

![그림 2. 네 개발 지역 제외 예측의 MAE. 학습 중앙값과 상수 편향 보정까지 비교하며 목표별 단위가 다르다.](../images/weather_transfer_20261031.png)

| 목표 | AWS 우선 MAE | 잔차 HGB MAE | 감소율 |
| --- | --- | --- | --- |
| 기온 (°C) | 1.699319 | 1.323764 | 22.10% |
| 상대습도 (%p) | 6.530284 | 5.875898 | 10.02% |
| 1분 풍속 (m/s) | 0.982751 | 0.563455 | 42.67% |

유효 쌍은 각각 137,630·137,450·137,498개다. 세 목표 모두 각 겨울에서도 MAE가 작았고, 7일 날짜 블록 차이의 97.5백분위는 0 미만이었다. 추가한 학습 중앙값·잔차 상수 대조에도 전체·각 겨울에서 우세했다. 풍속은 더 강한 중앙값 대조 대비 16.94% 개선이다. 추가 대조는 최초 결과를 본 뒤 계획했으며 모델을 다시 선택하지 않았다.

평균 개선이 모든 지표의 개선을 뜻하지 않는다. 풍속 상관 0.579446·R² 0.268789는 국지 변동 설명의 한계를 보여준다. 호남 기온 MAE는 ASOS 단독보다 나빴고 서상 기온 RMSE·전체 습도 BIAS도 악화한 비교가 있다. 자세한 BIAS·MAE·RMSE·상관은 목표·겨울·지역별 126행 CSV에 제공한다. 같은 개발 지역을 재사용한 결과이며 새로운 독립 성능이 아니다.

기상별 잔차 보정과 공간 대표성은 최근 연구[10–13]를 참고했다. 최근 도로 정답 오차를 쓰는 기존 연구의 입력은 미관측 지점에 사용할 수 없어 가져오지 않았다. 세 모형은 별도 기상 보완 기능으로 채택했다. 전체 13곳 적합·추론을 별도 경로로 이전해 재실행했으며, 세 모델의 재학습 결과도 정확히 재현했다.
'''


def main():
    old=(ROOT/'docs/delivery/ANALYSIS_REPORT_20261031.md').read_text(encoding='utf8')
    pages=old.split('<!-- page -->');assert len(pages)==13
    for i,page in enumerate(pages):
        for number in range(10,3,-1):
            new=number+1 if number<=8 else number+2
            page=re.sub(r'^## '+str(number)+r'\.', '## '+str(new)+'.',page,flags=re.M)
        pages[i]=page
    pages[0]=pages[0].replace('미관측 고속도로 구간의 노면온도 추정과 결빙 탐지','미관측 고속도로 구간의 기상·노면온도 추정과 결빙 조건')
    pages[0]=pages[0].replace('노면온도를 추정하고, 결빙 탐지와 공간적 활용 가능성을 별도로 평가하였다.',
        '노면온도를 추정하고, 도로 기온·습도·풍속 추정을 별도 개발하였다. 결빙 탐지와 공간적 활용 가능성도 구분해 평가하였다.')
    pages[0]=pages[0].replace('반면 유지한 결빙 판정',
        '새 기상 보완 모형은 개발 4지역 제외 비교에서 AWS 우선 기준 대비 기온·습도·풍속 MAE를 각각 22.10·10.02·42.67% 줄였다. 반면 유지한 결빙 판정')
    pages[0]=pages[0].replace('| 결빙을 기온 기준선보다 잘 탐지하는가?',
        '| 도로 기상을 더 잘 추정하는가? | 기온·습도·풍속의 평균 오차 감소 | 기상 정답이 있는 개발 4곳 비교 |\n| 결빙을 기온 기준선보다 잘 탐지하는가?')
    pages[0]=re.sub(r'\*\*읽는 순서\.\*\*.*?수치는',
        '**읽는 순서.** 1–2절은 자료·검증 설계, 3–4절은 온도·기상 추정 개선, 5–7절은 결빙 한계와 미채택 실험, 8–10절은 공간 비교·새 기상 지도, 11–12절은 한계·재현 절차이다. 수치는',pages[0])
    pages[5]=pages[5].replace('그림 2.','그림 3.')
    pages[7]=pages[7].replace('그림 3.','그림 4.')
    transfer='''
### 개선된 기온을 결빙 판정에 쓰면 좋아지는가?

지역 제외 기온 추정값이 0°C 이하이면 결빙으로 판정하는 한 가지 정책을 별도 고정했다. 일별 평균 F1은 0.036601에서 0.035825로 하락했고, 기준선이 탐지한 330사건 중 38사건을 잃고 8사건을 얻어 300사건만 탐지했다. 두 겨울 F1도 모두 감소했다. 기상 추정 개선을 결빙 개선으로 대신하지 않으며 이 정책은 채택하지 않았다.
'''
    projection=ROOT/'outputs/private/weather_segment_projection_20261031_v1'
    s=read(projection/'summary.json');audit=read(projection/'independent_verification.json')
    assert audit['status']=='passed'
    mapping=f'''## 10. 세 기상 변수의 500m 구간 적용

채택한 세 기상 모형을 방향별 843개 500m 구간 중점에 적용했다. 두 겨울 240일의 10분 추정값 {s['ten_minute_rows']:,}행을 계산하고, 구간·겨울 요약 1,686행과 일별 요약 {s['daily_rows']:,}행을 만들었다. 지도는 겨울 평균이며 구간 간 실제 정확도나 극한값을 검증한 결과는 아니다.

![그림 5. 세 기상 모형을 구간 중점에 적용한 두 겨울 평균. 같은 변수는 동일 색 범위로 비교한다.](../images/weather_projection_20261031.png)

가까운 ASOS와 순서가 고정된 AWS 후보 세 곳의 조합은 {s['source_candidate_sets']}개다. 세 기상값은 위치·태양 조건도 사용하지만 도로 분할마다 독립 관측이 있는 것은 아니다. 기존 노면온도·저온 수분 조건 노출은 보존하고 새 기상 통계와 나란히 연결했다. 새 위험등급·결빙확률을 부여하지 않았다.

{s['new_asos_source_segments']}구간은 도로 기상 학습에 등장하지 않은 ASOS 172 출처를 사용한다. 지도에 검은 점으로 구별하고 출처·입력 범위 이탈을 CSV에 남겼다. 범위 이탈은 학습 입력의 최솟값·최댓값을 벗어난 값의 존재이며 예측오차·확률·통계적 신뢰도를 뜻하지 않는다. 이 범위에서는 현장 검증이 특히 필요하다.

일별 자료에는 세 추정 평균과 각각의 유효 10분 수를 제공한다. 겨울 요약에는 분위수·세 변수 간 상관·상관 유효 쌍 수를 포함한다. GeoPackage 두 레이어와 CSV로 확인할 수 있으며, 추정값끼리의 상관을 실제 결빙의 영향 인자나 인과 효과로 해석하지 않는다. 전량 집계 검산·대표 구간 모형 재추론·기존 값 보존을 확인했다.
'''
    pages[10]=pages[10].replace('13쪽','17쪽').replace('analysis_report_v8.pdf','analysis_report_v9.pdf').replace('submission_review_v8.ipynb','submission_review_v9.ipynb')
    execution='''
### 별도 기상 모형 실행

`research/weather_observation_supplement/README.md`의 순서로 포함 학습 자료·세 저장 모형·환경·노트북을 실행한다. 해당 폴더에서 `python scripts/predict_weather_supplement.py --model model --input data/inference_example.csv --output my_prediction.csv`로 추론한다. 노트북의 `RUN_REFIT=True`는 세 목표를 다시 학습한다. 예제의 144행 일치는 실행 검증이며 성능평가가 아니다. 전체 구간 10분 캐시는 큰 용량 때문에 ZIP에서 제외하고 일별·겨울별 결과와 GIS를 포함한다.
'''
    refs='''## 참고문헌 · 도로 기상 보완 연구

[10] Hieta, L., & Partio, M. (2025). 기온·습도·바람의 운영 예보 편향 보정 연구. *Meteorological Applications*. [원문](https://rmets.onlinelibrary.wiley.com/doi/10.1002/met.70074). 기상 변수별 부스팅 보정과 직접 예보 비교를 참고했다. 원 연구는 NWP·최근 관측 오차와 별도 시간 평가를 사용하므로 미관측 도로에 같은 입력·정확도를 가정하지 않았다.

[11] 전국 일평균 기온의 고도 보정 크리깅 연구 (2026). *Atmosphere*, 17(2), 148. [원문](https://www.mdpi.com/2073-4433/17/2/148). 국내 기상망의 공간 대표성·고도 보정·지점 제외 평가를 참고했다. 일평균·매일 바뀌는 제외 지점은 이 연구의 10분 기상·두 겨울 지역 제외와 다르다. 논문 격자나 고정 감률을 새 모형 입력으로 사용하지 않았다.

[12] Van Wyk de Vries, M., et al. (2024). AtsMOS. *Geoscientific Model Development*, 17, 7629–7643. [원문](https://gmd.copernicus.org/articles/17/7629/2024/). 기상별 통계 보정을 입력·모형·출력 단계로 나누어 재현하는 방식을 참고했다. 관측이 있는 산악 지점의 예보 보정 성능을 이 프로젝트의 성능 근거로 차용하지 않았다.

[13] Shin, et al. (2022). 국내 농업용 고해상도 풍속 연구. *International Journal of Biometeorology*. [원문](https://link.springer.com/article/10.1007/s00484-022-02287-1). 관측 높이·지표 거칠기·지형에 따른 풍속 비교의 한계를 참고했다. 원 연구의 10m에서 3m로의 변환을 RWIS에 적용하거나 도로 관측 높이를 임의로 설정하지 않았다.

### 문헌·외부 자료와 자체 결과를 구별하기

추가 논문 페이지·저자 소속 기관 기록은 2026년 10월 31일 확인했다. 외부 학습 가중치·코드·그림을 복사하지 않았다. 문헌은 방법의 배경이고, 이 프로젝트의 수치 근거는 포함된 지역 제외 예측·비교 집계·검산 기록이다.

공공 기상 관측의 이용 조건과 출처는 기존 자료 기록을 따른다. ASOS 172의 추가 공개 기상 5,762시간을 확보해 지도 입력을 보완했다. 해당 출처가 도로 기상 학습에 없었다는 사실을 별도 표시했다. 도로 관측 정답을 추가 취득한 단계가 아니며 보호 평가 범위를 열지 않았다.
'''
    pages[12]+='''
### 이번 기상 보완의 추적

`research/weather_observation_supplement/`에는 세 모형·448,298행 학습 자료·34특성 정의·재학습 및 추론 노트북·환경·검산 결과를 포함한다. 목표마다 결측 정답을 제외하므로 실제 학습 행 수는 다르다. `research/latest/road_weather_transfer_20261031_v1/`은 24모형 개발 비교, `weather_calibration_controls_20261031_v1/`은 단순 기준선, `transferred_air_icing_20261031_v1/`은 미채택 결빙 정책 근거다. 추가 24적합을 과거 98적합과 합쳐 성공 실험으로 표현하지 않는다.

구간 기상 결과는 `research/latest/weather_segment_projection_20261031_v1/`에 있다. 최종 세 기상 모형의 학습·예제 추론은 포함 자료로 재현했으며, 전체 구간 입력 재구축에는 원 작업 공간 자료가 필요하다. 보호 정답과 인증정보를 제출 묶음에 넣지 않는다.
'''
    weather_a,weather_b=WEATHER.split('유효 쌍은',1)
    weather_b='## 도로 기상 보완: 대조·전이·실행\n\n유효 쌍은'+weather_b+transfer+execution
    pages[9]=pages[9].replace('현재 결과물의 기여는 온도 추정 개선과', '현재 결과물의 기여는 도로 기상·노면온도 추정 개선과')
    new=pages[:4]+[weather_a,weather_b]+pages[4:9]+[mapping]+pages[9:12]+[refs,pages[12]]
    assert len(new)==17
    target=ROOT/'docs/delivery/ANALYSIS_REPORT_V9_20261031.md'
    if target.exists():raise FileExistsError(target)
    target.write_text('\n\n<!-- page -->\n\n'.join(p.strip() for p in new)+'\n',encoding='utf8')
    print('V9 MANUSCRIPT',len(new))


if __name__=='__main__':main()
