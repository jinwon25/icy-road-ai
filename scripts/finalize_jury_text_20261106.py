"""최종 결과 중심의 문구와 규정 안내를 맞추고 문서자료를 동기화한다."""
from pathlib import Path
import json,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/private/final_jury_review_20261106';B=W/'icy_road_model';D=W/'icy_road_documents'
def main():
    for rel in ['assets/field_plan_template.html','results/field/index.html']:
        p=B/rel;s=p.read_text('utf8')
        assert s.count('두 범위에서 무엇을 확인할 것인가')==1
        s=s.replace('두 범위에서 무엇을 확인할 것인가','서해안 두 범위의 현장 확인 계획')
        s=s.replace('../../index.html#benchmarks','../../index.html#temperature')
        p.write_text(s,'utf8')
    target=B/'local_review/field_jury_text'
    subprocess.run([sys.executable,'-X','utf8',str(B/'code/build_field_plan.py'),'--output',str(target)],check=True)
    for p in target.iterdir():
        if p.name!='measurement_plan.gpkg':shutil.copyfile(p,B/'results/field'/p.name)
    # 실제 중점은 그대로이며 GPKG의 저장 시각 차이로 원 공간 파일을 바꾸지 않는다.
    shutil.copyfile(B/'report/analysis_report.pdf',D/'report/analysis_report.pdf')
    for p in (B/'report/figures').glob('*.png'):shutil.copyfile(p,D/'figures'/p.name)
    for name,new in [('threshold_comparison.csv','inventory_threshold_comparison.csv'),('mapped_inventory_records.csv','inventory_record_agreement.csv')]:
        shutil.copyfile(B/'results/inventory/agreement'/name,D/'data'/new)
    p=B/'README.md';s=p.read_text('utf8')
    s=s.replace('| 지형·일사 맥락 |','| 공개 목록 대조 | 명목 중첩 64구간, ±250m 중첩 가능 81구간 | 추정 이정의 대조. 기존 지정을 해제하는 기준으로 사용하지 않음 |\n| 지형·일사 맥락 |')
    s=s.replace('## 결과의 근거','''## 공개 목록과 기상 기준

[종합 지도](maps/sections.html)는 공개 목록의 추정 중첩과 추가 계측 후보를 함께 표시한다. 기상 상위 25%를 두 겨울 모두 요구하면, 목록과 명목상 겹치는 64개 분석구간 중 남는 곳은 0개였다. 이 기상 조건은 기존 취약구간 목록을 재현하지 못했으며, 기존 지정의 해제나 관리 축소에 사용하지 않는다. [문턱별 전체 대조](results/inventory/agreement/threshold_comparison.csv)와 [목록별 연결](results/inventory/agreement/mapped_inventory_records.csv)을 제공한다.

## 결과의 근거''')
    s=s.replace('이력 모형에는 출력일 전 24시간의 문맥을 함께 입력한다.','출력 시각 이전의 기상을 함께 입력하면 이력 결측을 줄일 수 있다. 기간 초입의 이력 부족은 weather_history_status에 표시한다.')
    s=s.replace('이 단계만 추가 지리 라이브러리가 필요하다.','지형 계산과 계측 계획 재생성에는 아래 지리 라이브러리를 추가로 설치한다.')
    p.write_text(s,'utf8')
    p=B/'AI_USAGE.md';s=p.read_text('utf8')
    s+='''
## 전체 기간 재현과 목록 대조

ASOS 좌표의 태양위치를 포함한 정답 없는 전체 검증 기상 입력을 제공한다. 제출 CLI의 온도·결빙 예측 103,680행은 기존 제출값과 정확히 일치했다. 분석 Notebook의 12개 코드 셀도 실제 Jupyter 커널에서 실행했다. 현재 Windows 환경에서 전체 추론은 파일 읽기·이력 계산·출력 저장을 포함해 약 27초였으며, 다른 장비의 처리시간으로 일반화하지 않았다.

공개 목록과 명목상 겹치는 64개 분석구간 중 두 겨울 모두 기상 상위 25% 조건을 충족한 곳은 0개였다. 이 불일치를 숨기거나 목록에 맞춰 문턱을 다시 고르지 않았다. 지도는 공개 목록 대조를 유지한 채 추가 계측 후보를 함께 표시한다. 목록 미포함 구간을 비결빙 음성 정답으로 사용하지 않았다.

목적·지표·자료의 정의를 맞추는 표현은 [Aurora의 도로기상 지수 프레임워크](https://www.intrans.iastate.edu/wp-content/uploads/2026/03/standardized_framework_road_condition_indices_w_cvr.pdf), 문턱 선택과 평가 역할의 구분은 [scikit-learn 공식 문서](https://scikit-learn.org/stable/modules/classification_threshold.html)를 참고했다. 이 자료의 외국 사례 성적을 우리 모형의 비교 점수나 수상 가능성 근거로 사용하지 않았다.
'''
    p.write_text(s,'utf8')
    (D/'AI_USAGE.md').write_text(s.replace('results/evaluation/fixed_temperature_rule_review/comparison.csv','data/fixed_temperature_rule_comparison.csv'),'utf8')
    p=D/'README.md';s=p.read_text('utf8').replace('13쪽','14쪽')
    s+='''
공개 목록과 기상 기준의 대조는 보고서에 별도 장으로 제시했다. 명목상 목록 중첩 64구간 중 두 겨울 모두 기상 상위 25%를 충족한 곳은 0개였다. [모든 기상 문턱의 비교](data/inventory_threshold_comparison.csv)와 [목록별 연결 원표](data/inventory_record_agreement.csv)를 제공하며, 목록을 비결빙 정답처럼 사용하거나 기존 지정을 해제하지 않는다.
'''
    p.write_text(s,'utf8')
    # 설치가 끝난 뒤 교체할 저장소의 현재 안내. 과거 원문은 작업 폴더에 보존했다.
    current=W/'current_project_documents';current.mkdir()
    requirements='''# 대회 요구와 제출 자료

로드투인사이트는 전북 고속도로 결빙 과제의 문제해결 부문에 참가한다. 결과물 마감은 **2026년 11월 6일 23:59 KST**다. 문서자료와 모델자료는 각각 한 개 폴더를 담은 ZIP으로 제출한다.

공통 심사는 창의성 20점·우수성 50점·효과성 30점이다. 과제의 회귀·분류·공간 결과에 임의의 세부 배점을 붙이지 않는다. [공식 소개](https://aida.kisti.re.kr/competition/main/overview.do)와 [공식 규정·Q&A의 상세 적용](OFFICIAL_RULES_AND_RUBRIC_20261106.md)을 함께 확인한다.

| 요구 | 현재 적용 |
| --- | --- |
| 보호 지점 | 부곡교 12410·삼봉 33411·해전 23402를 학습에서 제외 |
| 기간 | 2024/25·2025/26의 11월-2월, 정확한 10분 KST 시각 |
| 회귀 | 노면온도 BIAS·MAE·RMSE, 공통 관측쌍의 비교 기준 포함 |
| 분류 | Ice만 양성. 날짜별 지표, 지점별 기간 평균, 유효 지점 평균 순서. 무결빙 지점·산정불가 지표는 공식 답변대로 처리 |
| 필수 대조표 | 고속도로·지점·10분 시각·관측 상태·결빙 예측·관측 온도·추정 온도 포함 |
| 입력 제한 | 다른 학습 지점의 같은 시각 노면상태를 사용하지 않음. 외부 AI 예측 API에 의존하지 않음 |
| 공간 결과 | 500m 843구간, 기상·도로환경 기준과 근거, CSV·Shapefile·GeoPackage·JPG·오프라인 지도 |
| 기준 해석 | 자체 기준의 근거와 민감도 제시. 두 겨울을 10년 기후값으로 가장하지 않음. 정규화 DEM을 미터로 해석하지 않음 |
| 실행 재현 | 코드·고정 환경·모형·학습 및 검증 입력·Notebook·실행 매뉴얼·데모 포함 |
| 자료·AI 사용 | 출처와 이용조건, AI 지원 범위와 주요 대안·최종 선택을 기록. 제공 데이터의 승인 없는 외부 공개 금지 |

[현재 제출 자료](../../outputs/private/competition_submission/README.md) · [모델 실행 안내](../../outputs/private/competition_submission/icy_road_model/README.md) · [결과 읽는 순서](../START_HERE.md)

전체 과제 답변과 공통 답변의 마지막 본문 확인은 오늘 15:35 KST다. 이후 최신 공지·공통 Q&A 목록과 소개는 다시 확인했으나 상세 본문의 재접속은 제한됐다. 파일 제작·검증과 실제 사이트 접수 완료는 구분하며, 업로드 완료와 제출 이력은 제출 화면에서 확인해야 한다.
'''
    (current/'COMPETITION_REQUIREMENTS.md').write_text(requirements,'utf8')
    status='''# 분석 결과와 실행

참가팀: **로드투인사이트**

[분석 보고서](../outputs/private/competition_submission/icy_road_model/report/analysis_report.pdf) · [기상 지도](../outputs/private/competition_submission/icy_road_model/index.html) · [구간 검토](../outputs/private/competition_submission/icy_road_model/maps/sections.html) · [현장 확인 계획](../outputs/private/competition_submission/icy_road_model/results/field/index.html) · [실행 영상](../outputs/private/competition_submission/icy_road_model/demo/index.html)

학습 제외 3지점의 노면온도 MAE 평균은 0.978°C이며, 같은 관측쌍에서 기본 12특성 회귀보다 MAE가 14.6% 낮았다. 결빙의 날짜별 평균 Precision 0.0195·F1 0.0326은 낮은 수준이며 자동 경보 성능에는 한계가 남는다.

추가 계측 기준에 남은 대상은 3구간·2개 범위다. 공개 목록의 명목 중첩 64구간과 ±250m 위치 여유를 포함한 81구간을 함께 대조하며 기존 지정을 모형으로 해제하지 않는다. 현장 기록은 미측정 상태이고 실제 계측·사고 감소 효과를 검증한 것은 아니다.

모형·학습 자료·필수 예측은 보존했다. 전체 검증 기상 입력으로 제출 CLI의 103,680행을 재현했고, 분석 Notebook 12개 셀을 실제 실행했다. [실행 안내](../outputs/private/competition_submission/icy_road_model/README.md)와 [제출 파일](../outputs/private/competition_submission/README.md)을 따른다.
'''
    (current/'STATUS.md').write_text(status,'utf8')
    print('최종 문구·14쪽 문서자료·현재 규정 안내를 동기화했습니다.',flush=True)
if __name__=='__main__':main()
