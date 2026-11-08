"""새 열람 순서·영상 장면·키보드·지역 화면의 실제 동작을 확인한다."""
from pathlib import Path
from urllib.parse import urlparse,unquote
import json,sys,re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import cv2
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
W=ROOT/'outputs/private/late_research_design_20261106';B=W/'icy_road_model'

def main():
    out=W/'frontend_review_final';out.mkdir();checks=[];errors=[];external=[];dynamic_ids={}
    with sync_playwright() as w:
        browser=w.chromium.launch(headless=True)
        for name,width,height in [('desktop',1440,1000),('tablet',768,1024),('mobile',390,844)]:
            ctx=browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce');page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            def route(r):
                if r.request.url.startswith(('http://','https://')):external.append(r.request.url);r.abort()
                else:r.continue_()
            page.route('**/*',route)
            for rel,ready in [('start.html','window.START_READY===true'),('demo/index.html','window.DEMO_READY===true'),('demo/inference.html','document.readyState==="complete"'),('maps/sections.html','window.SECTION_READY===true'),('results/field/index.html','window.FIELD_READY===true')]:
                page.goto((B/rel).as_uri());page.wait_for_function(ready,timeout=60000);page.evaluate('document.fonts.ready')
                assert page.evaluate('document.documentElement.scrollWidth')<=width+1,(name,rel)
                for href in page.locator('a').evaluate_all('(a)=>a.map(e=>e.href)'):
                    p=urlparse(href)
                    if p.scheme!='file':continue
                    local=Path(unquote(p.path).lstrip('/'));assert local.is_file(),href
                    if p.fragment and local.suffix=='.html':
                        soup=BeautifulSoup(local.read_text('utf8'),'html.parser')
                        if not soup.find(id=p.fragment):
                            if str(local) not in dynamic_ids:
                                probe=ctx.new_page();probe.goto(local.as_uri());probe.wait_for_function('window.FIELD_READY===true',timeout=30000)
                                dynamic_ids[str(local)]=set(probe.locator('[id]').evaluate_all('(es)=>es.map(e=>e.id)'));probe.close()
                            assert p.fragment in dynamic_ids[str(local)],href
                page.screenshot(path=str(out/(name+'_'+rel.replace('/','_')+'.png')),full_page=rel in ['start.html','demo/index.html','demo/inference.html'])
                if rel=='start.html':
                    assert page.locator('.route-line').count()==3
                    for button in page.locator('.route-key button').all():
                        button.focus();page.keyboard.press('Enter');assert button.get_attribute('aria-pressed')=='true'
                        key=button.get_attribute('data-route')
                        assert page.locator('.route-line').evaluate_all('(p,key)=>p.every(e=>Number(getComputedStyle(e).opacity)===(e.dataset.route===key?1:.12))',key)
                        page.keyboard.press('Enter');assert button.get_attribute('aria-pressed')=='false'
                    assert '정밀도 1.95%' in page.locator('.findings').inner_text()
                    checks.append(dict(viewport=name,page=rel,route_toggle_keyboard=True,geographic_paths=3,explicit_icing_limitation=True))
                elif rel=='demo/index.html':
                    assert page.locator('video').get_attribute('poster')=='poster.png'
                    page.wait_for_function('document.querySelector("video").readyState>=2')
                    duration=page.locator('video').evaluate('v=>v.duration');assert 92<duration<93
                    for button in page.locator('[data-second]').all():
                        second=float(button.get_attribute('data-second'));button.focus();page.keyboard.press('Enter')
                        page.wait_for_function('document.querySelector("video").currentTime>=Number(document.activeElement.dataset.second) && document.querySelector("video").currentTime<Number(document.activeElement.dataset.second)+1.5')
                        page.locator('video').evaluate('v=>v.pause()')
                        assert button.get_attribute('aria-current')=='true'
                    page.locator('summary').click();assert page.locator('details').evaluate('e=>e.open')
                    checks.append(dict(viewport=name,page=rel,poster_exists=True,video_duration=duration,keyboard_seek_buttons=8,transcript_opens=True))
                elif rel=='demo/inference.html':
                    if width<720:
                        for table in page.locator('.table-scroll').all():
                            table.focus();before=table.evaluate('e=>e.scrollLeft');page.keyboard.press('ArrowRight');page.wait_for_timeout(250);assert table.evaluate('e=>e.scrollLeft')>before
                    checks.append(dict(viewport=name,page=rel,tables_keyboard_scroll=True))
                else:checks.append(dict(viewport=name,page=rel,local_links=True,no_overflow=True))
            ctx.close()
        browser.close()
    assert not errors and not external,(errors,external)
    cap=cv2.VideoCapture(str(B/'demo/model_demo.webm'));assert cap.isOpened()
    for sec in [9,21,27,40,47,65,83]:
        cap.set(cv2.CAP_PROP_POS_MSEC,sec*1000);ok,im=cap.read();assert ok;ok,buffer=cv2.imencode('.png',im);assert ok;(out/f'chapter_{sec:02d}.png').write_bytes(buffer.tobytes())
    cap.release()
    receipt=dict(status='passed',views=checks,js_errors=errors,external_requests=external,visual_review='pending',
        source_files={n:sha(B/n) for n in ['start.html','demo/index.html','demo/inference.html','demo/poster.png','demo/model_demo.webm','index.html','maps/sections.html','results/field/index.html']})
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf8')
    print('PASS',len(checks),'views; keyboard route selection, eight video seeks, offline links and scrollable tables',flush=True)
if __name__=='__main__':main()
