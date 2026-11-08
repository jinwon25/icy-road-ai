"""실제 로컬 Chromium에서 공식 목록 화면의 필터·수치·확대·모바일을 검증한다."""
from pathlib import Path
import argparse
import sys
import json
import pandas as pd
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha


def main():
    folder=ROOT/'outputs/private/official_inventory_viewer_20261031_v1'
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/private/official_inventory_viewer_qa_20261031_v1')
    out=parser.parse_args().output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
    for name,digest in manifest['files'].items():assert sha(folder/name)==digest
    for name,digest in manifest['source_signatures'].items():assert sha(ROOT/name)==digest
    records=json.loads((folder/'viewer_data.json').read_text(encoding='utf-8'))['rows']
    rows=pd.DataFrame(records).set_index('seg_id')
    weather=pd.read_csv(ROOT/'outputs/private/vulnerability_map_comparison_20261031_v1/two_winter_exposure.csv',dtype={'seg_id':str})
    errors=[];network=[];checks=0
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1320,'height':1000})
        page.on('pageerror',lambda error:errors.append(str(error)))
        def intercept(route):
            if route.request.url.startswith(('https://','http://')):network.append(route.request.url);route.abort()
            else:route.continue_()
        page.route('**/*',intercept)
        page.goto((folder/'index.html').as_uri());page.wait_for_selector('#segmentId')
        assert page.locator('.road').count()==843
        for route in ['all',*sorted(rows.route_nm.unique())]:
            page.select_option('#route',route)
            part=rows if route=='all' else rows.loc[rows.route_nm.eq(route)]
            flows=['all',*sorted(part.flow_lbl.unique())]
            for flow in flows:
                page.select_option('#flow',flow)
                section=part if flow=='all' else part.loc[part.flow_lbl.eq(flow)]
                for scope in ['all','candidate']:
                    page.select_option('#scope',scope)
                    expected=section if scope=='all' else section.loc[section.field_review_candidate]
                    assert page.locator('.road').count()==len(expected)
                    assert page.locator('#segment option').count()==len(expected)
                    assert page.locator('#count').inner_text()==f'{len(expected)}개 보고 구간'
                    if not len(expected):continue
                    for identifier in [expected.index[0],expected.index[-1]]:
                        page.select_option('#segment',identifier)
                        assert page.locator('#segmentId').inner_text()==identifier
                        data=weather.loc[weather.seg_id.eq(identifier)].set_index('winter')
                        for year,suffix in [(2024,'24'),(2025,'25')]:
                            assert page.locator('#winter'+suffix).inner_text()==f'{data.loc[year,"cold_wet_fraction"]*100:.2f}%'
                            assert page.locator('#hours'+suffix).inner_text()==f'{data.loc[year,"cold_wet_hours"]:.1f}시간 / 유효 {data.loc[year,"ice_valid_slots"]}개'
                        page.click('#focus');assert page.locator('#map').get_attribute('viewBox').split()[-2:]==['8','8']
                        page.click('#reset');checks+=1
        page.select_option('#route','all');page.select_option('#flow','all');page.select_option('#scope','all')
        for version in ['2026-09-07','problem_undated','none']:
            page.select_option('#version',version)
            if version=='none':assert page.locator('.inventory').count()==0
            else:assert page.locator('.inventory').count()>0
        page.select_option('#version','2026-09-07')
        chosen=page.locator('.road').nth(50);identifier=chosen.get_attribute('data-id');chosen.dispatch_event('click')
        assert page.locator('#segmentId').inner_text()==identifier
        # 논산/광주 등 특정 이름을 가정하지 않고 실제 후보에서 대표 구간을 고른다.
        candidate=rows.loc[rows.field_review_candidate].index[0];page.select_option('#segment',candidate)
        assert '연속 확인 구간' in page.locator('#screening').inner_text()
        page.screenshot(path=str(out/'desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        page.screenshot(path=str(out/'mobile.png'),full_page=True)
        browser.close()
    assert not errors and not network
    result=dict(status='passed',filter_numeric_cases=checks,winter_numeric_checks=checks*2,
        versions_checked=3,svg_click_checked=True,zoom_checked=True,mobile_horizontal_overflow=False,
        page_errors=errors,network_requests=network,html_sha256=sha(folder/'index.html'),
        source_sha256=sha(folder/'summary.json'),audit_script_sha256=sha(Path(__file__)))
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
