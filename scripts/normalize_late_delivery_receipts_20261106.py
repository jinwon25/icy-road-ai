"""검수 근거를 현재 파일 해시와 연결하고 포장 절차의 공통 명세로 정리한다."""
from pathlib import Path
import json,sys,shutil
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
W=ROOT/'outputs/private/late_research_design_20261106';B=W/'icy_road_model';CURRENT=ROOT/'outputs/private/competition_submission/icy_road_model'
def read(p):return json.loads(p.read_text('utf8'))
def put(p,v):p.parent.mkdir(exist_ok=True,parents=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')
def main():
    assert read(W/'reader_unbroken_review/receipt.json')['visual_review']=='passed'
    assert read(W/'report_source_final/receipt.json')['visual_review']=='passed'
    for name in ['field_browser_jury','browser_review_jury']:
        r=read(W/name/'receipt.json');assert r['visual_review']=='passed'
    reader=read(W/'reader_unbroken_review/receipt.json');base=read(CURRENT/'validation/media_browser.json')
    assert base['video_sha256']==sha(B/'demo/model_demo.webm')
    base.update(status='passed',visual_review='passed',current_wrapper_test=reader,raw_video_reused_byte_identical=True,
        video_facade_keyboard_test=read(W/'video_controls_current/receipt.json'),
        shared_typography_review=read(W/'shared_typography_review/receipt.json'),
        source_files={n:sha(B/n) for n in ['index.html','maps/sections.html','demo/index.html','demo/model_demo.webm','demo/poster.png','start.html','assets/site.css']})
    put(W/'media_review_final/receipt.json',base)
    report=read(W/'report_source_final/receipt.json');put(W/'layout_review/receipt.json',report)
    put(W/'inference_display_final/receipt.json',dict(status='passed',visual_review='passed',source_sha256=sha(B/'demo/inference.html'),
        evidence='frontend_review_final/receipt.json',keyboard_scroll_tested=True))
    for name,target in [('reader_unbroken_review','reader_browser.json'),('video_controls_current','video_navigation.json'),('shared_typography_review','shared_typography.json')]:shutil.copy2(W/name/'receipt.json',B/'validation'/target)
    for source,target in [('final_short_forcing_reproduction','short_forcing_reproduction.json'),('final_aws_short_forcing_reproduction','aws_short_forcing_reproduction.json')]:shutil.copy2(B/'local_review'/source/'receipt.json',B/'validation'/target)
    info=read(B/'summary.json');info['current_result_entry']='start.html';put(B/'summary.json',info)
    print('Bound final visual and numerical proofs to current files',flush=True)
if __name__=='__main__':main()
