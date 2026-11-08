"""움직임이 끝난 초기 화면·목록 대조·PDF 전체 쪽을 실제 크기로 확인한다."""
from pathlib import Path
from urllib.parse import urlparse,unquote
import json,sys,re
import fitz
from PIL import Image,ImageOps,ImageDraw
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
W=ROOT/'outputs/private/final_jury_review_20261106';B=W/'icy_road_model';O=W/'layout_review'
def main():
    O.mkdir();errors=[];external=[];checks=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        for name,width,height in [('desktop',1440,1080),('mobile',390,844)]:
            context=browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce')
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            def route(r):
                if r.request.url.startswith(('http://','https://')):external.append(r.request.url);r.abort()
                else:r.continue_()
            page.route('**/*',route)
            for rel,ready,label in [('maps/sections.html','window.SECTION_READY===true','map'),('index.html','window.WEATHER_READY===true','weather'),('results/field/index.html','window.FIELD_READY===true','field'),('demo/index.html','document.querySelector("video").readyState>=2','video')]:
                page.goto((B/rel).as_uri());page.wait_for_function(ready,timeout=60000);page.evaluate('document.fonts.ready')
                page.evaluate("document.documentElement.style.scrollBehavior='auto';scrollTo(0,0)")
                page.wait_for_function('scrollY<2')
                assert page.evaluate('document.documentElement.scrollWidth')<=width+1,(rel,width)
                here=urlparse(page.url)
                for href in page.locator('a').evaluate_all('(es)=>es.map(e=>e.href)'):
                    x=urlparse(href)
                    if x.scheme=='file':
                        assert Path(unquote(x.path).lstrip('/')).is_file(),href
                        if x.path==here.path and x.fragment:assert page.locator('[id="'+x.fragment+'"]').count()>0,href
                page.screenshot(path=str(O/(name+'_'+label+'_initial.png')))
                if label=='map':
                    assert page.locator('#view').input_value()=='review'
                    counts=page.evaluate('window.REVIEW_COUNTS');assert counts=={'listed':81,'additional':3,'environment':195,'unknown':22,'other':542},counts
                    page.locator('#inventoryAgreement').evaluate("e=>e.scrollIntoView({block:'start',behavior:'instant'})")
                    page.screenshot(path=str(O/(name+'_inventory.png')))
                checks.append(dict(viewport=name,page=rel,no_horizontal_overflow=True,local_links_and_local_fragments=True))
            context.close()
        browser.close()
    assert not errors and not external,(errors,external)
    doc=fitz.open(B/'report/analysis_report.pdf');assert len(doc)==14 and doc.metadata['author']=='로드투인사이트'
    labels=[]
    for i,page in enumerate(doc):
        spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for line in b['lines'] for s in line['spans']]
        assert all(s['bbox'][0]>=0 and s['bbox'][2]<=596 and s['bbox'][1]>=0 and s['bbox'][3]<=842 for s in spans)
        foot=[s['text'] for s in spans if s['bbox'][1]>790]
        assert str(i+1) in foot and any('로드투인사이트' in t for t in foot)
        labels+=re.findall(r'그림\s+(\d+)\.',page.get_text())
    assert [int(x) for x in labels]==list(range(1,len(labels)+1)),labels
    contact=Image.new('RGB',(1080,4*405),'#dce2e6');draw=ImageDraw.Draw(contact)
    for i in range(14):
        im=Image.open(W/'report_pages'/f'{i+1:02d}.png')
        contact.paste(ImageOps.contain(im,(260,375)),((i%4)*270+5,(i//4)*405+25))
        draw.text(((i%4)*270+8,(i//4)*405+7),str(i+1),fill='black')
    contact.save(O/'report_contact.png')
    receipt=dict(status='passed_pending_visual_review',views=checks,pdf_pages=14,pdf_sha256=sha(B/'report/analysis_report.pdf'),
        figure_numbers=[int(x) for x in labels],page_bounds_and_footers=True,js_errors=errors,external_requests=external)
    (O/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(dict(status=receipt['status'],html_views=len(checks),pdf_pages=14,figures=len(labels)),ensure_ascii=False),flush=True)
if __name__=='__main__':main()
