"""현재 분석에 공개 목록 대조의 결과와 해석을 포함하는 보고서 생성 코드를 준비한다."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/private/final_jury_review_20261106';B=W/'icy_road_model'
def main():
    text=(ROOT/'scripts/build_information_report_20261106.py').read_text('utf8')
    text=text.replace("P/'judging_upgrade_20261106","P/'final_jury_review_20261106")
    text=text.replace("assert len(doc)==13", "assert len(doc)==14")
    text=text.replace('기준 조합의 계측 검토 대상<br/>선정 기준 민감도 함께 제공','선정 기준에 남은 추가 계측 후보<br/>기존 목록과의 관계도 함께 제공')
    anchor=" page('추가 계측·시설 확인 범위')"
    page=""" page('공개 목록과 기상 기준의 관계')
 p('2026년 9월 7일 공개 목록의 8개 항목이 전북 분석 중심선의 64개 500m 구간과 명목상 겹쳤다. 이정은 공식 암거 기준점 사이를 보간한 값이며, 실제 시설 범위를 측량해 확정한 결과는 아니다.')
 picture('inventory_agreement',245,'공개 목록과 명목상 겹치는 64구간 중 겨울별 기상 문턱을 충족한 개수와 위치. 음영은 현재 선정 기준인 상위 25%다. 목록 미포함 구간을 비결빙 정답으로 사용하지 않았다.')
 table([['대조 범위','구간 수','해석'],['명목상 목록 중첩','64','공개 목록 8개 항목과 추정 이정이 겹침'],['±250m 안에서 중첩 가능','81','목록 경계의 위치 민감도를 포함'],['기상 상위 25%를 두 겨울 모두 충족','0 / 64','목록 제외 조건을 적용하기 전의 비교']],[159,75,273])
 p('기상 상위 25% 조건을 충족한 목록 대조 구간은 첫 겨울 30개, 둘째 겨울 0개였다. 이 두 겨울의 기상 조건으로 기존 취약구간 목록을 재현하지 못했다. 문턱을 바꾼 전체 비교를 함께 제공하고, 이 결과에 맞춰 선정 문턱을 다시 고르지 않았다.')
 p('종합 지도에는 공개 목록의 추정 중첩을 표시한 상태에서 추가 계측 후보와 도로환경 조건을 함께 보여 준다. 기존 취약구간의 관리를 이 기상 기준으로 축소하지 않는다. 관측 상태와 관리용 지수의 목적을 명시하는 최근 도로기상 프레임워크[12]도 참고했다.')
 p('이정 연결이 없는 22구간은 목록 밖으로 확정하지 않았다. 목록의 기준일은 두 겨울 뒤이므로 이 비교는 실제 Ice의 독립 검증이나 기존 지정의 정확도 평가가 아니다.',small)

"""
    assert text.count(anchor)==1;text=text.replace(anchor,page+anchor)
    anchor=" ('[11] 기상청 API허브. 추가 도로기상 관측·지점 정보의 원천.','https://apihub.kma.go.kr/apiInfo.do')]"
    replacement=""" ('[11] 기상청 API허브. 추가 도로기상 관측·지점 정보의 원천.','https://apihub.kma.go.kr/apiInfo.do'),
 ('[12] Nlenanya et al. Standardized Framework for Winter Weather Road Condition Indices. Aurora (2026).','https://www.intrans.iastate.edu/wp-content/uploads/2026/03/standardized_framework_road_condition_indices_w_cvr.pdf')]"""
    assert text.count(anchor)==1;text=text.replace(anchor,replacement)
    target=ROOT/'scripts/build_jury_report_20261106.py';assert not target.exists();target.write_text(text,'utf8')
    report=B/'report/analysis_report.pdf';backup=W/'baseline_analysis_report.pdf'
    assert report.resolve().is_relative_to(W.resolve()) and backup.resolve().is_relative_to(W.resolve()) and not backup.exists()
    report.rename(backup)
if __name__=='__main__':main()
