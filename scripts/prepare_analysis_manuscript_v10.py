"""기존 분석을 보존하면서 최종 습도 이력과 안정성·실행 검증을 19쪽 원고에 반영한다."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read
from src.data_source import sha256_file as sha


def main():
    target=ROOT/'docs/delivery/ANALYSIS_REPORT_V10_20261101.md'
    if target.exists():raise FileExistsError('Preserve previous v10 manuscript')
    study=ROOT/'outputs/private/weather_humidity_stable_20261101_v1'
    summary=read(study/'summary.json');audit=read(study/'independent_verification.json')
    assert summary['primary_success'] and audit['status']=='passed' and audit['summary_sha256']==sha(study/'summary.json')
    runtime=ROOT/'outputs/private/weather_history_supplement_validation_20261101_v2/receipt.json'
    assert read(runtime)['status']=='weather_history_supplement_verified'
    pages=(ROOT/'docs/delivery/ANALYSIS_REPORT_V9_20261031.md').read_text('utf-8').split('<!-- page -->')
    assert len(pages)==17
    pages[0]=pages[0].replace('분석 기준일 2026년 10월 31일','분석 기준일 2026년 11월 1일')
    pages[0]=pages[0].replace('22.10·10.02·42.67%','22.10·12.91·42.67%')
    pages[0]=pages[0].replace('온도 추정의 개선은 확인되었지만',
        '습도에는 과거 기상 이력을 추가해 기존 기상 모형 대비 지역 제외 MAE를 3.22%, 지역·겨울 동시 제외 MAE를 2.90% 줄였다. 온도·습도 추정의 개선은 확인되었지만')
    pages[0]=pages[0].replace('3–4절은 온도·기상 추정 개선','3–4-3절은 온도·기상 추정 개선과 실행 안정성')
    pages[4]='''## 4. 미관측 도로의 기온·습도·풍속 추정

노면온도와 별도로 도로의 기온·상대습도·1분 풍속을 추정했다. 허용 23지점 중 세 기상 정답이 있는 곳은 13곳이다. 개발 네 지역의 모든 지점을 두 겨울 모두 학습에서 제외하고, 종합 기상관측이 있는 4곳의 오차를 비교했다. 보호 3곳과 이미 개봉한 별도 결빙 4지역의 정답은 사용하지 않았다.

AWS는 15분 이내 과거 관측을 우선하고 없으면 60분 이내 ASOS로 대체했다. 이 기준값의 잔차를 절대오차 HGB 300회로 학습하고 지점·겨울의 총 가중치를 맞췄다. 기온·풍속은 34특성 모형을 유지했다. 습도에는 현재 기상 외에 과거 3시간·24시간 이력을 더한 82특성을 사용했다. 지점 번호·연도·목표 도로의 실제 과거 습도·노면온도·Ice는 모형 특성이 아니다.

![그림 2. 지역 전체 제외에서 AWS 우선 기준과 최종 채택 모형의 MAE. 습도만 과거 이력 모형으로 갱신했으며 목표별 단위가 다르다.](../images/weather_adopted_20261101.png)

| 목표 | AWS 우선 MAE | 채택 모형 MAE | 감소율 |
| --- | --- | --- | --- |
| 기온 (°C) | 1.699319 | 1.323764 | 22.10% |
| 상대습도 (%p) | 6.530284 | 5.686973 | 12.91% |
| 1분 풍속 (m/s) | 0.982751 | 0.563455 | 42.67% |

공통 유효 쌍은 각각 137,630·137,450·137,498개다. 전체 MAE는 유효 행 가중 평균이며 공식 보호 3지점의 성적이 아니다. 지역·겨울별 지표도 함께 제공한다. 풍속 상관 0.579446·R² 0.268789, 일부 지역 기온의 악화 등은 기존 모형의 한계로 유지된다.

최초 34특성 모형은 학습 관측 중앙값·잔차 상수 보정과도 비교했다. 이후 습도 이력의 추가 가치는 이 모형과 직접 비교해 판단했다. 기상별 보정·공간 대표성의 배경은 문헌[10–13]을 참고했으며 문헌 성능을 이 연구의 수치로 사용하지 않았다.
'''
    validation='''## 4-1. 습도 이력의 두 가지 제외 검증

기존 기상 입력 34개에 ASOS·AWS 8변수의 과거 평균·현재값과 평균의 차이·유효 입력 비율을 추가했다. 3시간은 18슬롯 중 6개, 24시간은 144슬롯 중 48개 이상 유효할 때 평균을 제공한다. 이력은 같은 도로의 과거 기상만 사용하고 다른 도로·다른 겨울에서 채우지 않는다. 결측 습도·강수를 0으로 바꾸지 않았다.

첫 검증은 두 겨울의 다른 지역을 학습에 사용해 같은 기간의 미관측 지역을 복원한다. 두 번째는 평가 지역의 두 겨울뿐 아니라 평가 겨울 전체를 학습에서 제외한다. 2024년 겨울로 2025년 겨울을 추정하는 순방향과 반대 방향의 사후 재현을 구분했다. 역방향을 미래 예측 성능으로 해석하지 않는다.

![그림 3. 최종 습도 모형의 두 검증. 왼쪽은 지역·겨울 동시 제외, 오른쪽은 두 겨울을 학습에 포함한 지역 제외이다. 같은 개발 지역을 반복 사용했다.](../images/weather_humidity_stable_20261101.png)

| 검증 조건 | 기존 34특성 MAE | 최종 82특성 MAE | 추가 감소 |
| --- | --- | --- | --- |
| 지역 전체 제외 | 5.875898 | 5.686973 | 3.22% |
| 지역·겨울 동시 제외 | 6.008156 | 5.834129 | 2.90% |

두 조건 모두 전체 MAE 2% 이상 감소, 양 겨울 비악화, 지역 악화 10% 이내, ASOS 기온 ±3°C 구간 비악화, 7일 날짜 블록 차이 상한 0 미만의 사전 기준을 통과했다. 모델 용량·학습 횟수·가중치·창 길이는 비교 중 조정하지 않았다. 같은 개발 자료를 사용했으므로 신규 독립 평가라고 부르지 않는다.
'''
    regions='''## 4-2. 개선 범위와 지역별 한계

지역 제외의 유효 137,450쌍에서 습도 RMSE는 7.950451→7.747100%p, BIAS는 +2.446025→+2.061275%p, R²는 0.841654→0.849650으로 변했다. 평균 오차와 편향은 줄었지만 양의 편향은 남아 있다. 첫·둘째 겨울 MAE는 각각 5.974275→5.810189%p, 5.777153→5.563298%p로 감소했다.

| 개발 지역 | 기존 MAE (%p) | 최종 MAE (%p) | 변화 |
| --- | --- | --- | --- |
| 호남 백양 | 4.939195 | 4.528809 | 8.31% 감소 |
| 서해안 서천 | 5.513134 | 5.576702 | 1.15% 증가 |
| 통영 금산 | 5.119334 | 4.965218 | 3.01% 감소 |
| 통영 서상 | 7.917464 | 7.663631 | 3.21% 감소 |

모든 지역에서 개선된 것은 아니다. 서천의 소폭 악화는 사전 허용 범위 안이지만 그대로 보고한다. 서상은 MAE 7.663631%p·BIAS +6.772757%p로 오차가 가장 크다. 고도·관측 높이·센서 교정·미세 환경을 추가 검증해야 하며, 이 비교만으로 도로별 습도 정확도를 보장할 수 없다.

ASOS 기온이 ±3°C인 공통 51,142쌍의 MAE는 5.841444→5.610078%p로 3.96% 감소했다. 목표 습도가 아닌 같은 입력 기온으로 범위를 정했다. 이 저온 구간의 개선도 결빙 분류 정확도 향상은 아니다.

7일 날짜 블록 2,000회 재표집에서 MAE 차이의 2.5–97.5백분위는 지역 제외 [−0.227743, −0.152968]%p, 지역·겨울 동시 제외 [−0.216418, −0.135412]%p였다. 이는 기존 네 지역에 조건부인 날짜 구성 민감도이며 새 지역 모집단의 신뢰구간이 아니다. 지점 수를 500m 지도 구간 수로 늘려 해석하지 않는다.

기온 이력은 지역 제외 개선 0.37%와 첫 겨울 악화, 풍속 이력은 지역·겨울 동시 제외의 악화로 채택하지 않았다. 이력이라는 방법을 세 목표에 일괄 적용하지 않고 습도에만 사용했다.
'''
    numeric='''## 4-3. 수치 안정성과 독립 실행 검증

첫 실행 묶음을 실제 추론할 때 같은 24시간 입력 앞에 더 오래된 기상을 붙이면 432행 중 4행의 습도 추정이 달라졌다. 최대 차이는 약 0.117%p였다. 과거 창 평균의 약 10⁻¹³ 수준 부동소수점 차이가 나무 분기에서 증폭되는 문제로 진단했다. 예측 비교의 허용오차를 넓혀 통과시키지 않았다.

최종 구현은 결측 시각을 10분 달력에 놓고 각 18·144슬롯 창을 독립 합산한다. 창보다 앞선 누적 보상 상태를 이어받지 않고 값을 반올림하지 않는다. 이 계산으로 지역·겨울 8개와 지역 4개 모형을 다시 학습해 앞의 결과를 얻었다. 65,152,690개 특성 값의 수학적 동치, 188,928개 문맥 변경 특성 값의 비트 단위 일치와 대표 4개 모형의 정확한 재학습을 검산했다.

| 실행 검사 | 확인한 내용 |
| --- | --- |
| 최종 적합 | 허용 기상 정답 13곳·유효 447,794행으로 습도 재학습 |
| 과거 문맥 | 48시간 입력과 더 긴 전체 과거 입력의 선택일 432행 차이 0 |
| 별도 위치 | 폴더 복제 후 실제 CLI 432행·Jupyter 3코드 셀 실행 |
| 전체 재학습 | 포함 자료로 습도 전체 재학습 후 432행 추론 정확히 일치 |
| 기존 성분 | 기온·풍속 저장 모형과 동일 정규 입력의 추론값 보존 |

출력일 앞의 24시간 기상을 입력에 포함하고 추론 후 출력 구간을 선택한다. 입력을 먼저 출력일로 자르면 필요한 이력을 잃는다. `humidity_history_status`는 제공 입력의 충실도, `humidity_history_outside_training_range`는 학습 최솟값·최댓값 범위 이탈이다. 두 값은 오차·신뢰구간·결빙확률을 뜻하지 않는다.

새 묶음은 `research/weather_history_supplement/`에 학습 자료·저장 모형·버전 고정 환경·재학습 및 추론 노트북을 포함한다. 설치 후 GPU·외부 AI API·인증정보 없이 실행한다. 예제는 학습 범위 내 재현 검사이며 성능 평가에 사용하지 않는다. 기존 기온 추정의 0°C 결빙 정책은 앞선 비교에서 F1 하락·38사건 손실로 미채택했고, 이번 습도 개선으로 결빙 성능이 올랐다고 주장하지 않는다.
'''
    pages[11]=pages[11].replace('../images/weather_projection_20261031.png','../images/weather_projection_20261101.png')
    pages[11]=pages[11].replace('채택한 세 기상 모형을','기온·풍속을 유지하고 새 습도 이력 모형을 포함한 세 기상 추정기를')
    pages[11]=pages[11].replace('전량 집계 검산·대표 구간 모형 재추론·기존 값 보존을 확인했다.',
        '새 습도 전량 집계·대표 19구간 API 재추론과 기존 기온·풍속·노면온도·조건 노출 보존을 검산했다. 과거 입력 부족과 새 습도 특성 범위 이탈도 따로 기록했다.')
    pages[13]=pages[13].replace('17쪽','19쪽').replace('analysis_report_v9.pdf','analysis_report_v10.pdf').replace('submission_review_v9.ipynb','submission_review_v10.ipynb')
    start=pages[13].find('### 별도 기상 모형 실행')
    if start>=0:
        pages[13]=pages[13][:start]+'''### 별도 기상 모형 실행

현재 기상 추론은 `research/weather_history_supplement/README.md`를 따른다. 해당 폴더에서 `python scripts/predict_weather_history.py --input data/weather_context_example.csv --output my_weather.csv --output-start 2024-12-15 --output-end 2024-12-16`으로 과거 문맥을 포함해 432행을 산출한다. 노트북의 `RUN_REFIT=True`는 최종 습도 모형을 전체 재학습한다. 기존 기온·풍속과 비교용 습도 모형의 재학습 자료도 앞선 기상 보완 폴더에 보존했다.

전체 구간 10분 캐시는 원 비공개 작업 공간에 두고 ZIP에는 일별·겨울별 집계와 GIS를 포함한다. 기본 실행과 최종 습도 전체 재학습은 포함 자료로 가능하다. 전체 원천 자료 재수집과 모든 과거 연구의 재실행은 별도 권한·원 작업 공간을 필요로 한다.
'''
    pages[13]='\n\n## 12. 재현과 산출물 안내\n\n실행 환경은 Windows·Python 3.11·CPU이다. GPU나 외부 예측 API는 필요하지 않다. 주요 라이브러리 버전은 포함된 `requirements.txt`와 `requirements-notebook.txt`에 고정하였다. 최초 의존성 설치에는 패키지 접근이 필요하며, 설치 후 예제 추론과 최종 모델 재학습은 포함 자료를 사용한다.\n\n| 확인할 내용 | 제출 검토 묶음 안의 경로 |\n| --- | --- |\n| 현재 보고서 | reports/analysis_report_v10.pdf |\n| 모델·학습 계획 | model/ · extended_training_plan.json |\n| 학습·추론 진입점 | code/train.py · code/predict.py |\n| 실행 노트북 | notebooks/submission_review_v10.ipynb |\n| CSV·공간 결과 | exports/ · figures/ |\n| 구간 탐색·조작 영상 | demo/review/index.html · demo/review_walkthrough.webm |\n| 공식 목록 비교 화면 | research/latest/official_inventory_viewer_20261031_v1/index.html |\n| 추론 출력 시각화 | demo/extended_inference.mp4 |\n| 현재 기상 학습·추론 | research/weather_history_supplement/README.md |\n| 자료 이용·AI 지원 | licenses/ · AI_USAGE.md |\n\n묶음 루트에서 아래 순서로 실행한다. 검사 결과는 원래 파일과 분리된 `local_review/`에 저장한다. 기존 결과 파일이 있으면 새 출력 이름을 사용한다.\n\n```powershell\npython -m pip install -r requirements-notebook.txt\npython scripts/review_submission_bundle.py\npython scripts/review_submission_bundle.py --smoke --output local_review/smoke.json\n```\n\n새 습도는 위 기상 폴더의 README·노트북을 따른다. 출력일 앞의 24시간 기상을 함께 넣고 추론 후 날짜를 선택한다. 예제 432행·전체 재학습 일치는 별도 검증했으며 기온·풍속은 기존 모형을 사용한다.\n\n첫 검사는 파일 목록·크기·해시·경로를 확인한다. 실행 검사는 기존 예측 144행·노트북 5코드 셀을 확인한다. 예제는 독립 성능평가가 아니며 전체 연구 탐색은 원 비공개 입력이 추가로 필요하다.\n\n보호 3지점 예측은 103,680행이며 입력 부족 18행을 NA로 유지한다. CSV의 `estimated_road_temp_c`는 현재 온도 추정값, `icing_reference_temperature_c`는 결빙 판정에 실제 사용한 별도 온도이다. 모델 간 차이가 0이라는 값은 예측오차 0을 뜻하지 않는다. 상세 단위·집계 규약은 [CSV 설명](CSV_CONTRACT.md)에 있다.\n\n### 제출 준비 상태\n\n10월 27일 공식 공지는 결과물 접수 개시를 안내했고 제출 화면에는 문서자료와 모델자료의 별도 ZIP 업로드 칸이 있다. 자료는 각각 하나의 최상위 폴더로 압축한다. 제공 공지 본문에는 마감 날짜가 없어 미확인이며 11월 6일 참가신청 종료일로 대신 확정하지 않는다. 일부 미정의 지표 규약은 추가 확인이 필요하다. 이 묶음은 비공개 검토 후보이며 대회 접수 완료본이 아니다[5, 6].\n\n'
    pages[16]='''## 수치 추적과 AI 활용

### 수치의 추적 경로

노면온도는 `research/extended/selection.json`, 기존 결빙은 `research/extended/audit.json`, 새 4지역은 `research/latest/blind_icing_20261025_v2/summary.json`에 연결된다. 보고서 생성 영수증에 원고·그림·수치 근거의 해시를 기록했다.

`research/latest/`에는 목적함수 40회, 재분석 온도 8회·분류 30회, 누적 조건 20회의 비교·검산을 보존한다. 공식 목록·위치 비교는 `official_chainage_alignment_20261031_v1`, `vulnerability_map_comparison_20261031_v1`, `official_inventory_viewer_20261031_v1`에서 방향별 8개 연속 구간·동률·위치 오차를 확인한다. 원천 입력 구축과 모든 연구 재실행에는 원 비공개 작업 공간 자료가 추가로 필요하다.

### 현재 기상 모형과 실행 증거

앞선 `research/weather_observation_supplement/`는 기존 34특성의 세 기상 모형·448,298행 자료·재학습 코드를 보존한다. 초기 공간 비교·단순 보정·실패한 기온 결빙 정책은 `road_weather_transfer_20261031_v1`, `weather_calibration_controls_20261031_v1`, `transferred_air_icing_20261031_v1`에서 확인한다.

최종 습도는 `weather_humidity_stable_20261101_v1`의 8+4 제외 모형·지표·독립 검산을 따른다. 초기 구현의 문맥 의존 사례와 실패 묶음도 보존했다. 적합 수 카운터·완료 기록 키 참조는 학습·선택 기준을 바꾸지 않고 고쳤으며 수정 전 소스와 최소 변경 대조를 남겼다. 수정 전 수치를 최종 성과로 합산하지 않았다.

현재 실행 폴더는 `research/weather_history_supplement/`이다. `validation/weather_history_full_refit.json`은 별도 위치 CLI·실제 Jupyter 전체 재학습의 432행 일치 근거다. 현재 지도는 `research/latest/weather_history_segment_projection_20261101_v1/`의 전량 집계·기존 성분 보존·대표 재추론을 따른다. 전체 구간 10분 캐시는 원 작업 공간에 보존하고 보호 정답·인증정보는 제출 자료에 포함하지 않는다.

### AI 지원과 참가자 검토

Codex가 문헌 탐색, 분석·검산 코드, 실험 실행, 해석, 보고서·화면 제작을 지원했고 사용자는 목표·작업 범위·공식 안내를 제공했다. AI 검산을 참가자의 수동 검토로 기재하지 않는다. 참가자의 직접 확인과 최종 판단은 실제 수행 후 기록해야 한다. [AI 활용 기록](../../AI_USAGE.md)에 지원·실패·선택 근거, [산출물 비교 검토](BENCHMARK_REVIEW_20261025.md)에 공개 보고서의 구성 참고 범위를 기록했다. 타인의 문장·그림·분석 코드·데이터를 복사하지 않았다.

11월 6일은 사용자 제공 작업 마감 기준이며 공식 상세 날짜의 독립 확인과 구별한다. 11월 1일 공개 목록 조회는 성공했으나 상세·브라우저 연결은 실패해 마지막 성공한 10월 31일 서약·규정 확인을 유지했다. 대회 업로드·외부 발송·공개는 수행하지 않았다.
'''
    final=pages[:5]+[validation,regions,numeric]+pages[6:]
    assert len(final)==19
    manuscript='\n\n<!-- page -->\n\n'.join(s.strip() for s in final)+'\n'
    manuscript=manuscript.replace('analysis_report_v9.pdf','analysis_report_v10.pdf').replace('submission_review_v9.ipynb','submission_review_v10.ipynb')
    manuscript=manuscript.replace('10⁻¹³','10^-13').translate(str.maketrans({'–':'-','—':'-','−':'-','‑':'-'}))
    target.write_text(manuscript,'utf-8')
    print('V10 MANUSCRIPT',len(final),'pages',flush=True)


if __name__=='__main__':main()
