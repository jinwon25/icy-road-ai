"""현재2026 일반Q&A·공개 평가/제출 경로와 변경된 규정의 기계 판독 기록."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import review_official_updates_20261013 as public
from scripts.compare_official_answers_20261013 import fields, normalized

OUT = ROOT / 'outputs/private/official_updates_20261013_v2'
CONFIG = ROOT / 'config/official_requirements_20261013_v2.json'


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    target = OUT / 'complete_review.json'
    if target.exists() or CONFIG.exists(): raise FileExistsError('Preserve completed public review')
    public.OUT = OUT; receipts = json.loads((OUT / 'fetch_receipts.json').read_text('utf-8'))
    extra = {}
    for name in ['evaluate', 'finalsubmit', 'submitAnswer', 'leaderboard']:
        url = public.BASE+f'/competition/problem/PROB_000000000004604/detail/{name}.do'
        public.fetch('public_'+name, url, receipts)
        path = OUT / ('public_'+name+'.html')
        if path.exists():
            soup = BeautifulSoup(path.read_bytes(), 'html.parser')
            for node in soup(['script', 'style']): node.decompose()
            text = soup.get_text(' ', strip=True)
            extra[name] = dict(final_url=receipts[-1].get('final_url'), text_excerpt=text[-1800:], logged_in=False)
    pages = []; questions = {}
    for index in range(2, 11):
        name = f'general_qna_page_{index}'
        public.fetch(name, public.BASE+f'/competition/main/qna.do?pageIndex={index}', receipts)
        path = OUT / (name+'.html')
        if not path.exists(): break
        soup = BeautifulSoup(path.read_bytes(), 'html.parser'); rows = []
        for tr in soup.select('tr'):
            cells = [n.get_text(' ', strip=True) for n in tr.select('td')]
            a = tr.find('a', href=re.compile(r'fn_select_detail'))
            if cells and a:
                identifier = re.search(r'fn_select_detail\((\d+)\)', a['href']).group(1)
                rows.append(dict(id=identifier, cells=cells))
                if any(c.startswith('2026-') for c in cells): questions[identifier] = cells
        current_index = soup.find('input', attrs={'name': 'pageIndex'})
        pages.append(dict(requested_page=index, returned_page=current_index.get('value') if current_index else None, rows=rows))
        if not any(any(c.startswith('2026-') for c in r['cells']) for r in rows): break
        if current_index and current_index.get('value') != str(index): raise ValueError('Pagination not honored')
    for identifier in questions:
        name = f'general_qa_{identifier}'
        if (OUT / (name+'.html')).exists(): continue
        public.fetch(name, public.BASE+f'/competition/main/selectQna.do?bbsId=BBSMSTR_BBBBBBBBBBBB&nttId={identifier}', receipts)
        value = fields(OUT / (name+'.html'))
        (OUT / (name+'_fields_clean.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        print(name, value.get('reply_nttCn', 'unanswered')[:2500], flush=True)
    current = json.loads((OUT / 'problem_tabs.bin').read_bytes()); old = json.loads((ROOT / 'outputs/private/official_updates_20261013_v1/problem_tabs.bin').read_bytes())
    tabs = [dict(title=x['title'], unchanged=x['content'] == y['content'], sha256=hashlib.sha256(x['content'].encode()).hexdigest()) for x, y in zip(current['overviewList'], old['overviewList'])]
    reply = fields(OUT / 'problem_qa_633.html')['commentNttCn_1']
    soup = BeautifulSoup((OUT / 'problem_qa_633.html').read_bytes(), 'html.parser')
    new_config = json.loads((ROOT / 'config/official_requirements_20261013.json').read_text('utf-8'))
    new_config['snapshot_version'] = 2; new_config['evaluation'].update(qa633_answer_present=True, qa633_answer_date='2026-10-13',
        missed_ice_day_precision='undefined; exclude from precision average', missed_ice_day_recall=0,
        missed_ice_day_f1=0, actual_and_predicted_both_zero='exclude; TN does not enter TP/FP/FN metric denominators',
        false_alarm_only_day_recall='zero denominator; null formula interpretation; not explicitly answered',
        fully_undefined_station_average='not explicitly answered', incomplete_day_policy_status='미확정')
    for key, source in new_config['sources'].items():
        receipt = next(r for r in receipts if r['url'] == source['url'])
        source.update(response_sha256=receipt['sha256'], status=receipt['status'])
    result = dict(checked_at_utc=datetime.now(timezone.utc).isoformat(), checked_date_kst='2026-10-13', tabs=tabs,
        application_bytes_unchanged=(OUT / 'current_application.hwp').read_bytes() == (ROOT / 'outputs/private/official_updates_20261013_v1/current_application.hwp').read_bytes(),
        qa633_reply_sha256=hashlib.sha256(reply.encode()).hexdigest(), qa633_reply_id=soup.find(id='commentNttId_1')['value'],
        qa633_answer_date='2026-10-13', pages=pages, additional_2026_questions=questions, public_surfaces=extra,
        account_status_verified=False, competition_submission_made=False, protected_outcomes_used=False)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    CONFIG.write_text(json.dumps(new_config, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('completed', len(receipts), 'public responses', len(questions), 'older2026 questions', tabs)
    print('public endpoint excerpts', extra)


if __name__ == '__main__': main()
