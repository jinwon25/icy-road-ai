"""로컬 HTML의 슬라이더·모바일·콘솔·외부 요청을 실제 헤드리스브라우저에서 검증."""
from pathlib import Path
import sys
import pandas as pd
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import write,read
from src.data_source import sha256_file as sha
OUT=ROOT/'outputs/private/submission_candidate_20261013_v1'


def main():
    target=OUT/'validation/demo_browser_receipt.json'
    if target.exists():raise FileExistsError('Preserve browser demo audit')
    errors=[];requests=[];f=pd.read_csv(OUT/'validation/cli_example_roundtrip.csv')
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1280,'height':1040})
        page.on('pageerror',lambda e:errors.append(str(e)))
        def route(r):
            if r.request.url.startswith(('http://','https://')):requests.append(r.request.url);r.abort()
            else:r.continue_()
        page.route('**/*',route)
        page.goto((OUT/'demo/index.html').as_uri());page.wait_for_selector('#temperature')
        assert page.locator('#time').inner_text()==f.time.iloc[72]+' KST'
        for i in [0,36,72,143]:
            page.locator('#slot').evaluate('(e,v)=>{e.value=v;e.dispatchEvent(new Event("input"));}',i)
            assert page.locator('#time').inner_text()==f.time.iloc[i]+' KST'
            assert page.locator('#temperature').inner_text()==f'{f.estimated_road_temp_c.iloc[i]:.2f} °C'
        page.screenshot(path=str(OUT/'validation/demo_desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        page.screenshot(path=str(OUT/'validation/demo_mobile.png'),full_page=True)
        browser.close()
    assert not errors and not requests
    write(target,dict(status='candidate_local_demo_browser_passed',slider_slots_verified=[0,36,72,143],console_errors=errors,external_requests=len(requests),
        mobile_no_horizontal_overflow=True,html_sha256=sha(OUT/'demo/index.html'),visual_review_pending=True))
    print(read(target))


if __name__=='__main__':main()
