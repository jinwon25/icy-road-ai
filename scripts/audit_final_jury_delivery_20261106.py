"""확정 화면·영상이 실제로 열리고 읽히는지 검수한다."""
from pathlib import Path
import json,sys,re
from urllib.parse import urlparse,unquote
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts import audit_polished_jury_media_20261106 as media
W=ROOT/'outputs/private/final_jury_review_20261106';B=W/'icy_road_model'

def main():
    assert (W/'demo_build_final.json').is_file()
    media.O=W/'media_review_final';media.main()
    out=W/'inference_display_final';out.mkdir();checks=[]
    with sync_playwright() as w:
        browser=w.chromium.launch(headless=True)
        for name,width,height in [('desktop',1440,1080),('mobile',390,844)]:
            page=browser.new_page(viewport={'width':width,'height':height});page.goto((B/'demo/inference.html').as_uri());page.evaluate('document.fonts.ready')
            assert page.evaluate('document.documentElement.scrollWidth')<=width+1
            text=page.locator('body').inner_text()
            assert '103,680' in text and '103,662' in text and '입력 없음' in text and '미산출' in text
            assert not re.search(r'\bNaN\b|<NA>',text)
            command=page.locator('pre').inner_text();assert '\n' not in command.strip()
            for href in page.locator('a').evaluate_all('(a)=>a.map(e=>e.href)'):
                p=urlparse(href)
                if p.scheme=='file':assert Path(unquote(p.path).lstrip('/')).is_file()
            page.screenshot(path=str(out/(name+'.png')),full_page=True)
            checks.append(dict(viewport=name,no_overflow=True,missing_values_readable=True,command_copyable=True))
            page.close()
        browser.close()
    (out/'receipt.json').write_text(json.dumps(dict(status='passed',views=checks,source_sha256=sha(B/'demo/inference.html'),visual_review='pending'),ensure_ascii=False,indent=2)+'\n','utf8')
    print('PASS final inference displays; visual review pending',flush=True)
if __name__=='__main__':main()
