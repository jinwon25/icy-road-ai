"""PDF 이동·전체 쪽과 포터블 재집계·화면 생성 원본을 검사한다."""
from pathlib import Path
import sys,json,subprocess,os,re
import fitz
from PIL import Image,ImageOps,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.check_markdown import inspect_documents
W=ROOT/'outputs/private/late_research_design_20261106';B=W/'icy_road_model';D=W/'icy_road_documents'
def main():
    out=W/'report_source_final';assert not (out/'receipt.json').exists();out.mkdir(exist_ok=True);doc=fitz.open(B/'report/analysis_report.pdf')
    assert len(doc)==14 and doc.metadata['author']=='로드투인사이트' and len(doc.get_toc())==14
    numbers=[]
    for i,page in enumerate(doc):
        spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for line in b['lines'] for s in line['spans']]
        assert all(s['bbox'][0]>=0 and s['bbox'][2]<=596 and s['bbox'][1]>=0 and s['bbox'][3]<=842 for s in spans)
        foot=[s['text'] for s in spans if s['bbox'][1]>790];assert str(i+1) in foot and any('로드투인사이트' in t for t in foot)
        numbers+=re.findall(r'그림\s+(\d+)\.',page.get_text())
    assert list(map(int,numbers))==list(range(1,13)),numbers
    links=[l for l in doc[0].get_links() if l['kind']==fitz.LINK_GOTO];assert sorted(l['page'] for l in links)==[2,5,9]
    assert '2609.33528' in doc[-1].get_text() and '[14]' in doc[-1].get_text() and '0.0038' in doc[6].get_text() and '0.0039' in doc[6].get_text()
    contact=Image.new('RGB',(1080,4*405),'#dce2e6');draw=ImageDraw.Draw(contact)
    for i in range(14):
        im=Image.open(W/'final_report_pages'/f'{i+1:02d}.png');contact.paste(ImageOps.contain(im,(260,375)),((i%4)*270+5,(i//4)*405+25));draw.text(((i%4)*270+8,(i//4)*405+7),str(i+1),fill='black')
    contact.save(out/'report_contact.png')
    assert sha(B/'report/analysis_report.pdf')==sha(D/'report/analysis_report.pdf')
    for folder in [B,D]:
        names=[p.relative_to(folder).as_posix() for p in folder.rglob('*.md') if 'local_review' not in p.parts]
        assert not inspect_documents(folder,names)
    env=dict(os.environ);env.update(PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
    for command in [
        ['code/analyze_short_forcing_review.py','--output','local_review/final_short_forcing_reproduction'],
        ['code/analyze_aws_short_forcing_review.py','--output','local_review/final_aws_short_forcing_reproduction']]:
        r=subprocess.run([sys.executable,'-X','utf8',*command],cwd=B,env=env,capture_output=True,text=True,encoding='utf8',timeout=240)
        assert r.returncode==0,r.stdout+r.stderr
        print(r.stdout.strip(),flush=True)
    assert sha(B/'local_review/sections_with_result_entry.html')==sha(B/'maps/sections.html')
    record=json.loads((B/'local_review/final_short_forcing_reproduction/receipt.json').read_text('utf8'));assert record['comparison_rows']==24
    other=json.loads((B/'local_review/final_aws_short_forcing_reproduction/receipt.json').read_text('utf8'));assert other['comparison_rows']==24
    receipt=dict(status='passed',pages=14,outline_entries=14,cover_destinations=[3,6,10],figure_numbers=list(range(1,13)),
        pdf_sha256=sha(B/'report/analysis_report.pdf'),page_bounds_and_footers=True,markdown_links=True,short_forcing_metric_rows_exact=24,
        explorer_generated_exact=True,visual_review='pending')
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf8')
    print('PASS PDF structure, Markdown, 24 new metric rows and generated map',flush=True)
if __name__=='__main__':main()
