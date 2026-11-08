import json
import sys

from scripts import review_official_updates as review


def complete_summary():
    return dict(unavailable=[], inventories={k: {'1': []} for k in ('notice', 'problem_qa', 'general_qa')},
                previous_details_not_seen=[], application={'verified': True}, tabs=[{}, {}])


def test_official_review_requires_nonempty_inventories_and_verified_pledge():
    summary = complete_summary()
    assert review.review_issues(summary) == []
    summary.update(inventories={}, application={'verified': False}, tabs=[])
    assert set(review.review_issues(summary)) == {
        'notice_inventory_empty', 'problem_qa_inventory_empty', 'general_qa_inventory_empty',
        'application_unverified', 'problem_tabs_incomplete'}


def test_official_review_cannot_silently_lose_previously_seen_details():
    summary = complete_summary()
    summary['previous_details_not_seen'] = ['notice_564']
    assert 'notice_564_not_seen' in review.review_issues(summary)


def test_official_review_network_failure_preserves_receipts_and_returns_failure(tmp_path, monkeypatch):
    old, out = tmp_path / 'previous', tmp_path / 'current'
    old.mkdir()
    (old / 'summary.json').write_text(json.dumps({'detail_comparisons': {'notice_564': {}}}), encoding='utf8')

    def fail_fetch(name, url, receipts):
        receipts.append({'name': name, 'url': url, 'error_type': 'ConnectionError'})

    monkeypatch.setattr(review.public, 'fetch', fail_fetch)
    monkeypatch.setattr(sys, 'argv', ['review_official_updates.py', '--previous', str(old), '--output', str(out)])
    assert review.main() == 2
    summary = json.loads((out / 'summary.json').read_text('utf8'))
    assert summary['status'] == 'partial_unverified'
    assert 'notice_564_not_seen' in summary['unavailable']
    assert len(json.loads((out / 'fetch_receipts.json').read_text('utf8'))) == 11
