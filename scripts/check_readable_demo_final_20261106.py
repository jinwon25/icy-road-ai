"""분석 탭·원표 대조·단어 줄바꿈·영상 동작을 다양한 화면에서 확인한다."""
from pathlib import Path
import sys,json,re
import numpy as np,pandas as pd
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
W=ROOT/'outputs/private/late_research_design_20261106';B=W/'icy_road_model'
def main():
    out=W/'reader_unbroken_review';out.mkdir();checks=[];errors=[];external=[]
    raw=pd.read_csv(B/'results/evaluation/temperature_benchmarks/metrics.csv',float_precision='round_trip')
    methods=['asos_air_reference','aws_air_reference','asos_ground_reference','weather12_regression','estimated']
    with sync_playwright() as w:
        browser=w.chromium.launch(headless=True)
        for name,width,height in [('wide',1920,1080),('desktop',1440,1000),('laptop',1280,900),('tablet',768,1024),('mobile',390,844),('narrow',320,800)]:
            page=browser.new_page(viewport={'width':width,'height':height},reduced_motion='reduce');page.on('pageerror',lambda e:errors.append(str(e)))
            def route(r):
                if r.request.url.startswith(('http://','https://')):external.append(r.request.url);r.abort()
                else:r.continue_()
            page.route('**/*',route);page.goto((B/'demo/index.html').as_uri());page.wait_for_load_state('networkidle');page.wait_for_function('window.READER_READY===true');page.evaluate('document.fonts.ready')
            assert page.evaluate('document.documentElement.scrollWidth')<=width+1
            page.screenshot(path=str(out/(name+'_initial.png')))
            assert page.locator('#videoCover').is_visible() and page.locator('video').get_attribute('src') is None
            for scope in ['all_temperature','near_freezing_observed_pm2c']:
                page.locator('#comparisonScope').select_option(scope)
                actual=[float(v) for v in page.locator('.plot-row strong').all_text_contents()]
                q=raw.loc[raw.temperature_scope.eq(scope)&raw.period.eq('all')&raw.station.eq('station_macro')].set_index('method')
                np.testing.assert_allclose(actual,[float(f'{q.loc[m,"mae"]:.3f}') for m in methods],rtol=0,atol=0)
            page.locator('#tab-temperature').focus();page.keyboard.press('ArrowRight');assert page.locator('#tab-icing').get_attribute('aria-selected')=='true'
            assert page.url.endswith('#icing-results') and page.locator('#icing-results').is_visible()
            page.locator('#icing-results').scroll_into_view_if_needed();page.screenshot(path=str(out/(name+'_icing.png')))
            page.keyboard.press('End');assert page.locator('#tab-sections').get_attribute('aria-selected')=='true'
            page.locator('#section-results').scroll_into_view_if_needed();page.wait_for_function('document.querySelector("#section-results img").complete');page.screenshot(path=str(out/(name+'_sections.png')))
            page.locator('#tab-temperature').click();page.locator('#analysisResults').scroll_into_view_if_needed();page.screenshot(path=str(out/(name+'_temperature.png')))
            # Keep Korean words together, including the user's reported "현/장" break.
            breaks=page.evaluate('''()=>{let bad=[];for(const e of document.querySelectorAll('p,h1,h2,h3,button,figcaption')){if(!e.getClientRects().length)continue;for(const n of e.childNodes){if(n.nodeType!==Node.TEXT_NODE)continue;for(const m of n.textContent.matchAll(/[가-힣]{2,}/g)){let r=document.createRange();r.setStart(n,m.index);r.setEnd(n,m.index+m[0].length);if(r.getClientRects().length>1)bad.push(m[0])}}}return bad}''')
            assert not breaks,(name,breaks)
            assert page.evaluate('document.documentElement.scrollWidth')<=width+1
            if name in ['desktop','mobile']:
                page.locator('[data-second="86"]').click();page.wait_for_function('document.querySelector("video").currentTime>=86&&!document.querySelector("video").paused',timeout=30000);page.locator('video').evaluate('v=>v.pause()')
            checks.append(dict(viewport=name,width=width,no_overflow=True,comparison_scopes=2,plot_values_match_csv=True,keyboard_tabs=True,korean_words_not_split=True,poster_visible_before_play=True))
            page.close()
        browser.close()
    assert not errors and not external,(errors,external)
    record=dict(status='passed',views=checks,js_errors=errors,external_requests=external,visual_review='pending',source_sha256=sha(B/'demo/index.html'))
    (out/'receipt.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n','utf8')
    print('PASS six widths, two comparison scopes, native keyboard tabs and Korean word wrapping',flush=True)
if __name__=='__main__':main()
