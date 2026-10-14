"""공식FAQ 변경의 본문과 그림을 구분하고 현재 규정·사이트 상태를 기록."""
from datetime import datetime,timezone
from pathlib import Path
import base64
import difflib
import hashlib
import re
import sys
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.compare_official_answers_20261013 import fields
from scripts.evaluate_method_blending import read,write
from src.data_source import sha256_file as sha

OUT=ROOT/'outputs/private/official_updates_20261014_v1'
OLD=ROOT/'outputs/private/official_updates_20261013_v2'


def body_text(value):
    soup=BeautifulSoup(value,'html.parser')
    for node in soup(['script','style']):node.decompose()
    return [s.strip() for s in soup.get_text('\n',strip=True).splitlines() if s.strip()]


def main():
    target=OUT/'change_interpretation.json'
    if target.exists():raise FileExistsError('Preserve interpretation')
    current=fields(OUT/'notice_639.html');previous=fields(OLD/'notice_639.html')
    old_lines=body_text(previous['nttCn']);new_lines=body_text(current['nttCn'])
    delta='\n'.join(difflib.unified_diff(old_lines,new_lines,fromfile='20261013',tofile='20261014',lineterm=''))
    (OUT/'faq_visible_text_diff.txt').write_text(delta,encoding='utf-8')
    (OUT/'faq_visible_text.txt').write_text('\n'.join(new_lines),encoding='utf-8')
    images={}
    for label,values in [('previous',previous),('current',current)]:
        images[label]=[]
        for i,match in enumerate(re.finditer(r'data:image/([^;,]+);base64,([A-Za-z0-9+/=]+)',values['nttCn'])):
            raw=base64.b64decode(match.group(2));images[label].append(dict(index=i,mime=match.group(1),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
    config=read(ROOT/'config/official_requirements_20261013_v2.json');summary=read(OUT/'summary.json')
    config['checked_date_kst']='2026-10-14';config['snapshot_version']=3
    for source in config['sources'].values():
        records=[r for r in read(OUT/'fetch_receipts.json') if r['url']==source['url']]
        if records:source['response_sha256']=records[-1]['sha256'];source['status']=records[-1]['status']
    result=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),faq_visible_text_unchanged=old_lines==new_lines,
        faq_visible_text_diff=delta,faq_images=images,changed_public_details=[k for k,v in summary['detail_comparisons'].items() if not v['normalized_fields_unchanged']],
        new_general_qa_653=read(OUT/'general_qa_653_fields_clean.json'),
        problem_questions_all_completed=all('완료' in cells for cells in summary['problem_question_ids'].values()),
        general_2026_questions_all_completed=all('완료' in cells for cells in summary['general_2026_question_ids'].values()),
        current_problem_question_count=len(summary['problem_question_ids']),current_general_question_count=len(summary['general_2026_question_ids']),
        tabs_unchanged=all(x['content_unchanged'] for x in summary['tabs']),
        result_submission_dates_confirmed=False,authenticated_account_status_verified=False)
    write(target,result)
    write(ROOT/'config/official_requirements_20261014.json',config)
    print('FAQ 가시본문 차이\n'+delta[:14000]);print('FAQ 그림 해시',images)
    print('문제Q&A',result['current_problem_question_count'],result['problem_questions_all_completed'],'일반',result['current_general_question_count'],result['general_2026_questions_all_completed'],'문제본문 동일',result['tabs_unchanged'])


if __name__=='__main__':main()
