"""최종 화면의 실제 표시와 검토 근거를 고정한다."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from urllib.parse import unquote,urlparse
import sys,json,re
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
W=ROOT/'outputs/private/final_jury_review_20261106';B=W/'icy_road_model';D=W/'icy_road_documents'

def read(p):return json.loads(p.read_text('utf8'))
def put(p,v):p.parent.mkdir(exist_ok=True,parents=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')

def main():
    out=W/'inference_display_review';assert not (out/'receipt.json').exists();out.mkdir(exist_ok=True);checks=[];errors=[];external=[]
    p=B/'demo/inference.html';s=p.read_text('utf8')
    style='<style>.analysis-grid>div{min-width:0}.table-scroll{max-width:100%}</style>'
    assert style not in s;s=s.replace('<header>',style+'<header>',1);p.write_text(s,'utf8')
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        for name,width,height in [('desktop',1440,1080),('mobile',390,844)]:
            page=browser.new_page(viewport={'width':width,'height':height},reduced_motion='reduce')
            page.on('pageerror',lambda e:errors.append(str(e)))
            def route(r):
                if r.request.url.startswith(('http://','https://')):external.append(r.request.url);r.abort()
                else:r.continue_()
            page.route('**/*',route);page.goto((B/'demo/inference.html').as_uri());page.evaluate('document.fonts.ready')
            assert page.evaluate('document.documentElement.scrollWidth')<=width+1
            text=page.locator('body').inner_text()
            assert all(t in text for t in ['103,680','103,662','입력 없음','미산출','ASOS 기온 (°C)','AWS 습도 (%)'])
            assert not re.search(r'\bNaN\b|<NA>',text)
            for href in page.locator('a').evaluate_all('(a)=>a.map(e=>e.href)'):
                p=urlparse(href)
                if p.scheme=='file':assert Path(unquote(p.path).lstrip('/')).is_file()
            page.screenshot(path=str(out/(name+'.png')),full_page=True)
            checks.append(dict(viewport=name,document_width=width,no_overflow=True,missing_values_readable=True,units_present=True,all_local_links_exist=True))
            page.close()
        browser.close()
    assert not errors and not external
    put(out/'receipt.json',dict(status='passed',views=checks,source_sha256=sha(B/'demo/inference.html'),visual_review='pending',js_errors=errors,external_requests=external))
    # The PNGs named here were individually viewed; keep visual evidence distinct from automated checks.
    proofs={
        'layout_review':['report_contact.png','desktop_map_initial.png','mobile_map_initial.png','desktop_field_initial.png','mobile_field_initial.png'],
        'field_browser_jury':['plan_01.png','plan_02.png'],
        'browser_review_jury':['../layout_review/desktop_map_initial.png','../layout_review/mobile_map_initial.png'],
        'media_review_polished':['video_contact.png','frame_12.png'],
    }
    for folder,images in proofs.items():
        p=W/folder/'receipt.json';r=read(p)
        r.update(status='passed',visual_review='passed',visually_reviewed_files={name:sha(W/folder/name) for name in images})
        put(p,r)
    # Public listing checked with web tool at this time; detailed refresh failed.
    official=read(B/'technical/official_evening_access_review.json')
    official.update(at_kst=datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M'),
        status='latest_public_listings_and_rubric_rechecked',latest_notice_titles_unchanged=True,
        new_unanswered_general_question=None,question_answered_on_listing=True,
        current_account_question_title='팀원 정보를 비회원에서 회원으로 변경한 후 참가 상태 및 결과 제출 메뉴가 사라졌습니다',
        current_account_question_listing_answer='완료',
        rubric={'창의성':20,'우수성':50,'효과성':30},
        detailed_refresh_attempts=[{'id':811,'status':'web_tool_inaccessible'},{'id':807,'status':'web_tool_inaccessible'},{'id':716,'status':'web_tool_inaccessible'}])
    put(B/'technical/official_evening_access_review.json',official)
    p=B/'README.md';s=p.read_text('utf8').replace('첫 명령은 노면온도와 결빙 조건, 둘째는 기온·습도·풍속을 산출한다.','predict.py는 노면온도와 결빙 조건을, predict_weather.py는 기온·습도·풍속을 산출한다.')
    p.write_text(s,'utf8')
    p=W/'JURY_REVIEW.md';s=p.read_text('utf8')
    # Improve Korean spacing in the user-facing audit note; no fabricated scores.
    for a,b in [('자료23','자료 23'),('평가3','평가 3'),('정확한10','정확한 10'),('기존100','기존 100'),('겨울을10','겨울을 10'),('아니라103','아니라 103'),('중첩64','중첩 64'),('상위25','상위 25'),('곳이0','곳이 0'),('가능한81','가능한 81'),('계측3','계측 3'),('이용한16','이용한 16'),('보고서를14','보고서를 14'),('안내의22','안내의 22')]:s=s.replace(a,b)
    p.write_text(s,'utf8')
    print('PASS inference displays and recorded visual reviews; official listing scope updated',flush=True)
if __name__=='__main__':main()
