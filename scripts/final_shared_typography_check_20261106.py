"""이동한 화면에서도 한국어 단어와 제목 줄바꿈을 일관되게 유지한다."""
from pathlib import Path
import sys,json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
W=ROOT/'outputs/private/late_research_design_20261106';B=W/'icy_road_model'
def main():
    p=B/'assets/site.css';s=p.read_text('utf8');rule='p,h1,h2,h3,figcaption{word-break:keep-all;overflow-wrap:break-word;text-wrap:pretty}h1,h2,h3{text-wrap:balance}'
    assert rule not in s;p.write_text(s+'\n'+rule+'\n','utf8')
    out=W/'shared_typography_review';out.mkdir();views=[];errors=[]
    with sync_playwright() as w:
        browser=w.chromium.launch(headless=True)
        for name,width,height in [('desktop',1440,1000),('mobile',390,844),('narrow',320,800)]:
            page=browser.new_page(viewport={'width':width,'height':height},reduced_motion='reduce');page.on('pageerror',lambda e:errors.append(str(e)))
            for rel,ready in [('start.html','window.START_READY===true'),('index.html','window.WEATHER_READY===true'),('maps/sections.html','window.SECTION_READY===true'),('results/field/index.html','window.FIELD_READY===true'),('demo/index.html','window.READER_READY===true'),('demo/inference.html','document.readyState==="complete"')]:
                page.goto((B/rel).as_uri());page.wait_for_function(ready,timeout=60000);page.evaluate('document.fonts.ready')
                assert page.evaluate('document.documentElement.scrollWidth')<=width+1,(name,rel)
                if rel in ['results/field/index.html','demo/index.html','start.html']:page.screenshot(path=str(out/(name+'_'+rel.replace('/','_')+'.png')))
                views.append(dict(viewport=name,page=rel,no_overflow=True))
            page.close()
        browser.close()
    assert not errors
    (out/'receipt.json').write_text(json.dumps(dict(status='passed',views=views,css_sha256=sha(p),visual_review='pending',js_errors=errors),ensure_ascii=False,indent=2)+'\n','utf8')
    print('PASS shared type in 18 views',flush=True)
if __name__=='__main__':main()
