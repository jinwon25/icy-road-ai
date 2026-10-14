"""목록에서 확인한 게시글·문제 본문·익명 참가양식을 보존한다."""
import json
from pathlib import Path
import re
import sys
from urllib.parse import urljoin
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.review_official_updates_20261013 import OUT, BASE, fetch


def main():
    target = OUT / 'detail_inventory.json'
    if target.exists():
        raise FileExistsError('Preserve detail snapshot')
    receipts = json.loads((OUT / 'fetch_receipts.json').read_text('utf-8')); inventory = json.loads((OUT / 'surface_inventory.json').read_text('utf-8'))
    requests = []
    for row in inventory['notice_list']['rows']:
        if row['cells'][2].startswith('2026'):
            identifier = re.search(r'fn_select_detail\((\d+)\)', row['links'][0]).group(1)
            requests.append((f'notice_{identifier}', f'/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId={identifier}'))
    for surface, prefix, path, bbs in [('problem_board', 'problem_qa', '/competition/problem/PROB_000000000004604/detail/commuDetail.do', 'BBSMSTR_000000000319'),
                                        ('general_qna_list', 'general_qa', '/competition/main/selectQna.do', 'BBSMSTR_BBBBBBBBBBBB')]:
        for row in inventory[surface]['rows']:
            identifier = re.search(r'fn_select_detail\((\d+)\)', row['links'][0]).group(1)
            requests.append((f'{prefix}_{identifier}', f'{path}?bbsId={bbs}&nttId={identifier}'))
    requests.append(('problem_tabs', '/competition/main/problem/loadOverview.do?probId=PROB_000000000004604'))
    page = BeautifulSoup((OUT / 'problem_page.html').read_bytes(), 'html.parser')
    attachments = []
    for anchor in page.select('a[onclick]'):
        match = re.search(r"fn_egov_downFile\('([^']+)','([^']+)','([^']+)'\)", anchor['onclick'])
        if match:
            file_id, number, access = match.groups()
            attachments.append(dict(label=anchor.get_text(' ', strip=True), file_id=file_id, file_number=number, displayed_access=access))
            if '.hwp' in anchor.get_text() and access == 'anonymous':
                requests.append(('current_application', f'/competition/cmm/fms/FileDown.do?atchFileId={file_id}&fileSn={number}'))
    for name, path in requests:
        fetch(name, urljoin(BASE, path), receipts)
    details = {}
    for name, _ in requests:
        path = OUT / (name+'.html')
        if not path.exists():
            continue
        soup = BeautifulSoup(path.read_bytes(), 'html.parser')
        details[name] = dict(hidden=[dict(id=n.get('id'), name=n.get('name'), value=n.get('value')) for n in soup.select('input[type=hidden]') if n.get('id') in ('nttCn', 'answerCn') or 'answer' in (n.get('id') or '').lower()],
                             bodies=[dict(id=n.get('id'), text=n.get('value', n.get_text())) for n in soup.select('input, textarea') if any(t in (n.get('id') or '').lower() for t in ['nttcn', 'answer', 'comment'])])
    target.write_text(json.dumps(dict(attachments=attachments, details=details), ensure_ascii=False, indent=2), encoding='utf-8')
    print('Details fetched', len(requests), 'Attachments', attachments)


if __name__ == '__main__':
    main()
