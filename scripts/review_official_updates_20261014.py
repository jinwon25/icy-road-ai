"""현재 공개 게시글을 동적으로 수집하고 10월13일 답변·자료·공지와 대조."""
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin
import hashlib
import json
import re
import sys
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import review_official_updates_20261013 as public
from scripts.compare_official_answers_20261013 import fields,normalized
from scripts.evaluate_method_blending import read,write,preservation
from src.data_source import sha256_file as sha

OUT=ROOT/'outputs/private/official_updates_20261014_v1'
OLD=ROOT/'outputs/private/official_updates_20261013_v2'


def clean(value):return re.sub(r'data:image/[^;,]+;base64,[A-Za-z0-9+/=]+','[embedded image omitted]',value)


def main():
    if (OUT/'summary.json').exists():raise FileExistsError('Preserve completed official review')
    freeze=preservation();OUT.mkdir(exist_ok=True);public.OUT=OUT
    receipts=read(OUT/'fetch_receipts.json') if (OUT/'fetch_receipts.json').exists() else []
    def fetch(name,path):
        absolute=urljoin(public.BASE,path)
        previous=next((r for r in receipts if r['name']==name and r['url']==absolute and r.get('status')==200),None)
        if previous:
            file=OUT/previous['file'];assert sha(file)==previous['sha256'];return file
        public.fetch(name,urljoin(public.BASE,path),receipts)
        receipts[-1]['checked_date_kst']='2026-10-14'
        (OUT/'fetch_receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf-8')
        r=receipts[-1]
        if r.get('status')!=200:raise RuntimeError('Public response failed: '+name)
        return OUT/r['file']
    inventory={}
    for name,path in public.SOURCES.items():
        file=fetch(name,path);soup=BeautifulSoup(file.read_bytes(),'html.parser');rows=[]
        for tr in soup.select('tr'):
            cells=[n.get_text(' ',strip=True) for n in tr.select('td')]
            links=[a.get('href','') for a in tr.select('a[href]')]
            if cells:rows.append(dict(cells=cells,links=links))
        inventory[name]=dict(rows=rows)
    notice_ids={}
    for row in inventory['notice_list']['rows']:
        if not any(c.startswith('2026-') for c in row['cells']):continue
        for link in row['links']:
            m=re.search(r'fn_select_detail\((\d+)\)',link)
            if m:notice_ids[m.group(1)]=row['cells']
    # 실제 목록에서 사용하는JavaScript명도 확인한다.
    if not notice_ids:
        for row in inventory['notice_list']['rows']:
            if not any(c.startswith('2026-') for c in row['cells']):continue
            for link in row['links']:
                m=re.search(r'\((?:[\"\x27])?(\d+)',link)
                if m:notice_ids[m.group(1)]=row['cells']
    if len(notice_ids)<4:raise ValueError('Current notices were not fully parsed')
    problem_ids={}
    for row in inventory['problem_board']['rows']:
        for link in row['links']:
            m=re.search(r'fn_select_detail\((\d+)\)',link)
            if m:problem_ids[m.group(1)]=row['cells']
    if not problem_ids:raise ValueError('Problem questions were not parsed')
    general_ids={};pages=[]
    for index in range(1,11):
        file=OUT/'general_qna_list.html' if index==1 else fetch('general_qna_page_'+str(index),f'/competition/main/qna.do?pageIndex={index}')
        soup=BeautifulSoup(file.read_bytes(),'html.parser');found=[]
        for tr in soup.select('tr'):
            cells=[n.get_text(' ',strip=True) for n in tr.select('td')];a=tr.find('a',href=re.compile('fn_select_detail'))
            if not cells or not a:continue
            identifier=re.search(r'fn_select_detail\((\d+)\)',a['href']).group(1)
            if any(c.startswith('2026-') for c in cells):general_ids[identifier]=cells;found.append(identifier)
        pages.append(dict(page=index,current_2026_ids=found))
        if not found:break
        marker=soup.find('input',attrs={'name':'pageIndex'})
        if index>1 and marker and marker.get('value')!=str(index):raise ValueError('Pagination mismatch')
    detail={}
    for kind,identifiers in [('notice',notice_ids),('problem_qa',problem_ids),('general_qa',general_ids)]:
        for identifier in identifiers:
            if kind=='notice':url=f'/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId={identifier}'
            elif kind=='problem_qa':url=f'/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId={identifier}'
            else:url=f'/competition/main/selectQna.do?bbsId=BBSMSTR_BBBBBBBBBBBB&nttId={identifier}'
            name=kind+'_'+identifier;file=fetch(name,url);current=fields(file);old=fields(OLD/(name+'.html')) if (OLD/(name+'.html')).exists() else {}
            answer_keys=[k for k in current if k!='nttCn' and current[k].strip()]
            detail[name]=dict(id=identifier,fields=list(current),answer_present=bool(answer_keys),new_since_previous=not bool(old),
                normalized_fields_unchanged=set(current)==set(old) and all(normalized(current[k])==normalized(old[k]) for k in current),
                source_sha256=sha(file))
            sanitized={k:clean(v) for k,v in current.items()}
            clean_path=OUT/(name+'_fields_clean.json')
            if clean_path.exists():assert read(clean_path)==sanitized
            else:write(clean_path,sanitized)
    # 문제 본문은 공개JSON만 조회한다. 승인 사용자용 전체ZIP은 다시 받지 않는다.
    tabs_path=fetch('problem_tabs','/competition/main/problem/loadOverview.do?probId=PROB_000000000004604')
    tabs=read(tabs_path);old_tabs=read(OLD/'problem_tabs.bin')
    tab_comparisons=[dict(title=a['title'],content_unchanged=a['content']==b['content'],sha256=hashlib.sha256(a['content'].encode()).hexdigest()) for a,b in zip(tabs['overviewList'],old_tabs['overviewList'])]
    public_surfaces={}
    for name in ['evaluate','finalsubmit','submitAnswer','leaderboard']:
        file=fetch('public_'+name,f'/competition/problem/PROB_000000000004604/detail/{name}.do')
        soup=BeautifulSoup(file.read_bytes(),'html.parser')
        for node in soup(['script','style']):node.decompose()
        public_surfaces[name]=dict(final_url=receipts[-1]['final_url'],text_excerpt=soup.get_text(' ',strip=True)[-1300:])
    assert preservation()==freeze
    result=dict(status='official_public_update_review_complete',checked_at_utc=datetime.now(timezone.utc).isoformat(),checked_date_kst='2026-10-14',
        responses=len(receipts),notice_ids=notice_ids,problem_question_ids=problem_ids,general_2026_question_ids=general_ids,pagination=pages,
        detail_comparisons=detail,tabs=tab_comparisons,public_surfaces=public_surfaces,
        account_login=False,account_approval_verified=False,full_data_zip_downloaded=False,competition_submitted=False,external_messages_sent=False,
        old_frozen_files=freeze[0],reserved_frozen_files=freeze[1])
    write(OUT/'inventory.json',inventory);write(OUT/'summary.json',result)
    print('공개 검토',len(receipts),'응답','공지',len(notice_ids),'문제Q&A',len(problem_ids),'일반2026Q&A',len(general_ids))
    print('새 게시글·변경된 답변',[n for n,r in detail.items() if r['new_since_previous'] or not r['normalized_fields_unchanged']])


if __name__=='__main__':main()
