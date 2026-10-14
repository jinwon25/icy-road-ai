"""공식 답변 본문만 과거와 대조하고 카운터·사이트 공통 표시 변경을 구별한다."""
import difflib
import hashlib
import json
from pathlib import Path
import re
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/private/official_updates_20261013_v1'


def fields(path):
    soup = BeautifulSoup(path.read_bytes(), 'html.parser'); result = {}
    for node in soup.select('input[id], textarea[id]'):
        name = node['id']
        if name in ['nttCn', 'reply_nttCn'] or re.fullmatch(r'commentNttCn_\d+', name):
            result[name] = str(node.get('value', node.get_text()))
    return result


def normalized(text):
    return re.sub(r'\s+', ' ', text).strip()


def main():
    target = OUT / 'answer_comparison.json'
    if target.exists():
        raise FileExistsError('Preserve answer comparison')
    comparisons = {}
    for identifier in [620, 633, 603, 588, 556, 555]:
        current_path = OUT / f'problem_qa_{identifier}.html'
        old_path = ROOT / ('outputs/private/ice_methodology_references_20261010_v1/official_qa633.html' if identifier == 633 else f'outputs/private/official_review_20261007/qna_{identifier}_recheck_20261009_user_materials.html')
        current, old = fields(current_path), fields(old_path)
        equal = set(current) == set(old) and all(normalized(current[k]) == normalized(old[k]) for k in current)
        for field, text in current.items():
            (OUT / f'problem_qa_{identifier}_{field}_answer.txt').write_text(text, encoding='utf-8')
        comparisons[str(identifier)] = dict(normalized_bodies_equal=equal, fields=list(current), old_path=str(old_path.relative_to(ROOT)),
                                            old_sha256=hashlib.sha256(old_path.read_bytes()).hexdigest(), current_sha256=hashlib.sha256(current_path.read_bytes()).hexdigest(),
                                            official_answer_present=any(k.startswith('commentNttCn_') for k in current))
    current = fields(OUT / 'notice_564.html')['nttCn']
    old = fields(ROOT / 'outputs/private/ice_methodology_references_20261010_v1/official_notice.html')['nttCn']
    delta = '\n'.join(difflib.unified_diff(old.splitlines(), current.splitlines(), fromfile='notice_before_20261010', tofile='notice_20261013', lineterm=''))
    (OUT / 'notice_564_body_diff.txt').write_text(delta, encoding='utf-8')
    (OUT / 'general_replies_clean.txt').write_text('\n\n'.join(f'{path.stem}\n'+fields(path).get('reply_nttCn', 'NO_ANSWER') for path in sorted(OUT.glob('general_qa_*.html'))), encoding='utf-8')
    result = dict(problem_questions=comparisons, notice_564_normalized_equal=normalized(current) == normalized(old), notice_diff='notice_564_body_diff.txt',
                  protected_outcomes_read=False, public_zip_downloaded=False, participant_account_status_verified=False)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8'); print(json.dumps(result, ensure_ascii=False)); print(delta)
    print('EXTERNAL DATA ANSWER:', fields(OUT / 'problem_qa_588.html').get('commentNttCn_3'))


if __name__ == '__main__':
    main()
