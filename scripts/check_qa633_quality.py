"""새 공식 원문·Q&A 설정·개발 지표·독립 감사·봉인·코드/문서의 완료 확인."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import read, write, preservation
from scripts.compare_official_answers_20261013 import fields

OUT = ROOT / 'outputs/private/qa633_quality_20261013_v1'
REFS = ROOT / 'outputs/private/official_updates_20261013_v2'
STUDY = ROOT / 'outputs/private/qa633_development_20261013_v1'


def main():
    if OUT.exists(): raise FileExistsError('Preserve quality receipt')
    OUT.mkdir(); checks = []
    commands = [[sys.executable, '-X', 'utf8', '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
        [sys.executable, '-X', 'utf8', 'scripts/check_repository.py', '--include-untracked'],
        [sys.executable, '-X', 'utf8', 'scripts/check_markdown.py', '--include-untracked', '--render-dir', str(OUT / 'rendered')]]
    for name, cmd in zip(['tests', 'repository', 'markdown'], commands):
        result = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log = OUT / (name+'.log'); log.write_bytes(result.stdout)
        checks.append(dict(name=name, returncode=result.returncode, log_sha256=sha(log)))
        print(name, result.returncode, result.stdout.decode('utf-8', errors='replace').splitlines()[-4:], flush=True)
        if result.returncode: raise RuntimeError('Preserve failed quality log')
    receipts = read(REFS / 'fetch_receipts.json'); assert len(receipts) == 39 and all(r['status'] == 200 for r in receipts)
    for r in receipts: assert sha(REFS / r['file']) == r['sha256'], r['file']
    changes = read(REFS / 'answer_changes.json'); complete = read(REFS / 'complete_review.json')
    assert changes['comparisons']['problem_qa_633']['answer_present'] and not changes['comparisons']['problem_qa_633']['normalized_fields_equal']
    assert all(changes['comparisons'][f'problem_qa_{i}']['normalized_fields_equal'] for i in [620, 603, 588, 556, 555])
    assert all(changes['comparisons'][f'problem_qa_{i}']['answer_present'] for i in [620, 633, 603, 588, 556, 555])
    assert all(row['cells'][4] == '완료' for row in changes['latest_problem_board_rows'])
    assert all(r['unchanged'] for r in complete['tabs']) and complete['application_bytes_unchanged']
    assert complete['qa633_answer_date'] == '2026-10-13' and complete['qa633_reply_id'] == '648'
    assert all(complete['public_surfaces'][name]['final_url'].endswith('/auth/login') for name in ['evaluate', 'finalsubmit', 'submitAnswer'])
    assert '리더보드 공개 기간이 아닙니다' in complete['public_surfaces']['leaderboard']['text_excerpt']
    inventory = read(REFS / 'surface_inventory.json')
    general_ids = list(complete['additional_2026_questions'])
    for row in inventory['general_qna_list']['rows']:
        import re
        general_ids.append(re.search(r'fn_select_detail\((\d+)\)', row['links'][0]).group(1))
        assert row['cells'][4] == '완료'
    assert len(set(general_ids)) == 16
    for i in general_ids: assert fields(REFS / f'general_qa_{i}.html').get('reply_nttCn', '').strip()
    for r in read(ROOT / 'outputs/private/official_updates_20261013_v1/fetch_receipts.json'):
        assert sha(ROOT / 'outputs/private/official_updates_20261013_v1' / r['file']) == r['sha256']
    config = read(ROOT / 'config/official_requirements_20261013_v2.json'); evaluation = config['evaluation']
    assert evaluation['qa633_answer_present'] and evaluation['missed_ice_day_f1'] == evaluation['missed_ice_day_recall'] == 0
    assert evaluation['incomplete_day_policy_status'] == '미확정' and config['result_submission']['deadline_date'] is None
    for source in config['sources'].values():
        record = next(r for r in receipts if r['url'] == source['url']); assert source['response_sha256'] == record['sha256']
    summary = read(STUDY / 'summary.json'); audit = read(STUDY / 'independent_verification.json')
    assert audit['status'] == 'independent_qa633_metrics_audit_passed' and audit['summary_sha256'] == sha(STUDY / 'summary.json')
    assert audit['audit_source_sha256'] == sha(ROOT / 'scripts/audit_qa633_development.py')
    for rel, digest in summary['files'].items(): assert sha(STUDY / rel) == digest, rel
    for rel, digest in read(STUDY / 'input_signatures.json').items(): assert sha(ROOT / rel) == digest, rel
    assert len(summary['methods']) == 21 and summary['new_model_fits'] == summary['changed_thresholds'] == 0 and summary['previous_f1_unchanged']
    r = summary['reports']['equal_nohistory_pair']['144']; b = summary['reports']['equal_distance_mse_mae300']['144']
    assert r['precision_available_station_mean'] < b['precision_available_station_mean'] and r['f1_available_station_mean'] > b['f1_available_station_mean']
    assert r['recall_all_population_station_mean'] is None and [r[m+'_days'] for m in ['precision', 'recall', 'f1']] == [307, 124, 365]
    freeze = preservation()
    names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT).decode('utf-8').split('\0')
    result = dict(status='official_qa633_followup_complete', checked_at_utc=datetime.now(timezone.utc).isoformat(), checked_date_kst='2026-10-13', checks=checks,
        public_responses_verified=39, current_problem_questions_answered=6, current_general_questions_reviewed=16,
        requirements_sha256=sha(ROOT / 'config/official_requirements_20261013_v2.json'), summary_sha256=sha(STUDY / 'summary.json'), audit_sha256=sha(STUDY / 'independent_verification.json'),
        source_file_hashes={n: sha(ROOT / n) for n in names if n and (ROOT / n).is_file()},
        reference_file_hashes={p.name: sha(p) for p in REFS.iterdir() if p.is_file()},
        new_model_fits=0, changed_thresholds=0, old_frozen_files=freeze[0], reserved_frozen_files=freeze[1],
        assessment_outcomes_used=False, account_login_performed=False, external_message_sent=False, competition_submission_made=False, model_promoted=False)
    write(OUT / 'completion_receipt.json', result); print('완료', len(result['source_file_hashes']), '소스 파일')


if __name__ == '__main__': main()
