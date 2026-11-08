"""현재 실제 화면을 미리보기로 사용하고 장면·시작 화면을 최종 캡처한다."""
from pathlib import Path
import sys,json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
W=ROOT/'outputs/private/late_research_design_20261106';B=W/'icy_road_model'
def main():
    out=W/'final_reading_screens';out.mkdir()
    with sync_playwright() as w:
        browser=w.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1080},reduced_motion='reduce')
        page.goto((B/'index.html').as_uri());page.wait_for_function('window.WEATHER_READY===true');page.evaluate('document.fonts.ready');page.screenshot(path=str(B/'demo/poster.png'));page.close()
        for name,width,height in [('desktop',1440,1000),('mobile',390,844)]:
            page=browser.new_page(viewport={'width':width,'height':height},reduced_motion='reduce')
            for rel,label in [('start.html','summary'),('demo/index.html','video')]:
                page.goto((B/rel).as_uri());page.evaluate('document.fonts.ready')
                if label=='video':
                    page.wait_for_function('document.querySelector("#videoCover img").complete&&document.querySelector("#videoCover img").naturalWidth>0')
                    assert page.locator('video').get_attribute('src') is None
                page.screenshot(path=str(out/(name+'_'+label+'.png')),full_page=label=='video')
            page.close()
        browser.close()
    (out/'receipt.json').write_text(json.dumps(dict(status='captured',poster_is_current_application_screenshot=True,poster_sha256=sha(B/'demo/poster.png'),visual_review='pending'),ensure_ascii=False,indent=2)+'\n','utf8')
    print('Captured current actual preview and final first views',flush=True)
if __name__=='__main__':main()
