"""공식 공지·문제·Q&A의 최신 공개 응답을 기존 원문과 구분해 보존한다."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/private/official_updates_20261013_v1'
BASE = 'https://aida.kisti.re.kr'
SOURCES = {
    'problem_page': '/competition/main/problem/PROB_000000000004604/detail.do',
    'problem_board': '/competition/problem/PROB_000000000004604/detail/commuBoard.do',
    'notice_list': '/competition/main/notice.do',
    'general_qna_list': '/competition/main/qna.do',
    'overview': '/competition/main/overview.do',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fetch(name, url, receipts):
    receipt = dict(name=name, url=url, checked_at_utc=datetime.now(timezone.utc).isoformat(), checked_date_kst='2026-10-13')
    try:
        response = requests.get(url, timeout=(10, 30), headers={'User-Agent': 'icy-road-ai official reference review'})
        receipt.update(status=response.status_code, bytes=len(response.content), sha256=digest(response.content), final_url=response.url)
        path = OUT / (name+('.hwp' if response.content.startswith(bytes.fromhex('d0cf11e0a1b11ae1')) else '.html' if 'html' in response.headers.get('Content-Type', '') else '.bin'))
        path.write_bytes(response.content); receipt['file'] = path.name
        if response.status_code == 200 and path.suffix == '.html':
            soup = BeautifulSoup(response.content, 'html.parser')
            hidden = soup.find(id='nttCn')
            body = str(hidden.get('value', hidden.get_text())) if hidden is not None else None
            if body is not None:
                (OUT / (name+'_body.md')).write_text(body, encoding='utf-8'); receipt['body_sha256'] = digest(body.encode())
            for node in soup(['script', 'style']):
                node.decompose()
            text = soup.get_text('\n', strip=True)
            (OUT / (name+'.txt')).write_text(text, encoding='utf-8')
            receipt['normalized_text_sha256'] = digest(re.sub(r'\s+', ' ', text).encode())
    except requests.RequestException as e:
        receipt['error_type'] = type(e).__name__
    receipts.append(receipt)
    (OUT / 'fetch_receipts.json').write_text(json.dumps(receipts, ensure_ascii=False, indent=2), encoding='utf-8')
    print(name, receipt.get('status'), receipt.get('bytes'), flush=True)


def main():
    if OUT.exists():
        raise FileExistsError('Preserve previous official snapshot')
    OUT.mkdir(parents=True); receipts = []
    for name, path in SOURCES.items():
        fetch(name, urljoin(BASE, path), receipts)
    inventory = {}
    for name in SOURCES:
        path = OUT / (name+'.html')
        if not path.exists():
            continue
        soup = BeautifulSoup(path.read_bytes(), 'html.parser')
        rows = []
        for row in soup.select('tr'):
            cells = [cell.get_text(' ', strip=True) for cell in row.select('td')]
            links = [a.get('href', '') for a in row.select('a[href]')]
            if cells:
                rows.append(dict(cells=cells, links=links))
        scripts = '\n'.join(node.get_text() for node in soup.select('script'))
        inventory[name] = dict(rows=rows, links=[dict(text=a.get_text(' ', strip=True), href=a.get('href')) for a in soup.select('a[href]')],
                               endpoints=sorted(set(re.findall(r'["\'](/competition/[^"\']+)["\']', scripts))),
                               hidden_inputs=[dict(name=n.get('name'), id=n.get('id'), value=n.get('value')) for n in soup.select('input[type=hidden]')])
    (OUT / 'surface_inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({name: {'rows': value['rows'][:12], 'endpoints': value['endpoints']} for name, value in inventory.items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
