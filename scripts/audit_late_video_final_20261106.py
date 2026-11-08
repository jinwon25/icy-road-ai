"""재생 전 미리보기와 수정된 장면 경계를 실제 브라우저로 확인한다."""
from pathlib import Path
import sys,json,cv2
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
W=ROOT/'outputs/private/late_research_design_20261106';B=W/'icy_road_model'
def main():
    out=W/'video_facade_review';out.mkdir();checks=[];errors=[]
    with sync_playwright() as w:
        browser=w.chromium.launch(headless=True)
        for name,width,height in [('desktop',1440,1000),('tablet',768,1024),('mobile',390,844)]:
            page=browser.new_page(viewport={'width':width,'height':height});page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto((B/'demo/index.html').as_uri());page.evaluate('document.fonts.ready');page.wait_for_timeout(400)
            assert page.locator('video').get_attribute('preload')=='none'
            assert page.locator('video').get_attribute('src') is None and page.locator('#videoCover').is_visible()
            page.wait_for_function('document.querySelector("#videoCover img").complete&&document.querySelector("#videoCover img").naturalWidth>0')
            assert page.evaluate('document.documentElement.scrollWidth')<=width+1
            page.screenshot(path=str(out/(name+'_before_play.png')),full_page=True)
            page.locator('#videoCover').focus();page.keyboard.press('Enter');page.wait_for_function('!document.querySelector("video").paused&&document.querySelector("video").currentTime>.1',timeout=30000)
            page.locator('video').evaluate('v=>v.pause()')
            assert not page.locator('#videoCover').is_visible()
            states=[]
            for button in page.locator('[data-second]').all():
                second=float(button.get_attribute('data-second'));button.focus();page.keyboard.press('Enter')
                page.wait_for_function('document.querySelector("video").currentTime>=Number(document.activeElement.dataset.second)&&document.querySelector("video").currentTime<Number(document.activeElement.dataset.second)+1.5&&!document.querySelector("video").paused',timeout=30000)
                page.locator('video').evaluate('v=>v.pause()');states.append(second)
                assert button.get_attribute('aria-current')=='true'
            assert states==[0,12,21,27,40,47,72,86]
            checks.append(dict(viewport=name,poster_before_play=True,keyboard_seek_seconds=states,no_overflow=True))
            page.goto((B/'start.html').as_uri());page.evaluate('document.fonts.ready');page.screenshot(path=str(out/(name+'_start_firstfold.png')))
            page.close()
        browser.close()
    assert not errors
    cap=cv2.VideoCapture(str(B/'demo/model_demo.webm'))
    for second in [12,27,40,47,72,86]:
        cap.set(cv2.CAP_PROP_POS_MSEC,second*1000);ok,frame=cap.read();assert ok;ok,buffer=cv2.imencode('.png',frame);assert ok;(out/f'chapter_{second}.png').write_bytes(buffer.tobytes())
    cap.release()
    (out/'receipt.json').write_text(json.dumps(dict(status='passed',views=checks,js_errors=errors,visual_review='pending',video_page_sha256=sha(B/'demo/index.html'),raw_video_sha256=sha(B/'demo/model_demo.webm')),ensure_ascii=False,indent=2)+'\n','utf8')
    print('PASS final poster and keyboard chapter controls in three viewports',flush=True)
if __name__=='__main__':main()
