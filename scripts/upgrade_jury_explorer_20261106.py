"""공개 목록을 유지한 채 추가 계측 후보를 보는 기본 화면과 목록 대조 설명을 만든다."""
from pathlib import Path
import subprocess,sys,shutil
ROOT=Path(__file__).resolve().parents[1];B=ROOT/'outputs/private/final_jury_review_20261106/icy_road_model'
def replace(s,a,b):
    assert s.count(a)==1,(a,s.count(a));return s.replace(a,b)
def main():
    p=B/'assets/inspection_template.txt';s=p.read_text('utf8')
    s=replace(s,'<h1>어느 구간을 먼저 확인할 것인가</h1><p>두 겨울의 기상 노출, 도로환경과 공개 취약구간 목록을 대조했습니다. 기준을 직접 바꾸며 현장 확인 범위와 그 근거를 살펴볼 수 있습니다.</p>',
        '<h1>공개 목록과 추가 확인 구간</h1><p>기존 취약구간 목록과 두 겨울의 기상·도로환경을 함께 봅니다. 선정 기준을 바꾸며 추가 계측 범위와 그 근거를 확인할 수 있습니다.</p>')
    s=replace(s,'<select id="view"><option value="selection">','<select id="view"><option value="review" selected>목록과 추가 확인 종합</option><option value="selection">')
    s=replace(s,"const labels={selection:","const labels={review:'목록과 추가 확인 종합',selection:")
    anchor="function part(){return DATA.rows.filter(r=>el('route').value==='all'||r.route===el('route').value)}"
    addition="""
function reviewKind(r){let link=relation(r);if(link==='inside_inventory_for_margin'||link==='boundary_uncertain')return 'listed';if(selected(r))return 'additional';if(link==='alignment_unavailable')return 'unknown';if(r.bridge>0||r.curve>active.curve_threshold)return 'environment';return 'other'}
const reviewColors={listed:'#29546d',additional:'#a66a2c',unknown:'#747f87',environment:'#6795a7',other:'#c7d3da'};
"""
    s=replace(s,anchor,anchor+addition)
    s=replace(s," if(mode==='selection')return", " if(mode==='review')return reviewColors[reviewKind(r)];\n if(mode==='selection')return")
    s=replace(s,"stroke:color(r)}));let hit", "stroke:color(r),style:'stroke:'+color(r)+'!important'}));let hit")
    s=replace(s,"el('scenarioCount').textContent='현재 기준 '","el('scenarioCount').textContent='추가 계측 후보 '")
    s=replace(s,"fmt(active.weather_threshold_2024,3)+'% / '+fmt(active.weather_threshold_2025,3)","fmt(active.weather_threshold_2024,1)+'% / '+fmt(active.weather_threshold_2025,1)")
    s=replace(s,"['selection','stability','inventory'].includes(mode)","['review','selection','stability','inventory'].includes(mode)")
    s=replace(s," let items=mode==='selection'?", " let items=mode==='review'?[[reviewColors.listed,'공개 목록 추정 중첩'],[reviewColors.additional,'추가 계측 후보'],[reviewColors.environment,'도로환경 조건'],[reviewColors.unknown,'이정 연결 확인'],[reviewColors.other,'그 외 분석 구간']]:mode==='selection'?")
    s=replace(s,"el('mapNote').textContent=mode==='shade'?", "let counts={listed:0,additional:0,environment:0,unknown:0,other:0};for(let r of visible)counts[reviewKind(r)]++;window.REVIEW_COUNTS=counts;\n el('mapNote').textContent=mode==='review'?'현재 노선: 목록 중첩 '+counts.listed+' · 추가 계측 '+counts.additional+' · 도로환경 '+counts.environment+' · 이정 확인 '+counts.unknown+' · 그 외 '+counts.other+'구간. 색은 위험등급이 아닙니다.':mode==='shade'?")
    s=replace(s,'<button id="download">선택 구간 근거 CSV</button>', '<a id="fieldPlanLink" class="button" href="../results/field/index.html">현장 확인 계획</a><button id="download">선택 구간 근거 CSV</button>')
    s=replace(s,"el('area').value=r.area||'';window.CHOSEN_SECTION=id;", "el('area').value=r.area||'';window.CHOSEN_SECTION=id;el('fieldPlanLink').href='../results/field/index.html'+(r.area?'#'+r.area:'');el('fieldPlanLink').textContent=r.area?r.area+' 현장 확인 계획':'두 범위의 현장 확인 계획';")
    s=replace(s,"el('criteria').open=innerWidth>720;scenario();", "el('criteria').open=false;scenario();")
    section='''<section class="analysis" id="inventoryAgreement"><h2>기상 기준과 공개 목록을 구분해서 보는 이유</h2>
<p>2026년 9월 공개 목록과 명목상 겹치는 분석구간은 64개입니다. 이 중 기상 상위 25%에 든 곳은 첫 겨울 30개, 둘째 겨울 0개였고 두 겨울을 모두 충족한 곳도 0개였습니다. 위치 여유를 ±250m로 넓히면 목록과 중첩 가능한 구간은 81개입니다.</p>
<div class="analysis-grid"><img src="../report/figures/inventory_agreement.png" alt="공개 목록과 명목상 겹치는 64구간 중 첫 겨울·둘째 겨울·두 겨울 모두 기상 기준을 충족한 개수. 상위 25% 기준은 각각 30개·0개·0개."><div><h3>기존 목록을 기상 모형으로 해제하지 않습니다</h3><p>두 겨울의 기상 상위 조건은 새로운 관측 위치를 탐색하는 조건입니다. 기존 취약구간 목록 전체를 재현하는 기준은 아닙니다. 종합 지도는 목록의 추정 중첩을 표시한 상태에서 추가 계측 후보를 함께 보여줍니다.</p><p>목록 미포함 구간을 실제 비결빙 정답으로 사용하지 않았습니다. 현재 이정은 암거 기준점의 보간값이며, 중첩 여부는 측량으로 확정한 위치가 아닙니다.</p><p class="caption">그래프는 전체 843구간을 대상으로 한 고정 비교이며 위 노선 필터와 별도입니다. <a href="../results/inventory/agreement/threshold_comparison.csv" download>전체 문턱 비교 CSV</a> · <a href="../results/inventory/agreement/mapped_inventory_records.csv" download>목록별 연결 원표</a></p></div></div></section>
'''
    s=replace(s,'<section class="analysis"><h2>기준값에 따라 달라지는 확인 범위</h2>',section+'<section class="analysis"><h2>기준값에 따라 달라지는 확인 범위</h2>')
    p.write_text(s,'utf8')
    build()
def build():
    target=B/'local_review/jury_sections.html'
    subprocess.run([sys.executable,'-X','utf8',str(B/'code/build_section_explorer.py'),'--output',str(target)],check=True)
    shutil.copyfile(target,B/'maps/sections.html')
    subprocess.run([sys.executable,'-X','utf8',str(B/'code/build_section_explorer.py'),'--output',str(B/'local_review/rebuilt_final_sections.html')],check=True)
    assert (B/'maps/sections.html').read_bytes()==(B/'local_review/rebuilt_final_sections.html').read_bytes()
    print('목록 중첩·추가 계측을 함께 보는 화면과 직접 계측 계획 이동을 연결했습니다.',flush=True)
if __name__=='__main__':main()
