"""동일 날짜의 새 공지/Q&A 스냅샷을 이전 완료본과 분리해 보존한다."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import review_official_updates_20261013 as surfaces
from scripts import fetch_official_details_20261013 as details
from scripts.compare_official_answers_20261013 import fields, normalized

OUT = ROOT / 'outputs/private/official_updates_20261013_v2'
OLD = ROOT / 'outputs/private/official_updates_20261013_v1'


def clean(text):
    return re.sub(r'data:image/[^;,]+;base64,[A-Za-z0-9+/=]+', '[embedded image omitted]', text)


def main():
    surfaces.OUT = OUT; details.OUT = OUT
    surfaces.main(); details.main()
    comparisons = {}
    for path in sorted(OUT.glob('*.html')):
        if not path.stem.startswith(('problem_qa_', 'general_qa_', 'notice_')): continue
        current = fields(path); old_path = OLD / path.name
        old = fields(old_path) if old_path.exists() else {}
        if not current: continue
        equal = set(current) == set(old) and all(normalized(current[k]) == normalized(old[k]) for k in current)
        questions, answers = {}, {}
        for key, value in current.items():
            if key == 'nttCn': questions[key] = clean(value)
            else: answers[key] = clean(value)
        (OUT / (path.stem+'_fields_clean.json')).write_text(json.dumps(dict(question=questions, answers=answers), ensure_ascii=False, indent=2), encoding='utf-8')
        delta = '\n'.join(difflib.unified_diff(json.dumps({k: clean(v) for k, v in old.items()}, ensure_ascii=False, indent=2).splitlines(), json.dumps({k: clean(v) for k, v in current.items()}, ensure_ascii=False, indent=2).splitlines(), fromfile='previous', tofile='current', lineterm=''))
        (OUT / (path.stem+'_diff.txt')).write_text(delta, encoding='utf-8')
        comparisons[path.stem] = dict(normalized_fields_equal=equal, fields=list(current), answer_present=bool(answers),
                    current_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), old_sha256=hashlib.sha256(old_path.read_bytes()).hexdigest() if old_path.exists() else None)
        print(path.stem, 'changed', not equal, 'answers', json.dumps(answers, ensure_ascii=False)[:8000], flush=True)
    inventory = json.loads((OUT / 'surface_inventory.json').read_text('utf-8'))
    result = dict(checked_at_utc=datetime.now(timezone.utc).isoformat(), checked_date_kst='2026-10-13', comparisons=comparisons,
        latest_problem_board_rows=inventory['problem_board']['rows'], previous_snapshot_preserved=True, no_account_login=True,
        assessment_outcomes_used=False, full_data_zip_downloaded=False, competition_submission_made=False)
    (OUT / 'answer_changes.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__': main()
