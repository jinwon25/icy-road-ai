"""최종 보고서에 실제 입력 중복 제거와 현재 선정 결과만 반영한다."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/private/judging_upgrade_20261106';B=W/'icy_road_model';O=W/'information_group_correction'
s=(ROOT/'scripts/build_judging_report_20261106.py').read_text('utf8')
def change(old,new):
    global s
    assert s.count(old)==1,(old[:90],s.count(old));s=s.replace(old,new)
change("Paragraph('22구간',stat)","Paragraph('3구간',stat)")
change("기준 조합 22구간과 75개 기준의 민감도를 제공한다.","기준 조합 3구간과 75개 기준의 민감도를 제공한다.")
marker=" page('학습에서 제외한 지점의 노면온도')"
addition=""" p('구간 노출의 분위수에는 실제 결빙 조건 입력 14열의 전체 시계열이 같은 조합을 한 번씩 집계했다. 후보 관측소 조합은 겨울별 68개지만 고유 입력은 각각 22개·24개다. 136개 조합의 2,350,080행을 대조했고 같은 배열인 90개 중복을 확인했다. 이 개수는 독립 관측 표본 수를 뜻하지 않는다.',small)
"""
change(marker,addition+"\n"+marker)
change("고유 기상 그룹 기준 75백분위","실제 14입력 시계열의 중복을 제외한 75백분위")
change("선정 결과는 서해안·호남의 22구간, 방향별 11개 연속 범위다. 길이는 양방향 합계 11.0km이며, 이 구간들이 공유하는 기상 입력은 겨울별 5개 조합이다. 선정 개수를 독립적인 위험 발견 건수로 해석하지 않는다.",
       "선정 결과는 서해안의 3구간·2개 연속 범위이며, 같은 진행 방향에서 총 1.5km다. 세 구간은 겨울마다 같은 하나의 결빙 조건 입력 시계열을 공유한다. 모두 교량 코드가 아닌 선형 변화 기준으로 선정됐다. 서로 독립적인 위험 발견 세 건으로 해석하지 않는다.")
old=""" table([['예시','방향과 추정 이정','조건 비율<br/>2024/25 → 2025/26'],['F06 서해안','서천·군산 → 고창·영광<br/>79.8-80.8km','13.0% → 6.8%'],['F08 호남','논산JC → 호남터널남측<br/>120.6-123.6km','12.0% → 4.8%']],[95,265,147])"""
new=""" table([['검토 범위','방향과 추정 이정','조건 비율<br/>2024/25 → 2025/26'],['S01 서해안','서천·군산 → 고창·영광<br/>79.81-80.84km / 2구간','13.0% → 6.8%'],['S02 서해안','서천·군산 → 고창·영광<br/>84.28-84.81km / 1구간','13.0% → 6.8%']],[95,265,147])"""
change(old,new)
change("전체 11개 범위와 구간 키는 CSV·GIS에 제공한다.","두 범위와 구간 키는 CSV·GIS에 제공한다.")
change("갈색 테두리가 기준 조합 22구간이다.","갈색 테두리가 기준 조합 3구간이다.")
change("기준 조합에서는 843개 중 기상 조건을 두 겨울 모두 충족한 곳이 95개, 교량·선형 조건까지 충족한 곳이 27개, 공개 목록 밖 조건까지 충족한 곳이 22개였다. 가용성 문턱을 90~99%로 바꿔도 기준 조합의 22개는 같았다.",
       "기준 조합에서는 843개 중 기상 조건을 두 겨울 모두 충족한 곳이 60개, 교량·선형 조건까지 충족한 곳이 3개였다. 이 세 구간은 공개 목록의 경계 여유를 ±100~500m로, 가용성 문턱을 90~99%로 바꿔도 유지됐다.")
change("F06의 두 구간은 60개 조합(80%)에서 유지돼 현장 확인의 우선 근거로 삼을 수 있다.",
       "S01의 두 구간은 60개 조합(80%), S02의 한 구간은 48개 조합(64%)에서 유지됐다.")
needle=" page('지형에서 확인할 낮의 일사 환경')"
add=""" h('문턱을 산정하는 정보 단위')
 table([['겨울','관측소 후보 조합','서로 다른 실제 14입력 시계열'],['2024/25',68,22],['2025/26',68,24]],[107,170,230])
 p('관측소 후보의 예비 순서가 달라도 실제로 입력된 값은 같을 수 있다. 모든 10분 시각과 14열 배열이 같은지 대조해 중복을 합쳤다. 조건 비율의 원래 분자·분모와 고정 예측은 유지하고, 문턱의 집계 단위를 실제 정보에 맞췄다. 재현용 원 입력과 식별자 대조표를 함께 제공한다.',small)
"""
change(needle,add+"\n"+needle)
change("F06·F08의 대표 중점","S01·S02의 대표 중점")
old=" p('F06의 대표 중점에서는 태양 고도가 양수인 시점의 15.2%가 근사 지평선 아래에 있었다. F08 대표 중점은 4.6%였다. 탐색을 1km로 줄이면 각각 15.2%·1.8%가 되어 먼 지형의 반영 범위에 따라 결과가 달라졌다. 각 범위에서 추정 이정이 가장 앞선 중점을 예시로 사용했으며, 전체 구간의 결과와 1km 비교를 CSV로 제공한다.')"
new=""" examples=pd.read_csv(F/'terrain_examples.csv').set_index('area')
 a=examples.loc['S01'];b=examples.loc['S02']
 p(f'S01 대표 중점의 지형 차폐 가능 낮 비율은 {100*a.shade_fraction_2024:.1f}%, S02는 {100*b.shade_fraction_2024:.1f}%였다. 탐색을 1km로 줄이면 각각 {100*a.shade_fraction_1km_2024:.1f}%·{100*b.shade_fraction_1km_2024:.1f}%다. 같은 결빙 조건 입력을 공유해도 주변 지형 맥락은 다르다. 각 범위에서 추정 이정이 가장 앞선 중점을 예시로 사용했으며 전체 843개 중점의 원표를 제공한다.')"""
change(old,new)
change("기준 조합 22구간의 선택 유지율은 36~80%였고","기준 조합 3구간의 선택 유지율은 64~80%였고")
change("B/'technical/judging_evidence.json'","B/'technical/weather_information_group_audit.json'")
change("B/'results/sections/terrain/segment_solar_context.csv']","B/'results/sections/terrain/segment_solar_context.csv',B/'data/weather_information_groups.csv']")
p=ROOT/'scripts/build_information_report_20261106.py';assert not p.exists();p.write_text(s,'utf8')
for original,saved in [(B/'report/analysis_report.pdf',O/'analysis_report_before_information_fix.pdf'),(W/'report_build.json',O/'report_build_before_information_fix.json'),(W/'new_figures.json',O/'new_figures_before_information_fix.json')]:
    assert original.resolve().is_relative_to(W.resolve()) and saved.resolve().is_relative_to(W.resolve()) and not saved.exists()
    original.replace(saved)
print('현재 정보 단위·3구간·2개 범위로 보고서 조판 준비 완료')
