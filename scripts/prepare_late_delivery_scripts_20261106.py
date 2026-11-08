"""검증된 포장 절차에 새 요약 화면·연구 재집계·PDF 이동 검사를 추가한다."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def swap(s,a,b):assert s.count(a)==1,(a,s.count(a));return s.replace(a,b)
def main():
    s=(ROOT/'scripts/package_jury_submission_20261106.py').read_text('utf8')
    s=swap(s,"W=P/'final_jury_review_20261106'","W=P/'late_research_design_20261106'")
    s=swap(s,"allowed={'README.md'","allowed={'index.html','README.md'")
    s=s.replace("B/'local_review/sections_review_ready.html'","B/'local_review/sections_with_result_entry.html'")
    s=swap(s,"facts.update(field_comparison_plan=", "facts.update(short_forcing_review=read(B/'technical/short_forcing_review.json'),aws_short_forcing_review=read(B/'technical/aws_short_forcing_review.json'),current_result_entry='start.html',field_comparison_plan=")
    s=swap(s,"'results/field/index.html','demo/model_demo.webm']}","'results/field/index.html','demo/model_demo.webm','start.html','demo/poster.png']}")
    s=swap(s,"new_model_fits=0,unconstrained_threshold_searches=16,unconstrained_candidate_promoted=False,", "new_model_fits=40,production_model_refits=0,short_forcing_threshold_searches=32,short_forcing_candidates_promoted=0,unconstrained_threshold_searches=16,unconstrained_candidate_promoted=False,\n        result_summary='start.html',pdf_bookmarks=14,pdf_cover_links=3,video_chapters=8,keyboard_tested=True,")
    s=swap(s,"if channel=='model':m['current_field_plan']='results/field/index.html'", "if channel=='model':m.update(current_field_plan='results/field/index.html',current_result_entry='start.html')")
    s=swap(s,"    assert verify_preserved()==frozen\n    for kind in FOLDERS:","""    run(['code/analyze_short_forcing_review.py','--output','local_review/short_forcing_review'])
    run(['code/analyze_aws_short_forcing_review.py','--output','local_review/aws_short_forcing_review'])
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':390,'height':844})
        page.goto((model/'start.html').as_uri());page.wait_for_function('window.START_READY===true')
        assert page.locator('.route-line').count()==3 and page.evaluate('document.documentElement.scrollWidth')<=391
        page.goto((model/'demo/index.html').as_uri());page.wait_for_function('window.DEMO_READY===true')
        assert page.locator('#videoCover').is_visible() and page.locator('video').get_attribute('src') is None
        page.locator('[data-second="86"]').click();page.wait_for_function('document.querySelector("video").currentTime>=86&&!document.querySelector("video").paused',timeout=30000)
        page.locator('video').evaluate('v=>v.pause()');browser.close()
    assert verify_preserved()==frozen
    for kind in FOLDERS:""")
    s=swap(s,"extracted_archives_verified=True,extracted_model_inference_rows_exact=103680,", "extracted_archives_verified=True,extracted_result_summary_and_video_verified=True,extracted_short_forcing_metric_rows_exact=48,extracted_model_inference_rows_exact=103680,")
    p=ROOT/'scripts/package_late_submission_20261106.py';assert not p.exists();p.write_text(s,'utf8')
    print('Prepared archive checks for summary, video controls and two research comparisons',flush=True)
if __name__=='__main__':main()
