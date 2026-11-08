"""공식 공개 목록·상세·서약을 curl로 수집하기 위한 재현 가능한 계획과 대조 영수증."""
import argparse
from datetime import datetime,timezone
import hashlib,json,re,sys
from pathlib import Path
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.compare_official_answers_20261013 import fields,normalized
OUT=ROOT/'outputs/private/official_curl_review_20261106_v1'
OLD=ROOT/'outputs/private/official_research_review_20261031_v1'
BASE='https://aida.kisti.re.kr'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def write(p,x):
    with p.open('x',encoding='utf8') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def config(label,sources):
    lines=['parallel','parallel-max = 4','connect-timeout = 10','max-time = 40','fail','show-error']
    for name,url in sources.items():
        assert not (OUT/(name+'.bin')).exists(),name
        lines += ['url = '+json.dumps(BASE+url),'output = '+json.dumps((OUT/(name+'.bin')).relative_to(ROOT).as_posix())]
    write(OUT/(label+'_sources.json'),sources)
    (OUT/(label+'.curl')).write_text('\n'.join(lines)+'\n',encoding='utf8')
def inventory(path,kind):
    soup=BeautifulSoup(path.read_bytes(),'html.parser');rows={}
    for tr in soup.select('tr'):
        cells=[c.get_text(' ',strip=True) for c in tr.select('td')]
        if kind!='problem_qa' and not any(c.startswith('2026-') for c in cells):continue
        for a in tr.select('a[href]'):
            match=re.search(r'fn_select_detail\([\"\x27]?(\d+)',a['href'])
            if match:rows[match.group(1)]=cells
    return rows

def pages():
    sources={'general_qna_page_'+str(i):'/competition/main/qna.do?pageIndex='+str(i) for i in range(2,11)}
    sources['problem_board_page_2']='/competition/problem/PROB_000000000004604/detail/commuBoard.do?pageIndex=2'
    config('pages',sources)

def details():
    inv={kind:inventory(OUT/(name+'.bin'),kind) for kind,name in [('notice','notice_list'),('general_qa','general_qna_list'),('problem_qa','problem_board')]}
    for i in range(2,11):
        rows=inventory(OUT/f'general_qna_page_{i}.bin','general_qa')
        if not rows:break
        inv['general_qa'].update(rows)
    assert not inventory(OUT/'problem_board_page_2.bin','problem_qa')
    urls={}
    for kind,items in inv.items():
        for ident in items:
            name=kind+'_'+ident
            if (OUT/(name+'.bin')).exists():continue
            if kind=='notice':url=f'/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId={ident}'
            elif kind=='general_qa':url=f'/competition/main/selectQna.do?bbsId=BBSMSTR_BBBBBBBBBBBB&nttId={ident}'
            else:url=f'/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId={ident}'
            urls[name]=url
    write(OUT/'inventories.json',inv);config('details',urls)
    print('DETAILS',len(urls),'inventories',{k:len(v) for k,v in inv.items()})

def summarize():
    inv=read(OUT/'inventories.json');results={};failed=[]
    clean=lambda v:re.sub(r'data:image/[^;,]+;base64,[A-Za-z0-9+/=\r\n]+','[embedded image omitted]',v)
    for kind,items in inv.items():
        for ident,cells in items.items():
            name=kind+'_'+ident;path=OUT/(name+'.bin');current=fields(path)
            if not current.get('nttCn','').strip():failed.append(name)
            priorpath=OLD/(name+'.html');prior=fields(priorpath) if priorpath.exists() else {}
            same=bool(current) and set(current)==set(prior) and all(normalized(current[k])==normalized(prior[k]) for k in current)
            texts={k:clean(v) for k,v in current.items()}
            write(OUT/(name+'_fields.json'),texts)
            results[name]=dict(listing=cells,sha256=sha(path),fields=list(current),unchanged=same,new=not priorpath.exists())
    current=read(OUT/'problem_tabs.bin')['overviewList'];prior=read(OLD/'problem_tabs.bin')['overviewList'];oldtabs={t['title']:t for t in prior}
    tabs=[dict(title=t['title'],modify_date=t.get('modifyDt'),unchanged=t['title'] in oldtabs and t['content']==oldtabs[t['title']]['content']) for t in current]
    write(OUT/'problem_tab_contents_clean.json',[dict(t,content=clean(t['content'])) for t in current])
    app=OUT/'current_blank_application.bin'
    from scripts.inspect_official_updates_20261013 import hwp_text
    body,_,_=hwp_text(app)
    (OUT/'application_body.txt').write_text(body,encoding='utf8')
    application=dict(bytes=app.stat().st_size,sha256=sha(app),body_extracted=bool(body.strip()),unchanged=sha(app)==sha(OLD/'current_blank_application.hwp'))
    assert application['body_extracted']
    paths=list(OUT.glob('*.bin'))
    previous=set(read(OLD/'summary.json')['detail_comparisons']);missing=sorted(previous-set(results))
    summary=dict(status='public_review_complete' if not failed and not missing else 'partial_unverified',checked_at_utc=datetime.now(timezone.utc).isoformat(),
        detail_comparisons=results,inventories=inv,tabs=tabs,application=application,missing_previous_details=missing,failed=failed,
        responses=len(paths),response_files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in paths},
        source_transport='curl.exe HTTPS public GET; no login or cookies',full_data_zip_downloaded=False,competition_submitted=False,external_messages_sent=False)
    write(OUT/'summary.json',summary)
    print(json.dumps(dict(status=summary['status'],responses=len(paths),details=len(results),changed=[k for k,v in results.items() if not v['unchanged']],tabs=tabs,application=application,missing=missing),ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True,choices=['pages','details','summarize']);globals()[p.parse_args().stage]()