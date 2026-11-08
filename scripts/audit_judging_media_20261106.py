"""현재 HTML·숫자 대비·실제 WebM 재생과 주요 장면을 확인한다."""
from pathlib import Path
from urllib.parse import urlparse,unquote
import sys,json
import cv2
from PIL import Image,ImageOps,ImageDraw
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.seal_protected_weather_20261106 import W,write
from src.data_source import sha256_file as sha
B=W/'icy_road_model';O=W/'media_review'

def main():
    O.mkdir();errors=[];external=[];results=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        for name,width,height in [('desktop',1440,1000),('mobile',390,844)]:
            context=browser.new_context(viewport={'width':width,'height':height});page=context.new_page()
            page.on('pageerror',lambda e:errors.append(str(e)))
            def route(r):
                if r.request.url.startswith(('http://','https://')):external.append(r.request.url);r.abort()
                else:r.continue_()
            page.route('**/*',route)
            for relative,ready in [('index.html','window.WEATHER_READY===true'),('maps/sections.html','window.SECTION_READY===true'),('demo/index.html','document.querySelector("video").readyState>=2')]:
                page.goto((B/relative).as_uri());page.wait_for_function(ready,timeout=60000)
                page.evaluate('document.fonts.ready')
                assert page.evaluate('document.documentElement.scrollWidth')<=width+1,(name,relative)
                for href in page.locator('a').evaluate_all('(rows)=>rows.map(a=>a.href)'):
                    parsed=urlparse(href)
                    if parsed.scheme=='file':assert Path(unquote(parsed.path).lstrip('/')).is_file(),href
                if relative=='index.html':
                    assert '14.6%' in page.locator('#benchmarks').inner_text()
                    assert page.locator('#map .road').count()==843
                    page.locator('#benchmarks').scroll_into_view_if_needed()
                    page.screenshot(path=str(O/(name+'_benchmarks.png')))
                elif relative=='maps/sections.html':
                    assert page.locator('#scenarioCount').get_attribute('data-count')=='22'
                    contrasts=[]
                    for margin in ['100','250','500']:
                        page.locator('#matrixMargin').select_option(margin)
                        contrasts+=page.locator('#matrix button').evaluate_all("""rows=>{function L(s){let a=s.match(/[0-9.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});return .2126*a[0]+.7152*a[1]+.0722*a[2]}return rows.map(e=>{let c=getComputedStyle(e),a=L(c.color),b=L(c.backgroundColor);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)})}""")
                    assert min(contrasts)>=4.5,min(contrasts)
                    page.locator('#restore').click();page.locator('#matrix').scroll_into_view_if_needed()
                    page.screenshot(path=str(O/(name+'_matrix.png')))
                else:
                    metadata=page.eval_on_selector('video','v=>({duration:v.duration,width:v.videoWidth,height:v.videoHeight})')
                    assert 59<=metadata['duration']<=100 and (metadata['width'],metadata['height'])==(1440,1080),metadata
                    page.eval_on_selector('video','async v=>{await v.play()}')
                    page.wait_for_function('document.querySelector("video").currentTime>.2',timeout=10000)
                    page.eval_on_selector('video','v=>{v.pause();v.currentTime=38}')
                    page.wait_for_function('Math.abs(document.querySelector("video").currentTime-38)<.2')
                    page.screenshot(path=str(O/(name+'_video.png')),full_page=True)
                results.append(dict(viewport=name,page=relative,no_page_overflow=True))
            context.close()
        browser.close()
    assert not errors and not external,(errors,external)
    video=B/'demo/model_demo.webm';cap=cv2.VideoCapture(str(video));assert cap.isOpened()
    frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=cap.get(cv2.CAP_PROP_FPS);seconds=frames/fps
    assert abs(seconds-metadata['duration'])<.6
    selected=[3,13,19,28,35,41,47,54,min(62,seconds-2)]
    for i,second in enumerate(selected,1):
        cap.set(cv2.CAP_PROP_POS_MSEC,second*1000);ok,frame=cap.read();assert ok and frame.shape==(1080,1440,3)
        success,encoded=cv2.imencode('.png',frame);assert success;(O/f'frame_{i:02d}.png').write_bytes(encoded.tobytes())
    cap.release()
    contact=Image.new('RGB',(990,3*395),'#dce2e6');draw=ImageDraw.Draw(contact)
    for i,second in enumerate(selected):
        im=Image.open(O/f'frame_{i+1:02d}.png');contact.paste(ImageOps.contain(im,(320,360)),((i%3)*330+5,(i//3)*395+25))
        draw.text(((i%3)*330+8,(i//3)*395+7),f'{second:.1f}s',fill='black')
    contact.save(O/'video_contact.png')
    write(O/'receipt.json',dict(status='passed',html_views=results,video_metadata=metadata,actual_playback=True,seek_second=38,
        video_sha256=sha(video),decoded_frames=len(selected),minimum_numeric_button_contrast=float(min(contrasts)),
        js_errors=errors,external_requests=external,visual_review='pending',
        source_files={p.relative_to(B).as_posix():sha(p) for p in [B/'index.html',B/'maps/sections.html',B/'demo/index.html',video]}))
    print('PASS',len(results),'HTML views; video',round(metadata['duration'],2),'seconds;',len(selected),'decoded frames; minimum contrast',round(min(contrasts),2),flush=True)

if __name__=='__main__':main()
