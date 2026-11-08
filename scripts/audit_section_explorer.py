"""구간 검토의 원천 수치·필터·선정 범위·CSV·모바일을 대조한다."""
from pathlib import Path
import sys,json
from urllib.parse import unquote,urlsplit
import numpy as np,pandas as pd
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import write,sha
P=ROOT/'outputs/private';B=P/'competition_submission/icy_road_model';O=P/'editorial_review_20261106/section_browser'
def main():
 assert not O.exists();O.mkdir();f=pd.read_csv(B/'results/sections/section_review.csv',float_precision='round_trip');errors=[];network=[];checks=0
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True);context=browser.new_context(viewport=dict(width=1440,height=1050),accept_downloads=True);page=context.new_page()
  page.on('pageerror',lambda e:errors.append(str(e)))
  def route(r):
   if r.request.url.startswith(('http://','https://')):network.append(r.request.url);r.abort()
   else:r.continue_()
  page.route('**/*',route);page.goto((B/'maps/sections.html').as_uri());page.wait_for_function('window.SECTION_READY===true')
  data=page.evaluate('DATA')
  assert len(data['rows'])==843 and len(data['areas'])==11
  indexed=f.set_index(['seg_id','winter'])
  for r in data['rows']:
   for i,w in enumerate([2024,2025]):
    a=indexed.loc[(r['id'],w)]
    np.testing.assert_array_equal([r['w'][i]['index'],r['w'][i]['availability']],[a.weather_index_100,a.condition_availability]);checks+=2
   assert bool(r['area'])==bool(indexed.loc[(r['id'],2024)].inspection_candidate)
  cases=0
  for mode in ['inspection','exposure','inventory']:
   page.select_option('#view',mode)
   for winter in ['0','1']:
    page.select_option('#year',winter)
    for road in ['all',*sorted(f.route_nm.unique())]:
     page.select_option('#route',road);expected=843 if road=='all' else f.loc[f.winter.eq(2024)&f.route_nm.eq(road)].shape[0]
     assert page.locator('.road').count()==expected;cases+=1
  for a in data['areas']:
   page.select_option('#area',a['area_id']);r=next(r for r in data['rows'] if r['area']==a['area_id'])
   assert page.locator('#exposure24').inner_text()==f"{r['w'][0]['index']:.2f}%"
   assert page.locator('#exposure25').inner_text()==f"{r['w'][1]['index']:.2f}%";cases+=1
  # 산정하지 못한 선형 값은 숫자 0으로 바꾸지 않는다.
  unknown=next((r for r in data['rows'] if r['curve'] is None),None)
  if unknown:
   page.select_option('#route','all');page.locator('.hit[data-id="'+unknown['id']+'"]').dispatch_event('click');assert page.locator('#curve').inner_text()=='산정하지 못함';cases+=1
  page.select_option('#view','inspection');page.select_option('#area','F06')
  page.click('#focus');assert page.locator('#map').get_attribute('viewBox').split()[-2:]==['6','6'];page.click('#reset')
  with page.expect_download() as info:page.click('#download')
  dl=info.value;path=O/dl.suggested_filename;dl.save_as(path);q=pd.read_csv(path);assert len(q)==2
  page.screenshot(path=str(O/'desktop.png'),full_page=True)
  page.set_viewport_size(dict(width=390,height=844));assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.screenshot(path=str(O/'mobile.png'),full_page=True)
  context.close();browser.close()
 assert not errors and not network
 write(O/'receipt.json',dict(status='passed',numeric_values=checks,browser_cases=cases,download_rows=2,external_requests=network,js_errors=errors,mobile_overflow=False,html_sha256=sha(B/'maps/sections.html')))
 print('SECTION EXPLORER VERIFIED',checks,'values;',cases,'browser cases',flush=True)
if __name__=='__main__':main()
