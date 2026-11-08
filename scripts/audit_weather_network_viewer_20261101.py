"""1472원천행·1840필터 조합·SVG선택·CSV·모바일·외부 요청을 검증한다."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--viewer',type=Path,default=ROOT/'outputs/private/weather_network_viewer_20261101_v1')
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/private/weather_network_viewer_qa_20261101_v1')
    args=parser.parse_args();folder=args.viewer.resolve();out=args.output.resolve()
    if out.exists():raise FileExistsError('Preserve browser verification')
    receipt=json.loads((folder/'summary.json').read_text('utf8'))
    for name,digest in receipt['files'].items():assert sha(folder/name)==digest,name
    text=(folder/'index.html').read_text('utf8')
    data=json.loads(text.split('<script id="payload" type="application/json">',1)[1].split('</script>',1)[0])
    schema={'target':str,'aws':str,**{k:float for k in ['distance_km','age_minutes','air_temp','humidity','wind_speed','rain_15m','dewpoint']}}
    snapshots=pd.read_csv(folder/'snapshot_sources.csv',dtype=schema,float_precision='round_trip')
    pd.testing.assert_frame_equal(pd.DataFrame(data['snapshots']),snapshots,check_exact=True)
    assert len(data['targets'])==23 and len(data['aws'])==34 and len(data['times'])==16 and len(snapshots)==1472
    assert not set(t['station'] for t in data['targets'])&{'12410','33411','23402','33402','33406','12213','23411'}
    out.mkdir();errors=[];network=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True);context=browser.new_context(viewport={'width':1380,'height':1050},accept_downloads=True)
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        def route(r):
            if r.request.url.startswith(('https://','http://')):network.append(r.request.url);r.abort()
            else:r.continue_()
        page.route('**/*',route);page.goto((folder/'index.html').as_uri())
        assert page.locator('circle.target').count()==23 and page.locator('circle.aws').count()==34
        results=page.evaluate('''() => {const results=[];for(const t of D.targets)for(const time of D.times)for(const f of Object.keys(names)){
          $('#station').value=t.station;$('#time').value=time;$('#field').value=f;render();results.push({station:t.station,time,field:f,
          mean:$('#mean').textContent,range:$('#range').textContent,count:$('#count').textContent,
          weights:[...document.querySelectorAll('#sources tbody tr')].map(r=>r.lastChild.textContent),quality:[...document.querySelectorAll('#quality tbody tr')].map(r=>r.textContent)});}return results;}''')
        values=0
        for result in results:
            q=snapshots.loc[snapshots.target.eq(result['station'])&snapshots.time.eq(result['time'])]
            field=result['field'];good=q[field].notna();have=q.loc[good]
            weights=1/np.maximum(have.distance_km.to_numpy(),1.)**2;weights/=weights.sum()
            expect=float(np.sum(have[field].to_numpy()*weights));span=float(have[field].max()-have[field].min())
            assert abs(float(result['mean'])-expect)<=.00500001 and abs(float(result['range'])-span)<=.00500001
            assert result['count']==str(len(have))+' / '+str(len(q))
            j=0
            for usable,shown in zip(good,result['weights']):
                if usable:assert abs(float(shown)-weights[j]*100)<=.05000001;j+=1
                else:assert shown=='—'
            assert len(result['quality'])==2;values+=3+len(q)
        assert len(results)==1840
        page.select_option('#station','12207');page.select_option('#time',data['times'][2]);page.select_option('#field','humidity')
        page.locator('circle[aria-label="도로 23205"]').dispatch_event('click')
        assert page.locator('#station').input_value()=='23205' and '23205' in page.locator('#heading').inner_text()
        with page.expect_download() as info:page.click('#download')
        download=info.value;path=out/download.suggested_filename;download.save_as(path)
        actual=pd.read_csv(path,dtype=schema,float_precision='round_trip')
        expected=snapshots.loc[snapshots.target.eq('23205')&snapshots.time.eq(data['times'][2])].reset_index(drop=True)
        pd.testing.assert_frame_equal(actual,expected,check_exact=True)
        for a in page.locator('footer a').all():
            path=(folder/a.get_attribute('href')).resolve();assert path.is_relative_to(folder) and path.is_file()
        page.screenshot(path=str(out/'desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(out/'mobile.png'),full_page=True)
        context.close();browser.close()
    assert not errors and not network
    record=dict(status='passed_pending_visual_review',html_sha256=sha(folder/'index.html'),source_rows_exact=len(snapshots),
        filter_cases=len(results),rounded_ui_values_checked=values,csv_download_rows=len(actual),svg_click=True,
        mobile_width=390,mobile_horizontal_overflow=False,external_requests=len(network),javascript_errors=len(errors),
        screenshots={p.name:sha(p) for p in out.glob('*.png')},protected_outcomes_read=False)
    (out/'summary.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n','utf8');print(record,flush=True)


if __name__=='__main__':main()
