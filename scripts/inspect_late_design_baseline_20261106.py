"""현재 첫 화면·영상 열람·표의 실제 화면과 의미 구조를 기록한다."""
from pathlib import Path
import sys,json,gzip
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/private/late_research_design_20261106';B=W/'icy_road_model'
def main():
    out=W/'baseline_screens_distinct';out.mkdir();facts=[]
    with sync_playwright() as w:
        browser=w.chromium.launch(headless=True)
        for name,width,height in [('desktop',1440,1000),('mobile',390,844)]:
            page=browser.new_page(viewport={'width':width,'height':height},reduced_motion='reduce')
            for rel,ready in [('index.html','window.WEATHER_READY===true'),('demo/index.html','document.querySelector("video").readyState>=2'),('demo/inference.html','document.readyState==="complete"')]:
                page.goto((B/rel).as_uri());page.wait_for_function(ready,timeout=60000);page.evaluate('document.fonts.ready');page.screenshot(path=str(out/(name+'_'+rel.replace('/','_')+'.png')),full_page=rel!='index.html')
                facts.append(dict(viewport=name,page=rel,h1=page.locator('h1').all_text_contents(),headings=page.locator('h2').all_text_contents(),image_alternatives=page.locator('img').evaluate_all('(a)=>a.map(x=>({src:x.getAttribute("src"),alt:x.getAttribute("alt")}))'),overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth+1')))
            page.close()
        browser.close()
    (out/'facts.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n','utf8')
    viewer=json.loads(gzip.decompress((B/'viewer_data.json.gz').read_bytes()))
    print('Viewer top keys:',list(viewer)[:15],flush=True)
    for key,value in viewer.items():
        if isinstance(value,list):print('LIST',key,len(value),'first keys',list(value[0])[:18] if value and isinstance(value[0],dict) else str(value[:1])[:80],flush=True)
    print(json.dumps([dict(page=x['page'],viewport=x['viewport'],headings=x['headings']) for x in facts],ensure_ascii=False),flush=True)
if __name__=='__main__':main()
