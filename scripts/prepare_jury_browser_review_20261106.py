"""종합 지도·목록 중첩 유지·새 이동 경로를 기존 75기준 검사에 추가한다."""
from pathlib import Path
import subprocess,sys,shutil
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/private/final_jury_review_20261106';B=W/'icy_road_model'
def change(s,old,new):assert s.count(old)==1,(old,s.count(old));return s.replace(old,new)
def main():
    p=B/'assets/inspection_template.txt';s=p.read_text('utf8')
    old='<img src="../report/figures/inventory_agreement.png" alt="공개 목록과 명목상 겹치는 64구간 중 첫 겨울·둘째 겨울·두 겨울 모두 기상 기준을 충족한 개수. 상위 25% 기준은 각각 30개·0개·0개.">'
    s=change(s,old,'<a href="../report/figures/inventory_agreement.png" target="_blank" rel="noopener">'+old+'</a>')
    p.write_text(s,'utf8')
    target=B/'local_review/sections_review_ready.html'
    subprocess.run([sys.executable,'-X','utf8',str(B/'code/build_section_explorer.py'),'--output',str(target)],check=True)
    shutil.copyfile(target,B/'maps/sections.html')
    source=(ROOT/'scripts/check_evening_experience_20261106.py').read_text('utf8')
    source=source.replace("W=ROOT/'outputs/private/evening_refinement_20261106'","W=ROOT/'outputs/private/final_jury_review_20261106'")
    source=source.replace("O=W/'browser_review_final'","O=W/'browser_review_jury'")
    source=source.replace("if width<720:page.locator('#criteria summary').click()","page.locator('#criteria').evaluate('(e)=>e.open=true')")
    needle="errors=[];external=[];results=[]"
    source=change(source,needle,"""overlap=pd.read_csv(B/'results/inventory/overlap_sensitivity.csv',dtype={'seg_id':str})
    listed={m:sorted(set(overlap.loc[overlap.version.eq('2026-09-07')&overlap.margin_m.eq(m)&overlap.possible_overlap_km.gt(0),'seg_id'])) for m in [100,250,500]}
    errors=[];external=[];results=[]""")
    needle="assert page.locator('#scenarioCount').get_attribute('data-count')=='3'"
    at=source.index(needle)
    source=source[:at]+source[at:].replace(needle,needle+"""
            assert page.locator('#view').input_value()=='review'
            counts=page.evaluate('window.REVIEW_COUNTS');assert sum(counts.values())==843 and counts['listed']==81 and counts['additional']==3
            page.locator('#segment').select_option(listed[250][0])
            stroke=page.locator('path.road[data-id="'+listed[250][0]+'"]').evaluate('(e)=>getComputedStyle(e).stroke')
            assert stroke=='rgb(41, 84, 109)',stroke""",1)
    needle="ids:DATA.rows.filter(selected).map(r=>r.id).sort()}}"
    source=change(source,needle,"ids:DATA.rows.filter(selected).map(r=>r.id).sort(),listed:DATA.rows.filter(r=>reviewKind(r)==='listed').map(r=>r.id).sort()}}")
    needle="assert actual['count']==s['selected_segments'] and actual['ids']==expected,(name,s['scenario'])"
    source=change(source,needle,needle+"\n                assert actual['listed']==listed[int(s['margin_m'])],(name,s['scenario'],'inventory lost')")
    needle="page.locator('#view').select_option('selection');page.locator('#year').evaluate"
    source=change(source,needle,"""assert page.locator('#fieldPlanLink').get_attribute('href').endswith('#S01')
            page.locator('#fieldPlanLink').click();page.wait_for_function('window.FIELD_READY===true')
            assert page.url.endswith('#S01') and page.locator('#S01').count()==1
            page.go_back();page.wait_for_function('window.SECTION_READY===true')
            page.locator('#area').select_option('S02')
            assert page.locator('#fieldPlanLink').get_attribute('href').endswith('#S02')
            page.locator('#view').select_option('review');page.locator('#year').evaluate""")
    needle="page.locator('#map').scroll_into_view_if_needed();page.screenshot(path=str(O/(name+'_sections_map.png')))"
    source=change(source,needle,needle+"\n            page.locator('#inventoryAgreement').scroll_into_view_if_needed();page.screenshot(path=str(O/(name+'_inventory_comparison.png')))\n            page.evaluate('scrollTo(0,0)');page.screenshot(path=str(O/(name+'_overview.png')))")
    target=ROOT/'scripts/check_jury_experience_20261106.py';assert not target.exists();target.write_text(source,'utf8')
    print('75개 기준에서도 공개 목록 표시가 유지되는지와 계측 계획 이동을 확인합니다.',flush=True)
if __name__=='__main__':main()
