"""단일 HTML의 전량 수치·압축 자료·실제 브라우저 필터/그래프/CSV·모바일을 검증한다."""
import argparse
import csv
import gzip
import io
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit,unquote
import numpy as np
import pandas as pd
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--viewer',type=Path,default=ROOT/'outputs/private/weather_explorer_20261101_v1')
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/private/weather_explorer_validation_20261101_v1')
    args=parser.parse_args();folder=args.viewer.resolve();out=args.output.resolve()
    if out.exists():raise FileExistsError('Preserve browser review')
    receipt=json.loads((folder/'summary.json').read_text(encoding='utf8'))
    for name,h in receipt['files'].items():assert sha(folder/name)==h,name
    source=ROOT/receipt['source']
    for name,h in receipt['source_data_sha256'].items():assert sha(source/name)==h,name
    data=json.loads(gzip.decompress((folder/'viewer_data.json.gz').read_bytes()))
    w=pd.read_csv(source/'weather_segments_500m.csv',float_precision='round_trip').set_index(['seg_id','winter'])
    d=pd.read_csv(source/'weather_segment_daily.csv.gz',float_precision='round_trip').sort_values(['seg_id','date'])
    assert len(data['rows'])==843 and sum(r['unknown'] for r in data['rows'])==50
    fields=['air_temperature_mean','relative_humidity_mean','wind_speed_mean']
    columns=[*fields,'air_temperature_valid_slots','relative_humidity_valid_slots','wind_speed_valid_slots','humidity_history_outside_slots','humidity_history_partial_slots']
    numeric=0;lookup={r['id']:r for r in data['rows']}
    for identifier,part in d.groupby('seg_id',sort=True):
        row=lookup[identifier]
        values=np.array([[np.nan if x is None else x for x in q] for q in row['days']],float)
        np.testing.assert_allclose(values,part[columns].to_numpy(),atol=.500001e-6,rtol=0,equal_nan=True);numeric+=values.size
        for i,year in enumerate([2024,2025]):
            record=w.loc[(identifier,year)];state=row['w'][i]
            np.testing.assert_array_equal(state['mean'],record[fields].to_numpy())
            np.testing.assert_array_equal(state['coverage'],record[columns[3:6]].to_numpy(float)/17280)
            assert state['outside']==record.humidity_history_outside_fraction and state['partial']==record.humidity_history_partial_fraction
            numeric+=8
    out.mkdir();errors=[];network=[];cases=0;downloads=[];links=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':1380,'height':1050},accept_downloads=True)
        page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
        def route(request):
            if request.request.url.startswith(('https://','http://')):network.append(request.request.url);request.abort()
            else:request.continue_()
        page.route('**/*',route);page.goto((folder/'index.html').as_uri())
        page.wait_for_function('window.WEATHER_READY===true || window.WEATHER_ERROR',timeout=60000)
        assert page.evaluate('window.WEATHER_READY===true'),page.locator('#loading').inner_text()
        assert page.locator('.road').count()==843
        for anchor in page.locator('a[download]').all():
            path=(folder/unquote(urlsplit(anchor.get_attribute('href')).path)).resolve()
            assert path.is_relative_to(folder.parent) and path.is_file()
            links.append(dict(relative=anchor.get_attribute('href'),sha256=sha(path)))
        for metric in range(5):
            page.select_option('#metric',str(metric))
            for winter in range(2):
                page.select_option('#winter',str(winter))
                for route_name in ['all',*sorted({r['route'] for r in data['rows']})]:
                    page.select_option('#route',route_name)
                    for quality in ['all','new','outside']:
                        page.select_option('#quality',quality)
                        expected=[r for r in data['rows'] if (route_name=='all' or r['route']==route_name) and
                            (quality=='all' or (r['unknown'] if quality=='new' else r['w'][winter]['outside']>.25))]
                        assert page.locator('.road').count()==len(expected)
                        if not expected:
                            assert page.locator('#empty').is_visible() and page.locator('#segment').is_disabled();cases+=1;continue
                        identifier=expected[-1]['id'];page.select_option('#segment',identifier)
                        assert page.locator('#segmentId').inner_text()==identifier
                        record=w.loc[(identifier,2024+winter)]
                        for j,suffix in enumerate(['24','25']):
                            original=w.loc[(identifier,2024+j)]
                            v=original[fields[metric]] if metric<3 else 100*original['humidity_history_outside_fraction' if metric==3 else 'humidity_history_partial_fraction']
                            unit=['°C','%','m/s','%','%'][metric]
                            assert page.locator('#value'+suffix).inner_text()==f'{v:.2f} {unit}'
                        assert page.locator('.chartline').count()==2
                        cases+=1
        page.select_option('#quality','all');page.select_option('#route','all');page.select_option('#metric','1');page.select_option('#winter','0')
        for flow in sorted({r['flow'] for r in data['rows']}):
            page.select_option('#flow',flow)
            assert page.locator('.road').count()==sum(r['flow']==flow for r in data['rows']);cases+=1
        page.select_option('#flow','all')
        identifier=next(r['id'] for r in data['rows'] if r['unknown'])
        page.locator(f'.hit[data-id="{identifier}"]').dispatch_event('click')
        assert page.locator('#segmentId').inner_text()==identifier and '172' in page.locator('#sourceNote').inner_text()
        page.click('#focus');assert page.locator('#map').get_attribute('viewBox').split()[-2:]==['8','8']
        page.click('#reset');np.testing.assert_array_equal([float(v) for v in page.locator('#map').get_attribute('viewBox').split()],data['box'])
        page.locator('#chart').hover(position={'x':130,'y':80});assert '2024/25' in page.locator('#hover').inner_text()
        with page.expect_download() as info:page.click('#download')
        download=info.value;path=out/download.suggested_filename;download.save_as(path)
        parsed=pd.read_csv(path,float_precision='round_trip',dtype={'seg_id':str});assert len(parsed)==240 and parsed.seg_id.eq(identifier).all()
        np.testing.assert_allclose(parsed.iloc[:,2:].to_numpy(float),np.asarray(lookup[identifier]['days'],float),atol=1e-12,rtol=0,equal_nan=True)
        downloads.append(dict(rows=len(parsed),sha256=sha(path),path=path.name))
        page.screenshot(path=str(out/'desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(out/'mobile.png'),full_page=True)
        context.close();browser.close()
    assert not errors and not network
    result=dict(status='passed',viewer_summary_sha256=sha(folder/'summary.json'),html_sha256=sha(folder/'index.html'),
        numeric_values_checked=numeric,filter_browser_cases=cases,downloads=downloads,relative_downloads=links,
        network_requests=network,page_errors=errors,mobile_horizontal_overflow=False,svg_click_and_zoom=True,
        screenshots={name:sha(out/name) for name in ['desktop.png','mobile.png']},pending_visual_review=True,audit_sha256=sha(Path(__file__)))
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('WEATHER EXPLORER VERIFIED',numeric,cases,flush=True)


if __name__=='__main__':main()
