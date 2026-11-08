"""본문 제목과 책갈피의 쉬운 표현을 맞추고 최종 쪽을 렌더한다."""
from pathlib import Path
import sys,subprocess,os,json,shutil
import fitz
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
W=ROOT/'outputs/private/late_research_design_20261106';B=W/'icy_road_model';D=W/'icy_road_documents'
def main():
    pdf=B/'report/analysis_report.pdf';before=W/'report_before_heading_alignment.pdf';assert not before.exists()
    old=fitz.open(pdf);toc=old.get_toc();old.close()
    p=ROOT/'scripts/render_readable_final_report_body_20261106.py';s=p.read_text('utf8')
    for a,b in {
        '학습에서 제외한 지점의 노면온도':'학습에 쓰지 않은 지점의 온도 오차',
        '비교 기준으로 확인한 노면온도 추정의 가치':'같은 자료로 비교한 노면온도 오차',
        '도로 기상 추정':'도로의 기온·습도·풍속 추정',
        '결빙 판정의 성능과 오경보':'결빙 판정에서 맞힌 경우와 놓친 경우',
        '영하·적설 조건과 실제 결빙 사이의 차이':'추운 날씨와 실제 도로 결빙은 달랐다',
        '기상요소와 결빙 조건의 관계':'어떤 기상 조건에서 판정이 늘었는가',
        '겨울별 조건 노출과 도로환경':'두 겨울의 저온·수분 조건과 도로환경',
        '공개 목록과 기상 기준의 관계':'기존 취약구간과 우리 기준의 비교',
        '추가 계측·시설 확인 범위':'추가로 관측하고 현장을 확인할 두 범위',
        '선정 기준을 바꾸면 남는 구간':'기준을 바꿔도 남는 구간은 어디인가',
        '지형에서 확인할 낮의 일사 환경':'지형 때문에 햇빛이 가려질 수 있는 시간',
        '활용 범위와 결론':'활용할 수 있는 범위와 남은 확인',
    }.items():s=s.replace(a,b)
    s=s.replace(" h('질문별로 읽기')"," h('궁금한 부분부터 읽기')\n p('쪽 번호를 누르면 해당 부분으로 이동한다.',small)")
    p.write_text(s,'utf8');assert pdf.resolve().is_relative_to(W.resolve());pdf.rename(before)
    record=W/'report_build.json';backup=W/'report_build_before_heading_alignment.json';assert not backup.exists();record.rename(backup)
    r=subprocess.run([sys.executable,'-X','utf8',str(p)],cwd=ROOT,env=dict(os.environ),capture_output=True,text=True,encoding='utf8',timeout=180);assert r.returncode==0,r.stdout+r.stderr
    doc=fitz.open(pdf);assert len(doc)==14;doc.set_toc(toc)
    for label,target in [('3-4쪽',2),('6-7쪽',5),('10-13쪽',9)]:
        matches=doc[0].search_for(label);assert len(matches)==1
        rect=matches[0];doc[0].insert_link({'kind':fitz.LINK_GOTO,'from':rect+(-5,-4,5,4),'page':target,'to':fitz.Point(0,0)})
        doc[0].draw_line(fitz.Point(rect.x0,rect.y1+1),fitz.Point(rect.x1,rect.y1+1),color=(.16,.33,.43),width=.5)
    temp=B/'report/readable_navigation.pdf';assert not temp.exists();doc.save(temp,garbage=4,deflate=True);doc.close()
    saved=W/'report_before_last_navigation.pdf';assert not saved.exists();pdf.rename(saved);temp.rename(pdf)
    shutil.copyfile(pdf,D/'report/analysis_report.pdf');(D/'report/analysis_report.md').write_text((B/'report/analysis_report.md').read_text('utf8').replace('](figures/','](../figures/'),'utf8')
    pages=W/'final_report_pages';pages.mkdir();doc=fitz.open(pdf)
    for i,page in enumerate(doc):page.get_pixmap(matrix=fitz.Matrix(1.7,1.7),alpha=False).save(pages/f'{i+1:02d}.png')
    (W/'report_final.json').write_text(json.dumps(dict(status='rendered_pending_review',pages=14,pdf_sha256=sha(pdf),bookmarks=14,cover_links=3,references=14,word_wrap='word boundaries'),ensure_ascii=False,indent=2)+'\n','utf8')
    print('Rendered final 14 pages with aligned plain-language headings and navigation',flush=True)
if __name__=='__main__':main()
