"""자체 오프라인 탐색 화면을 실제 Chromium에서 조작하며 WebM으로 녹화한다."""
import argparse
import json
from pathlib import Path
import sys
import time
import cv2
import pandas as pd
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dashboard',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    dashboard=args.dashboard.resolve();out=args.output.resolve()
    if out.exists():raise FileExistsError('Preserve previous browser recording')
    source=json.loads((dashboard/'source_snapshot.json').read_text('utf-8'))
    assert source['html_sha256']==sha(dashboard/'index.html') and not source['visual_review_pending']
    segments=pd.read_csv(dashboard/'segment_estimates.csv',dtype={'seg_id':str,'prediction_group':str},float_precision='round_trip')
    daily=pd.read_csv(dashboard/'prediction_group_daily.csv',dtype={'prediction_group':str},float_precision='round_trip')
    out.mkdir(parents=True);errors=[];requests=[];events=[];started=time.perf_counter()
    with sync_playwright() as pl:
        browser=pl.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':1280,'height':1000},accept_downloads=True,
            record_video_dir=str(out/'raw'),record_video_size={'width':1280,'height':1000})
        page=context.new_page();video=page.video
        page.on('pageerror',lambda e:errors.append(str(e)))
        def intercept(route):
            if route.request.url.startswith(('https://','http://')):requests.append(route.request.url);route.abort()
            else:route.continue_()
        page.route('**/*',intercept)
        def step(label,hold=1800):
            events.append(dict(seconds=round(time.perf_counter()-started,3),action=label,
                scale=page.locator('#scale').input_value(),winter=page.locator('#winter').input_value(),
                route=page.locator('#route').input_value(),segment=page.locator('#segmentId').inner_text()))
            page.wait_for_timeout(hold)
        page.goto((dashboard/'index.html').as_uri());page.wait_for_selector('#meanTemp')
        step('500m 전체 구간 보기',2200);page.screenshot(path=str(out/'start.png'))
        page.select_option('#metric','estimated_temp_mean_c');step('지도 지표를 평균 추정 온도로 전환')
        page.select_option('#winter','2025');step('2025/26 겨울 선택')
        page.select_option('#route','호남고속국도');step('호남 노선 선택')
        selected=segments.loc[segments.scale_m.eq(500)&segments.winter.eq(2025)&segments.route_nm.eq('호남고속국도')].iloc[10]
        page.select_option('#segment',f'500|2025|{selected.seg_id}')
        assert page.locator('#meanTemp').inner_text()==f'{selected.estimated_temp_mean_c:.2f} °C'
        step('구간 선택과 관측소·환경 연결 확인')
        page.locator('#dayReadout').scroll_into_view_if_needed()
        expected=daily.loc[daily.prediction_group.eq(selected.prediction_group)&daily.winter.eq(2025)].sort_values('date_kst').reset_index(drop=True)
        for index in [0,20,40,60,80,119]:
            page.locator('#day').evaluate('(e,v)=>{e.value=v;e.dispatchEvent(new Event("input"));}',index)
            readout=page.locator('#dayReadout').inner_text();row=expected.iloc[index]
            assert row.date_kst[:10] in readout and f'{row.estimated_temp_mean_c:.2f} °C' in readout
            step(f'일별 결과 {index+1}번째 날짜',750)
        page.screenshot(path=str(out/'middle.png'))
        with page.expect_download() as event:page.click('#download')
        event.value.save_as(out/'selected_daily.csv')
        actual=pd.read_csv(out/'selected_daily.csv',dtype={'seg_id':str,'prediction_group':str},float_precision='round_trip')
        pd.testing.assert_frame_equal(actual[expected.columns],expected,check_dtype=False,check_exact=True)
        assert len(actual)==120 and actual.seg_id.eq(selected.seg_id).all()
        step('선택 구간의 120일 CSV 다운로드',1800)
        page.evaluate('window.scrollTo(0,0)');page.select_option('#scale','1000');page.select_option('#route','all')
        page.select_option('#metric','cold_wet_fraction');step('1km 전체 구간의 조건 노출로 전환',2200)
        page.screenshot(path=str(out/'end.png'))
        context.close();video.save_as(str(out/'review_walkthrough.webm'))
        (out/'video_check.html').write_text('<!doctype html><meta charset="utf-8"><video src="review_walkthrough.webm" controls muted autoplay></video>','utf-8')
        viewer=browser.new_page();viewer.route('**/*',intercept)
        viewer.on('pageerror',lambda e:errors.append(str(e)))
        viewer.goto((out/'video_check.html').as_uri())
        viewer.wait_for_function('document.querySelector("video").currentTime > .2 && !document.querySelector("video").error')
        browser.close()
    assert not errors and not requests
    cap=cv2.VideoCapture(str(out/'review_walkthrough.webm'));assert cap.isOpened()
    fps=cap.get(cv2.CAP_PROP_FPS);frames=0
    while True:
        ok,frame=cap.read()
        if not ok:break
        assert frame.shape[:2]==(1000,1280);frames+=1
    cap.release();assert fps>0 and 18<=frames/fps<=90
    probes={min(frames-1,int(2*fps)):'video_start.png',frames//2:'video_middle.png',max(0,frames-int(fps)):'video_end.png'}
    cap=cv2.VideoCapture(str(out/'review_walkthrough.webm'));index=0;decoded=[]
    while True:
        ok,frame=cap.read()
        if not ok:break
        if index in probes:
            ok,encoded=cv2.imencode('.png',frame);assert ok
            (out/probes[index]).write_bytes(encoded.tobytes());decoded.append(probes[index])
        index+=1
    cap.release();assert index==frames and len(decoded)==3
    receipt=dict(status='actual_browser_walkthrough_recorded_and_decoded',video='review_walkthrough.webm',
        frames=frames,fps=fps,seconds=frames/fps,events=events,download_rows=120,download_numeric_exact=True,
        errors=errors,external_requests=requests,html_sha256=sha(dashboard/'index.html'),
        video_sha256=sha(out/'review_walkthrough.webm'),code_sha256=sha(Path(__file__)),
        screenshots={name:sha(out/name) for name in ['start.png','middle.png','end.png']},
        decoded_frame_sha256={name:sha(out/name) for name in decoded},
        actual_browser_recording=True,browser_playback_passed=True,
        live_model_refit_or_inference=False,visual_review_pending=True)
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf-8')
    print('Actual browser recording decoded',frames,'frames',round(frames/fps,2),'seconds',flush=True)


if __name__=='__main__':main()
