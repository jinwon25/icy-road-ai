"""배포 위치에서 실제 WebM 재생·이동·링크·모바일 배치를 확인한다."""
from pathlib import Path
import sys,json
from urllib.parse import unquote,urlsplit
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import write,sha
B=ROOT/'outputs/private/submission_candidate_20261106_v14';O=B/'validation/v14_demo_browser'
def main():
 assert not O.exists();O.mkdir();errors=[];external=[]
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True);context=browser.new_context(viewport=dict(width=1380,height=1000));page=context.new_page()
  page.on('pageerror',lambda x:errors.append(str(x)))
  def route(r):
   if r.request.url.startswith(('http://','https://')):external.append(r.request.url);r.abort()
   else:r.continue_()
  page.route('**/*',route);page.goto((B/'demo/index_v14.html').as_uri())
  page.wait_for_function('document.querySelector("video").readyState>=2',timeout=60000)
  initial=page.eval_on_selector('video','v=>({duration:v.duration,width:v.videoWidth,height:v.videoHeight,source:v.currentSrc})')
  assert abs(initial['duration']-80)<.5 and initial['width']==1440 and initial['height']==900 and initial['source'].endswith('.webm'),initial
  page.eval_on_selector('video','async v=>{await v.play()}');page.wait_for_function('document.querySelector("video").currentTime>0.25',timeout=20000)
  page.eval_on_selector('video','v=>{v.pause();v.currentTime=44}');page.wait_for_function('Math.abs(document.querySelector("video").currentTime-44)<0.2')
  page.screenshot(path=str(O/'desktop.png'),full_page=True)
  links=[]
  for a in page.locator('a').all():
   target=(B/'demo'/unquote(urlsplit(a.get_attribute('href')).path)).resolve();assert target.is_relative_to(B) and target.is_file();links.append(dict(name=a.inner_text(),sha256=sha(target)))
  page.set_viewport_size(dict(width=390,height=844));page.screenshot(path=str(O/'mobile.png'),full_page=True)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  context.close();browser.close()
 assert not errors and not external
 write(O/'receipt.json',dict(status='passed',html_sha256=sha(B/'demo/index_v14.html'),webm_sha256=sha(B/'demo/final_review_v14.webm'),
 metadata=initial,actual_playback=True,seek_second=44,relative_links=links,external_requests=external,js_errors=errors,mobile_width=390))
 print('DEMO BROWSER PASSED actual VP8 playback, seek, relative links, mobile',flush=True)
if __name__=='__main__':main()
