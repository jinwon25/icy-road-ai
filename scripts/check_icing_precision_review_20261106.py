"""정밀도 검토 화면의 표 숫자·로컬 링크·오프라인 로드와 두 화면 크기를 확인한다."""
from pathlib import Path
from datetime import datetime,timezone
import json
from urllib.parse import urlparse,unquote
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/private/icing_precision_review_20261106'

def main():
    receipt=OUT/'browser_audit.json';assert not receipt.exists()
    data=json.loads((OUT/'review.json').read_text('utf8'));rows=data['rows']
    errors=[];external=[];results=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        for name,width,height in [('desktop',1440,1000),('mobile',390,844)]:
            context=browser.new_context(viewport=dict(width=width,height=height))
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            def route(r):
                if r.request.url.startswith(('http://','https://')):
                    external.append(r.request.url);r.abort()
                else:r.continue_()
            page.route('**/*',route)
            page.goto((OUT/'index.html').as_uri())
            page.evaluate('document.fonts.ready')
            page.wait_for_function('Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0)')
            displayed=page.locator('tbody tr').evaluate_all('(rows)=>rows.map(r=>Array.from(r.cells).map(c=>c.textContent.trim()))')
            assert len(displayed)==len(rows)
            for expected,actual in zip(rows,displayed):
                target=[expected['방법'],f"{expected['정밀도']*100:.2f}%",f"{expected['재현율']*100:.2f}%",f"{expected['F1']:.4f}",
                        f"{expected['오경보']:,}",f"{expected['추가누락사건']:,}",expected['판단']]
                assert actual==target,(actual,target)
            dimensions=page.evaluate('({width:innerWidth,document:document.documentElement.scrollWidth,images:document.images.length})')
            assert dimensions['document']<=width+1
            links=page.locator('a').evaluate_all('(a)=>a.map(x=>x.href)')
            local=0
            for href in links:
                parsed=urlparse(href)
                if parsed.scheme=='file':
                    path=Path(unquote(parsed.path).lstrip('/'))
                    assert path.exists(),path
                    local+=1
            page.locator('details').evaluate('(e)=>e.open=true')
            page.screenshot(path=str(OUT/(name+'.png')),full_page=True)
            results.append(dict(viewport=name,rows=len(rows),checked_cells=sum(map(len,displayed)),
                                dimensions=dimensions,local_links=local))
            context.close()
        browser.close()
    assert not errors and not external
    receipt.write_text(json.dumps(dict(status='passed',at_utc=datetime.now(timezone.utc).isoformat(),
        views=results,js_errors=errors,external_requests=external,visual_review='pending'),ensure_ascii=False,indent=2)+'\n','utf8')
    print('PASS',results,flush=True)

if __name__=='__main__':main()
