"""실제 오프라인 HTML 추론 데모의 브라우저 화면을 영상으로 기록한다."""
from pathlib import Path
import shutil
import sys
import cv2
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write
from src.data_source import sha256_file as sha
OUT=ROOT/'outputs/private/submission_candidate_20261013_v1'


def main():
    target=OUT/'demo/inference_demo.webm'
    if target.exists():raise FileExistsError('Preserve actual demo recording')
    errors=[];requests=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':1280,'height':1200},record_video_dir=str(OUT/'validation/video_raw'),record_video_size={'width':1280,'height':1200})
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        def route(r):
            if r.request.url.startswith(('http://','https://')):requests.append(r.request.url);r.abort()
            else:r.continue_()
        page.route('**/*',route);page.goto((OUT/'demo/index.html').as_uri());page.wait_for_selector('#temperature');page.wait_for_timeout(1600)
        for i in [0,24,48,72,96,120,143]:
            page.locator('#slot').evaluate('(e,v)=>{e.value=v;e.dispatchEvent(new Event("input"));}',i)
            page.wait_for_timeout(1200)
        page.wait_for_timeout(1600);video=page.video;context.close();source=Path(video.path());browser.close()
    assert not errors and not requests;shutil.copy2(source,target)
    capture=cv2.VideoCapture(str(target));assert capture.isOpened()
    frames=int(capture.get(cv2.CAP_PROP_FRAME_COUNT));fps=capture.get(cv2.CAP_PROP_FPS);width=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    ok,frame=capture.read();assert ok;cv2.imwrite(str(OUT/'validation/video_first_frame.png'),frame);capture.release()
    assert frames>100 and fps>0
    write(OUT/'validation/video_receipt.json',dict(status='actual_browser_demo_recorded',frames=frames,fps=fps,duration_seconds=frames/fps,
        width=width,height=height,video_sha256=sha(target),external_requests=0,console_errors=errors,
        real_browser_recording=True,independent_performance_evaluation=False,source=source.name))
    print(read(OUT/'validation/video_receipt.json'))


if __name__=='__main__':main()
