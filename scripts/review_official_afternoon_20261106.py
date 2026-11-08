"""오후 공개 목록과 최신 세부 답변을 정오 원문과 대조한다."""
import argparse,json
from pathlib import Path
from datetime import datetime,timezone
from scripts import collect_official_curl_20261106 as old
from scripts.compare_official_answers_20261013 import fields,normalized

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/private/official_afternoon_review_20261106'
PREV=ROOT/'outputs/private/official_curl_review_20261106_v1'
old.OUT=OUT

def lists():
    OUT.mkdir()
    old.config('lists',dict(notice_list='/competition/main/notice.do',
        general_qna_list='/competition/main/qna.do',
        problem_board='/competition/problem/PROB_000000000004604/detail/commuBoard.do'))

def details():
    inv={kind:old.inventory(OUT/(name+'.bin'),kind) for kind,name in [('notice','notice_list'),('general_qa','general_qna_list'),('problem_qa','problem_board')]}
    old.write(OUT/'inventories.json',inv)
    urls={}
    # 첫 페이지 현재 답변과 모든 과제 답변: 기존 답변 편집도 확인한다.
    for kind,items in inv.items():
        for ident in items:
            if kind=='notice':url=f'/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId={ident}'
            elif kind=='general_qa':url=f'/competition/main/selectQna.do?bbsId=BBSMSTR_BBBBBBBBBBBB&nttId={ident}'
            else:url=f'/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId={ident}'
            urls[kind+'_'+ident]=url
    old.config('details',urls)
    print('current_listings',{k:len(v) for k,v in inv.items()},'details',len(urls),flush=True)

def summarize():
    inv=old.read(OUT/'inventories.json');new=[];changed=[];all_results={};failed=[]
    for kind,items in inv.items():
        for ident,cells in items.items():
            name=kind+'_'+ident
            current=fields(OUT/(name+'.bin'))
            before=fields(PREV/(name+'.bin')) if (PREV/(name+'.bin')).exists() else {}
            same=bool(current) and set(current)==set(before) and all(normalized(current[k])==normalized(before[k]) for k in current)
            if not current.get('nttCn','').strip():failed.append(name)
            if not before:new.append(name)
            elif not same:changed.append(name)
            old.write(OUT/(name+'_fields.json'),current)
            all_results[name]=dict(listing=cells,unchanged=same,sha256=old.sha(OUT/(name+'.bin')))
    result=dict(status='current_first_page_and_all_task_qa_verified' if not failed else 'partial',
                at_utc=datetime.now(timezone.utc).isoformat(),scope='2026 notice list, latest general Q&A page, all task Q&A; older general pages not reread',
                new_details=new,changed_details=changed,failed=failed,details=all_results,comparison=PREV.relative_to(ROOT).as_posix(),
                competition_submitted=False,external_messages_sent=False)
    old.write(OUT/'summary.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['lists','details','summarize'],required=True)
    globals()[p.parse_args().stage]()
