"""계측 계획 화면·PDF·미측정 CSV와 작성 파일의 실제 브라우저 동작을 검증한다."""
from pathlib import Path
from urllib.parse import urlparse,unquote
import csv,io,json,sys
import fitz,numpy as np,pandas as pd,geopandas as gpd
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
W=ROOT/'outputs/private/final_jury_review_20261106';B=W/'icy_road_model';F=B/'results/field';O=W/'field_browser_jury'

def main():
    O.mkdir();errors=[];external=[];checks=[]
    # 생성 코드와 별도로 전체 후보의 거리를 다시 계산해 선정을 대조한다.
    review=pd.read_csv(B/'results/sections/section_review.csv',dtype={'seg_id':str})
    plans=pd.read_csv(B/'results/sections/field_review_plan.csv').set_index('area_id')
    cases=json.loads((F/'field_cases.json').read_text('utf8'))
    compare=pd.read_csv(F/'comparison_candidates.csv',dtype={'comparison_seg_id':str})
    g=gpd.read_file(B/'results/sections/risk_review.gpkg',layer='winter_2024',engine='pyogrio').to_crs(5179).set_index('seg_id')
    for c in cases:
        r=plans.loc[c['id']]
        a=gpd.GeoSeries(gpd.points_from_xy([r.representative_midpoint_lon],[r.representative_midpoint_lat]),crs=4326).to_crs(5179).iloc[0]
        q=review.loc[(review.route_nm==c['route'])&(review.flow_lbl==c['direction'])].copy()
        ref=q.loc[q.seg_id==c['selected']['ids'][0]].set_index('winter').weather_information_group
        good=[]
        for sid,part in q.groupby('seg_id'):
            if part.inspection_candidate.any() or part.condition_availability.min()<.95 or not part.chainage_available.all():continue
            if not part.set_index('winter').weather_information_group.sort_index().equals(ref.sort_index()):continue
            distance=g.loc[sid].geometry.interpolate(.5,normalized=True).distance(a)
            if distance<=2000:good.append((distance,sid))
        expected=min(good)
        assert expected[1]==c['comparator']['id']
        assert abs(expected[0]-c['comparator']['distance_m'])<1e-6
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        for label,width,height in [('desktop',1440,1100),('tablet',768,1024),('mobile',390,844)]:
            ctx=browser.new_context(viewport={'width':width,'height':height},accept_downloads=True)
            page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            def route(r):
                if r.request.url.startswith(('https://','http://')):external.append(r.request.url);r.abort()
                else:r.continue_()
            page.route('**/*',route)
            page.goto((F/'index.html').as_uri());page.wait_for_function('window.FIELD_READY===true');page.evaluate('document.fonts.ready')
            assert page.evaluate('document.documentElement.scrollWidth')<=width+1
            assert page.locator('article.case').count()==2 and page.locator('.area-map svg').count()==2
            assert page.locator('input[type=number]').count()==12
            assert all(not v for v in page.locator('input[type=number]').evaluate_all('(es)=>es.map(e=>e.value)'))
            if label=='desktop':
                assert (F/'field_measurement_plan.pdf').is_file()
            for href in page.locator('a').evaluate_all('(es)=>es.map(e=>e.href)'):
                parts=urlparse(href)
                if parts.scheme=='file':assert Path(unquote(parts.path).lstrip('/')).is_file(),href
            page.screenshot(path=str(O/(label+'_start.png')))
            page.locator('#S02').scroll_into_view_if_needed();page.screenshot(path=str(O/(label+'_S02.png')))
            with page.expect_download() as d:page.locator('#csv').click()
            empty=O/(label+'_unmeasured.csv');d.value.save_as(str(empty))
            rows=list(csv.DictReader(io.StringIO(empty.read_text('utf-8-sig'))))
            assert len(rows)==4 and all(r['road_temperature_c']=='' and r['location_verified']=='false' and r['moisture_state']=='미측정' for r in rows)
            page.locator('#S01 summary').click()
            page.locator('#S01_A_road_temperature_c').fill('-2.4')
            page.locator('#S01_A_relative_humidity_pct').fill('101')
            assert not page.locator('#S01_A_relative_humidity_pct').evaluate('(e)=>e.checkValidity()')
            page.locator('#csv').click()
            assert '입력값의 범위' in page.locator('#status').inner_text()
            page.locator('#S01_A_relative_humidity_pct').fill('85')
            page.locator('#S01_A_moisture_state').select_option('습윤')
            page.locator('#S01_A_notes').fill('검증 전용, "기록"')
            page.locator('#S01_verified').check()
            page.locator('#S01_time').fill('2026-11-06T19:30')
            with page.expect_download() as d:page.locator('#save').click()
            saved=O/(label+'_test_record.json');d.value.save_as(str(saved))
            with page.expect_download() as d:page.locator('#csv').click()
            filled=O/(label+'_test_record.csv');d.value.save_as(str(filled))
            rows=list(csv.DictReader(io.StringIO(filled.read_text('utf-8-sig'))))
            assert rows[0]['road_temperature_c']=='-2.4' and rows[0]['notes']=='검증 전용, "기록"'
            assert rows[0]['location_verified']=='true' and rows[2]['location_verified']=='false'
            assert rows[1]['road_temperature_c']=='' and rows[2]['road_temperature_c']==''
            page.reload();page.wait_for_function('window.FIELD_READY===true')
            assert page.locator('#S01_A_road_temperature_c').input_value()=='-2.4'
            page.evaluate('localStorage.clear()');page.reload();page.wait_for_function('window.FIELD_READY===true')
            assert page.locator('#S01_A_road_temperature_c').input_value()==''
            page.locator('#file').set_input_files(str(saved));assert page.locator('#S01_A_road_temperature_c').input_value()=='-2.4'
            bad=O/(label+'_invalid.json');bad.write_text(json.dumps(dict(purpose='field_measurement_record',fields={'S01_A_road_temperature_c':'33','S01_verified':'bad'})),'utf8')
            page.locator('#file').set_input_files(str(bad));assert page.locator('#S01_A_road_temperature_c').input_value()=='-2.4'
            page.evaluate('localStorage.clear()');page.reload();page.wait_for_function('window.FIELD_READY===true')
            page.locator('#S01 summary').click();page.locator('#S01 details').scroll_into_view_if_needed()
            page.screenshot(path=str(O/(label+'_blank_form.png')))
            assert page.evaluate('document.documentElement.scrollWidth')<=width+1
            ctx.close();checks.append(dict(viewport=label,width=width,unmeasured_csv_rows=4,draft_roundtrip=True,csv_roundtrip=True,invalid_import_atomic=True,no_horizontal_overflow=True))
        browser.close()
    assert not errors and not external,(errors,external)
    pdf=fitz.open(F/'field_measurement_plan.pdf');assert len(pdf)==2,len(pdf)
    for i,page in enumerate(pdf):
        t=page.get_text();assert '로드투인사이트' in t and f'S0{i+1}' in t and 'Terrain context produced' in t
        assert '기록을 입력하려면' not in t
        page.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(O/f'plan_{i+1:02d}.png')
    receipt=dict(status='passed_pending_visual_review',comparators_independently_verified=2,
        viewports=checks,js_errors=errors,external_requests=external,pdf_pages=2,
        source_sha256={p.relative_to(B).as_posix():sha(p) for p in F.iterdir() if p.is_file()},
        actual_field_measurements=0,test_entries_excluded_from_package=True)
    (O/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(dict(status=receipt['status'],viewports=3,pdf_pages=2),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
