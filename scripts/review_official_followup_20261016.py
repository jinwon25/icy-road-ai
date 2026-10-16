"""같은 날 후속 공개 검토를 앞선 오전 원문과 구분해 보존한다."""
from datetime import datetime,timezone
from pathlib import Path
import json
import sys
import requests

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import review_official_updates_20261016 as review
from src.data_source import sha256_file as sha


def main():
    review.OUT=ROOT/'outputs/private/official_updates_20261016_v2'
    review.OLD=ROOT/'outputs/private/official_updates_20261016_v1'
    review.main()
    config=json.loads((ROOT/'config/official_requirements_20261016.json').read_text('utf-8'))
    url='https://aida.kisti.re.kr/competition/cmm/fms/FileDown.do?atchFileId=FILE_000000000003138&fileSn=0'
    response=requests.get(url,timeout=(10,40));response.raise_for_status()
    path=review.OUT/'current_blank_application.hwp';path.write_bytes(response.content)
    assert sha(path)==config['application']['current_sha256']
    summary=json.loads((review.OUT/'summary.json').read_text('utf-8'))
    receipt=dict(status='same_day_followup_official_review_complete',checked_at_utc=datetime.now(timezone.utc).isoformat(),
        responses=len(json.loads((review.OUT/'fetch_receipts.json').read_text('utf-8')))+1,
        changed_details=[k for k,v in summary['detail_comparisons'].items() if not v['normalized_fields_unchanged']],
        changed_tabs=[v['title'] for v in summary['tabs'] if not v['content_unchanged']],
        blank_application_sha256=sha(path),blank_application_unchanged=True,participant_account_inspected=False)
    (review.OUT/'completion_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':main()
