"""오프라인 구간 지도 75기준·실제 CSV·데스크톱과 모바일을 자료 원표와 대조한다."""
from pathlib import Path
from urllib.parse import urlparse,unquote
import sys,json
import numpy as np
import pandas as pd
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.seal_protected_weather_20261106 import W,write
W=ROOT/'outputs/private/final_jury_review_20261106';B=W/'icy_road_model';O=W/'browser_review_jury'

def main():
    O.mkdir(exist_ok=True);assert not (O/'receipt.json').exists()
    scenarios=pd.read_csv(B/'results/sections/sensitivity/scenario_summary.csv')
    membership=pd.read_csv(B/'results/sections/sensitivity/scenario_membership.csv',dtype={'seg_id':str}).set_index('seg_id')
    overlap=pd.read_csv(B/'results/inventory/overlap_sensitivity.csv',dtype={'seg_id':str})
    listed={m:sorted(set(overlap.loc[overlap.version.eq('2026-09-07')&overlap.margin_m.eq(m)&overlap.possible_overlap_km.gt(0),'seg_id'])) for m in [100,250,500]}
    errors=[];external=[];results=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        for name,width,height in [('desktop',1440,1000),('mobile',390,844)]:
            context=browser.new_context(viewport={'width':width,'height':height},accept_downloads=True)
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            def route(r):
                if r.request.url.startswith(('http://','https://')):external.append(r.request.url);r.abort()
                else:r.continue_()
            page.route('**/*',route);page.goto((B/'maps/sections.html').as_uri());page.wait_for_function('window.SECTION_READY===true')
            page.evaluate('document.fonts.ready')
            assert page.locator('#scenarioCount').get_attribute('data-count')=='3'
            assert page.locator('#view').input_value()=='review'
            counts=page.evaluate('window.REVIEW_COUNTS');assert sum(counts.values())==843 and counts['listed']==81 and counts['additional']==3
            page.locator('#segment').select_option(listed[250][0])
            stroke=page.locator('path.road[data-id="'+listed[250][0]+'"]').evaluate('(e)=>getComputedStyle(e).stroke')
            assert stroke=='rgb(41, 84, 109)',stroke
            assert page.locator('#areas tbody tr').count()==2
            assert page.locator('#matrix tbody button').count()==25
            page.locator('#matrix button[data-scenario=\"2\"]').click()
            assert page.locator('#scenarioCount').get_attribute('data-count')=='86'
            page.locator('#matrixMargin').select_option('500')
            assert page.locator('#scenarioCount').get_attribute('data-count')=='84'
            page.locator('#restore').click()
            data=page.evaluate('DATA.rows.map(r=>({id:r.id,membership:r.membership,stability:r.stability}))')
            assert len(data)==843
            for r in data:
                expected=''.join('1' if v else '0' for v in membership.loc[r['id']])
                assert r['membership']==expected
                assert abs(r['stability']-expected.count('1')/75)<1e-12
            for s in scenarios.to_dict('records'):
                actual=page.evaluate("""(s)=>{el('weatherQ').value=String(s.weather_quantile);el('curveQ').value=String(s.curve_quantile);el('margin').value=String(s.margin_m);scenario();return {count:Number(el('scenarioCount').dataset.count),ids:DATA.rows.filter(selected).map(r=>r.id).sort(),listed:DATA.rows.filter(r=>reviewKind(r)==='listed').map(r=>r.id).sort()}}""",s)
                expected=sorted(membership.index[membership[f"scenario_{int(s['scenario']):02d}"]])
                assert actual['count']==s['selected_segments'] and actual['ids']==expected,(name,s['scenario'])
                assert actual['listed']==listed[int(s['margin_m'])],(name,s['scenario'],'inventory lost')
            page.locator('#restore').click();assert page.locator('#scenarioCount').get_attribute('data-count')=='3'
            page.locator('#criteria').evaluate('(e)=>e.open=true')
            page.locator('#weatherQ').select_option('0.9');assert page.locator('#scenarioCount').get_attribute('data-count')=='0'
            page.locator('#restore').click();page.locator('#area').select_option('S01')
            page.locator('#view').select_option('shade');assert page.locator('#year').is_enabled()
            page.locator('#year').select_option('1');assert '2025/26' in page.locator('#shade').inner_text()
            page.locator('#view').select_option('stability');assert page.locator('#year').is_disabled()
            page.locator('#focus').click();box=page.locator('#map').get_attribute('viewBox');assert box.endswith('6 6')
            page.locator('#reset').click();assert page.locator('#map').get_attribute('viewBox')!=box
            chosen=page.evaluate('CHOSEN_SECTION')
            with page.expect_download() as event:page.locator('#download').click()
            download=event.value;path=O/f'selected_{name}.csv';download.save_as(path)
            f=pd.read_csv(path,dtype={'seg_id':str});assert len(f)==2 and set(f.seg_id)=={chosen}
            assert f.scenario_selection_fraction.eq(.8).all() and f.margin_m.eq(250).all()
            assert page.locator('#fieldPlanLink').get_attribute('href').endswith('#S01')
            page.locator('#fieldPlanLink').click();page.wait_for_function('window.FIELD_READY===true')
            assert page.url.endswith('#S01') and page.locator('#S01').count()==1
            page.go_back();page.wait_for_function('window.SECTION_READY===true')
            page.locator('#area').select_option('S02')
            assert page.locator('#fieldPlanLink').get_attribute('href').endswith('#S02')
            page.locator('#view').select_option('review');page.locator('#year').evaluate("(e)=>e.value='0'");page.evaluate('draw()')
            page.locator('#criteria').evaluate('(e)=>e.open=false')
            page.wait_for_function('Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0)')
            assert page.evaluate('document.documentElement.scrollWidth')<=width+1
            links=page.locator('a').evaluate_all('(a)=>a.map(x=>x.href)')
            for href in links:
                parsed=urlparse(href)
                if parsed.scheme=='file':assert Path(unquote(parsed.path).lstrip('/')).exists(),href
            page.screenshot(path=str(O/(name+'_sections_full.png')),full_page=True)
            page.locator('#map').scroll_into_view_if_needed();page.screenshot(path=str(O/(name+'_sections_map.png')))
            page.locator('#inventoryAgreement').scroll_into_view_if_needed();page.screenshot(path=str(O/(name+'_inventory_comparison.png')))
            page.evaluate('scrollTo(0,0)');page.screenshot(path=str(O/(name+'_overview.png')))
            results.append(dict(viewport=name,scenarios=75,rows=843,exact_memberships=843*75,csv_rows=2,local_links=len(links),document_width=page.evaluate('document.documentElement.scrollWidth')))
            context.close()
        browser.close()
    assert not errors and not external,(errors,external)
    write(O/'receipt.json',dict(status='passed',views=results,js_errors=errors,external_requests=external,visual_review='pending'))
    print(json.dumps(results,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
