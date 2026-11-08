"""복사된 v8 지도 화면의 실제 조작을 녹화하고 상대 다운로드 경로를 확인한다."""
from pathlib import Path
import json
import shutil
import sys
from urllib.parse import unquote,urlsplit
import cv2
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_objective_icing import write,now


def main():
    bundle=ROOT/'outputs/private/submission_candidate_20261031_v8'
    folder=bundle/'research/latest/official_inventory_viewer_20261031_v1'
    out=ROOT/'outputs/private/inventory_walkthrough_20261031_v1'
    out.mkdir(exist_ok=False)
    data=json.loads((folder/'viewer_data.json').read_text(encoding='utf8'))['rows']
    errors=[];network=[];links=[];steps=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':1320,'height':1000},
            record_video_dir=str(out/'raw'),record_video_size={'width':1320,'height':1000})
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        def intercept(route):
            if route.request.url.startswith(('https://','http://')):network.append(route.request.url);route.abort()
            else:route.continue_()
        page.route('**/*',intercept);page.goto((folder/'index.html').as_uri());page.wait_for_selector('#segmentId')
        assert page.locator('.road').count()==843
        for link in page.locator('a[download]').all():
            relative=unquote(urlsplit(link.get_attribute('href')).path)
            path=(folder/relative).resolve()
            assert path.is_relative_to(bundle.resolve()) and path.is_file()
            links.append(dict(path=path.relative_to(bundle).as_posix(),sha256=sha(path),bytes=path.stat().st_size))
        assert len(links)>=3
        page.evaluate("""()=>{const e=document.createElement('div');e.id='recording-caption';e.style.cssText='position:fixed;bottom:12px;left:3%;width:94%;padding:14px 20px;box-sizing:border-box;border-radius:10px;background:rgba(22,46,66,.96);color:white;font:18px/1.55 sans-serif;z-index:99999;text-align:center;pointer-events:none';document.body.appendChild(e)}""")
        def caption(text,seconds=3):
            page.locator('#recording-caption').evaluate('(e,t)=>e.textContent=t',text)
            steps.append(text);page.wait_for_timeout(seconds*1000)
        caption('전북 3개 고속도로 · 공식 취약구간과 두 겨울 기상 조건을 함께 확인합니다.')
        page.select_option('#version','problem_undated')
        caption('문제 제시 목록입니다. 기준일과 방향이 명시되지 않은 부분은 그대로 남겼습니다.')
        page.select_option('#version','2026-09-07')
        caption('2026년 9월 7일 최신 목록과 비교합니다. 과거 지정 현황이나 위험 변화로 소급하지 않습니다.')
        page.select_option('#route','서해안고속국도');page.select_option('#scope','candidate')
        identifier=next(r['seg_id'] for r in data if r['route_nm']=='서해안고속국도' and r['field_review_candidate'])
        page.select_option('#segment',identifier)
        assert page.locator('#segmentId').inner_text()==identifier
        caption('최신 목록 밖의 현장 확인 후보를 선택합니다. 두 겨울 노출과 유효 시각을 함께 봅니다.',4)
        page.click('#focus');assert page.locator('#map').get_attribute('viewBox').split()[-2:]==['8','8']
        caption('선택 구간을 확대합니다. 표시한 이정은 암거 자료로 보간한 추정 위치입니다.',4)
        page.click('#reset');page.select_option('#route','all');page.select_option('#scope','all')
        caption('318개 보고 구간을 방향별 8개 연속 범위로 묶었습니다. 같은 기상 입력과 동률을 포함합니다.',4)
        caption('CSV·GIS는 같은 폴더에서 열 수 있습니다. 결빙 확률이나 공식 A/B/C 등급을 새로 검증한 결과는 아닙니다.',4)
        page.locator('#recording-caption').evaluate('(e)=>e.remove()')
        page.screenshot(path=str(out/'desktop.png'),full_page=True)
        video=page.video;context.close();raw=Path(video.path());browser.close()
    assert not errors and not network
    target=out/'inventory_comparison_walkthrough.webm';shutil.copy2(raw,target)
    capture=cv2.VideoCapture(str(target));assert capture.isOpened()
    frames=int(capture.get(cv2.CAP_PROP_FRAME_COUNT));fps=capture.get(cv2.CAP_PROP_FPS)
    width=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT));assert fps>0 and frames/fps>=24
    for seconds in [2,12,19,25]:
        capture.set(cv2.CAP_PROP_POS_MSEC,seconds*1000);ok,frame=capture.read();assert ok
        encoded,buffer=cv2.imencode('.png',frame);assert encoded
        # Windows OpenCV의 한글 파일 경로 쓰기 실패를 피하고 저장 여부를 확인한다.
        (out/f'frame_{seconds:02d}.png').write_bytes(buffer.tobytes())
    capture.release()
    write(out/'receipt.json',dict(status='recorded_and_paths_verified',at_utc=now(),frames=frames,fps=fps,
        duration_seconds=frames/fps,width=width,height=height,video_sha256=sha(target),
        html_sha256=sha(folder/'index.html'),local_downloads=links,steps=steps,network_requests=network,
        page_errors=errors,actual_browser_recording=True,independent_performance_evaluation=False,
        source_script_sha256=sha(Path(__file__))))
    print('RECORDED',frames/fps,'seconds',len(links),'local download paths',flush=True)


if __name__=='__main__':main()
