"""공개 공지·질문·답변·첨부 표시를 이전 스냅샷과 대조한다. 로그인/제출은 하지 않는다."""
import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import review_official_updates_20261013 as public
from scripts.compare_official_answers_20261013 import fields, normalized


def write(path, value):
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def attachments(path):
    soup = BeautifulSoup(path.read_bytes(), 'html.parser')
    result = []
    for link in soup.select('a[href]'):
        href = link['href']
        if 'fn_egov_downFile' in href or 'FileDown.do' in href:
            result.append({'text': link.get_text(' ', strip=True), 'href': href})
    return result


def review_issues(summary):
    """수집 실패·비어 있는 목록·본문 누락을 성공한 최신 확인과 구별한다."""
    issues = list(summary['unavailable'])
    for kind in ('notice', 'problem_qa', 'general_qa'):
        if not summary['inventories'].get(kind):
            issues.append(kind + '_inventory_empty')
    for name in summary['previous_details_not_seen']:
        issues.append(name + '_not_seen')
    if not summary['application'].get('verified'):
        issues.append('application_unverified')
    if len(summary['tabs']) < 2 or any(tab.get('removed') for tab in summary['tabs']):
        issues.append('problem_tabs_incomplete')
    return list(dict.fromkeys(issues))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    old, out = args.previous, args.output
    if out.exists():
        raise FileExistsError('Preserve previous official snapshot; use a new output directory')
    if not (old / 'summary.json').is_file():
        raise FileNotFoundError('Previous completed review required')
    out.mkdir(parents=True)
    public.OUT = out
    checked = datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    receipts, unavailable = [], []

    def fetch(name, path):
        public.fetch(name, urljoin(public.BASE, path), receipts)
        r = receipts[-1]
        r['checked_date_kst'] = checked
        (out / 'fetch_receipts.json').write_text(json.dumps(receipts, ensure_ascii=False, indent=2)+'\n', 'utf-8')
        if r.get('status') != 200:
            unavailable.append(name)
            return None
        return out / r['file']

    paths = {name: fetch(name, path) for name, path in public.SOURCES.items()}
    inventories, pagination = {}, {}
    for kind, first, stem in [('notice', 'notice_list', '/competition/main/notice.do'),
                              ('problem_qa', 'problem_board', '/competition/problem/PROB_000000000004604/detail/commuBoard.do'),
                              ('general_qa', 'general_qna_list', '/competition/main/qna.do')]:
        ids, pages, signatures = {}, [], set()
        for page in range(1, 21):
            path = paths[first] if page == 1 else fetch(f'{first}_page_{page}', f'{stem}?pageIndex={page}')
            if path is None:
                break
            soup = BeautifulSoup(path.read_bytes(), 'html.parser')
            current, all_ids = {}, []
            for row in soup.select('tr'):
                cells = [cell.get_text(' ', strip=True) for cell in row.select('td')]
                for link in row.select('a[href]'):
                    match = re.search(r'fn_select_detail\([\"\x27]?(\d+)', link['href'])
                    if match:
                        identifier = match.group(1)
                        all_ids.append(identifier)
                        if kind == 'problem_qa' or any(c.startswith('2026-') for c in cells):
                            current[identifier] = cells
            signature = tuple(all_ids)
            if signature in signatures:
                unavailable.append(f'{kind}_pagination_repeated_at_{page}')
                break
            signatures.add(signature)
            ids.update(current)
            pages.append({'page': page, 'current_ids': list(current)})
            # 첫 과거연도/빈 페이지까지 확인. 고정글이 반복되면 새 ID 존재 여부로 판단.
            if not current or (page > 1 and not (set(current) - set(seen))):
                break
            seen = set(ids)
            if kind == 'problem_qa' and len(all_ids) < 10:
                break
        else:
            unavailable.append(f'{kind}_pagination_limit')
        inventories[kind] = ids
        pagination[kind] = pages

    comparisons = {}
    for kind, identifiers in inventories.items():
        for identifier, cells in identifiers.items():
            if kind == 'notice':
                url = f'/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId={identifier}'
            elif kind == 'problem_qa':
                url = f'/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId={identifier}'
            else:
                url = f'/competition/main/selectQna.do?bbsId=BBSMSTR_BBBBBBBBBBBB&nttId={identifier}'
            name = kind+'_'+identifier
            path = fetch(name, url)
            if path is None:
                continue
            current = fields(path)
            previous_path = old / (name+'.html')
            prior = fields(previous_path) if previous_path.exists() else {}
            if not current.get('nttCn', '').strip():
                unavailable.append(name+'_body')
            equal = bool(current) and set(current) == set(prior) and all(normalized(current[k]) == normalized(prior[k]) for k in current)
            comparisons[name] = {'listing': cells, 'url': urljoin(public.BASE, url),
                'new_since_previous': not previous_path.exists(), 'normalized_fields_unchanged': equal,
                'answer_present': any(k != 'nttCn' and v.strip() for k, v in current.items()),
                'attachments': attachments(path),
                'attachments_unchanged': attachments(path) == attachments(previous_path) if previous_path.exists() else None}
            clean = lambda v: re.sub(r'data:image/[^;,]+;base64,[A-Za-z0-9+/=\r\n]+', '[embedded image omitted]', v)
            write(out / (name+'_fields_clean.json'), {k: clean(v) for k, v in current.items()})
            if not equal:
                delta = '\n'.join(difflib.unified_diff(json.dumps({k: clean(v) for k, v in prior.items()}, ensure_ascii=False, indent=2).splitlines(),
                    json.dumps({k: clean(v) for k, v in current.items()}, ensure_ascii=False, indent=2).splitlines(), fromfile='previous', tofile='current'))
                (out / (name+'_diff.txt')).write_text(delta, 'utf-8')

    tabs = fetch('problem_tabs', '/competition/main/problem/loadOverview.do?probId=PROB_000000000004604')
    tab_comparisons = []
    if tabs:
        current = json.loads(tabs.read_bytes())['overviewList']
        previous = json.loads((old / 'problem_tabs.bin').read_bytes())['overviewList']
        before = {t['title']: t for t in previous}
        for tab in current:
            tab_comparisons.append({'title': tab['title'], 'modify_date': tab.get('modifyDt'),
                'content_unchanged': tab['title'] in before and tab['content'] == before[tab['title']]['content']})
        write(out / 'problem_tab_contents.json', current)
        for title in set(before) - {t['title'] for t in current}:
            tab_comparisons.append({'title': title, 'removed': True, 'content_unchanged': False})

    app = fetch('current_blank_application', '/competition/cmm/fms/FileDown.do?atchFileId=FILE_000000000003138&fileSn=0')
    application = {'verified': False}
    if app:
        try:
            # 기존 HWP 추출기는 로컬 비공개 도구에 의존하므로 필요할 때만 읽는다.
            from scripts.inspect_official_updates_20261013 import hwp_text
            body, _, _ = hwp_text(app)
            if not body.strip():
                raise ValueError('Blank application body')
            (out / 'current_blank_application_body.txt').write_text(body, 'utf-8')
            previous = old / 'current_blank_application.hwp'
            application = {'verified': True, 'sha256': hashlib.sha256(app.read_bytes()).hexdigest(),
                'bytes': app.stat().st_size, 'unchanged': previous.exists() and app.read_bytes() == previous.read_bytes()}
        except (ValueError, OSError, ImportError) as exc:
            unavailable.append('application_body_'+type(exc).__name__)
    surfaces = {}
    for name in ['evaluate', 'finalsubmit', 'submitAnswer', 'leaderboard']:
        path = fetch('public_'+name, f'/competition/problem/PROB_000000000004604/detail/{name}.do')
        if path:
            soup = BeautifulSoup(path.read_bytes(), 'html.parser')
            for node in soup(['script', 'style']):
                node.decompose()
            surfaces[name] = soup.get_text(' ', strip=True)[-1600:]
    old_summary = json.loads((old / 'summary.json').read_text('utf-8'))
    not_seen = sorted(set(old_summary['detail_comparisons']) - set(comparisons))
    page_attachments = attachments(paths['problem_page']) if paths['problem_page'] else None
    summary = {'status': 'partial_unverified' if unavailable else 'public_review_complete',
        'checked_date_kst': checked, 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'previous': str(old), 'responses': len(receipts), 'inventories': inventories, 'pagination': pagination,
        'detail_comparisons': comparisons, 'previous_details_not_seen': not_seen, 'tabs': tab_comparisons,
        'problem_attachments': page_attachments, 'problem_attachments_unchanged': page_attachments == attachments(old/'problem_page.html') if page_attachments is not None else None,
        'application': application, 'public_surfaces': surfaces, 'unavailable': unavailable,
        'full_data_zip_downloaded': False, 'full_zip_byte_identity_verified': False,
        'account_login': False, 'account_approval_verified': False, 'competition_submitted': False,
        'external_messages_sent': False}
    summary['unavailable'] = review_issues(summary)
    summary['status'] = 'partial_unverified' if summary['unavailable'] else 'public_review_complete'
    write(out / 'summary.json', summary)
    print(json.dumps({'status': summary['status'], 'responses': len(receipts), 'changed_or_new': [k for k, v in comparisons.items() if not v['normalized_fields_unchanged']],
        'tabs': tab_comparisons, 'application': application, 'unavailable': summary['unavailable']}, ensure_ascii=False))
    return 2 if summary['unavailable'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
