"""자체 로컬 구간 화면의 필터·수치·날짜·다운로드·모바일 배치를 실제 Chromium으로 검산한다."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha


def main():
    p = argparse.ArgumentParser();p.add_argument('--dashboard',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    dashboard=args.dashboard.resolve();out=args.output.resolve()
    if out.exists(): raise FileExistsError('Preserve previous browser QA')
    out.mkdir(parents=True)
    source=json.loads((dashboard/'source_snapshot.json').read_text('utf-8'))
    assert sha(dashboard/'index.html')==source['html_sha256']
    segments=pd.read_csv(dashboard/'segment_estimates.csv',dtype={'seg_id':str,'prediction_group':str},float_precision='round_trip')
    daily=pd.read_csv(dashboard/'prediction_group_daily.csv',dtype={'prediction_group':str},float_precision='round_trip')
    errors=[];requests=[];checks=[]
    with sync_playwright() as pl:
        browser=pl.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1280,'height':1000},accept_downloads=True)
        page.on('pageerror',lambda e:errors.append(str(e)))
        def intercept(route):
            if route.request.url.startswith(('http://','https://')): requests.append(route.request.url);route.abort()
            else: route.continue_()
        page.route('**/*',intercept)
        page.goto((dashboard/'index.html').as_uri())
        page.wait_for_selector('#meanTemp')
        for scale in [500,1000]:
            page.select_option('#scale',str(scale))
            for winter in [2024,2025]:
                page.select_option('#winter',str(winter))
                for route in ['all',*sorted(segments.route_nm.unique())]:
                    page.select_option('#route',route)
                    part=segments.loc[segments.scale_m.eq(scale)&segments.winter.eq(winter)]
                    if route!='all':part=part.loc[part.route_nm.eq(route)]
                    assert int(page.locator('#segmentCount').inner_text().replace(',',''))==len(part)
                    assert page.locator('#segment option').count()==len(part)
                    assert int(page.locator('#groupCount').inner_text())==part.prediction_group.nunique()
                    for position in sorted(set([0,len(part)//2,len(part)-1])):
                        r=part.iloc[position]
                        page.select_option('#segment',f'{scale}|{winter}|{r.seg_id}')
                        assert page.locator('#segmentId').inner_text()==r.seg_id
                        assert page.locator('#meanTemp').inner_text()==f'{r.estimated_temp_mean_c:.2f} °C'
                        assert page.locator('#exposure').inner_text()==f'{r.cold_wet_fraction*100:.1f}%'
                        expected=daily.loc[daily.prediction_group.eq(r.prediction_group)&daily.winter.eq(winter)].sort_values('date_kst')
                        for i in [0,59,119]:
                            page.locator('#day').evaluate('(e,v)=>{e.value=v;e.dispatchEvent(new Event("input"));}',i)
                            text=page.locator('#dayReadout').inner_text();d=expected.iloc[i]
                            assert d.date_kst[:10] in text
                            assert f'{d.estimated_temp_mean_c:.2f} °C' in text
                            assert f'{d.cold_wet_hours:.1f}시간' in text
                        checks.append({'scale':scale,'winter':winter,'route':route,'segment':r.seg_id})
        page.select_option('#scale','500');page.select_option('#winter','2024');page.select_option('#route','all')
        # 지도의 실제 SVG 선을 클릭해 선택 연결을 확인한다.
        target=page.locator('#map .road').nth(50)
        segid=target.get_attribute('data-id');target.dispatch_event('click')
        assert page.locator('#segmentId').inner_text()==segid
        page.select_option('#metric','estimated_temp_mean_c')
        assert '평균 추정' in page.locator('#mapTitle').inner_text()
        page.locator('#day').evaluate('(e)=>{e.value=40;e.dispatchEvent(new Event("input"));}')
        page.click('#next');assert page.locator('#day').input_value()=='41'
        page.click('#prev');assert page.locator('#day').input_value()=='40'
        with page.expect_download() as event: page.click('#download')
        download=event.value;download.save_as(out/'selected_daily.csv')
        expected_segment=segments.loc[segments.seg_id.eq(segid)&segments.scale_m.eq(500)&segments.winter.eq(2024)].iloc[0]
        expected=daily.loc[daily.prediction_group.eq(expected_segment.prediction_group)&daily.winter.eq(2024)].sort_values('date_kst').reset_index(drop=True)
        actual=pd.read_csv(out/'selected_daily.csv',dtype={'seg_id':str,'prediction_group':str},float_precision='round_trip')
        assert len(actual)==120 and actual.seg_id.eq(segid).all()
        pd.testing.assert_frame_equal(actual[expected.columns],expected,check_dtype=False,check_exact=True)
        page.screenshot(path=str(out/'desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path=str(out/'mobile.png'),full_page=True)
        browser.close()
    assert not errors and not requests
    receipt=dict(status='dashboard_browser_numeric_filter_download_checks_passed',segment_checks=len(checks),
        date_checks=len(checks)*3,checks=checks,download_rows=120,download_numeric_exact=True,
        svg_click_selects_segment=True,metric_switch=True,previous_next_day=True,
        errors=errors,external_requests=requests,mobile_no_horizontal_overflow=True,
        html_sha256=sha(dashboard/'index.html'),visual_review_pending=True,
        screenshot_sha256={n:sha(out/n) for n in ['desktop.png','mobile.png']})
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf-8')
    print('Dashboard checks passed',len(checks),'segments and',len(checks)*3,'dates',flush=True)


if __name__=='__main__':main()
