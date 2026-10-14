"""현재 공식 숨김 답변·서약과 문헌 적용 범위를 확정한다."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import sys
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_method_blending import read, write
from scripts.compare_official_answers_20261013 import fields, normalized
from scripts.inspect_official_updates_20261013 import hwp_text
from src.data_source import sha256_file as sha

OUT = ROOT / 'outputs/private/report_references_20261014_v1'


def main():
    if (OUT / 'review_receipt.json').exists():
        raise FileExistsError('Preserve reviewed sources')
    comparison = {}
    mapping = {'official_submission':'notice_564', 'official_faq':'notice_639', 'official_ai':'general_qa_618',
               'official_metric':'problem_qa_633', 'official_public_weather':'problem_qa_588'}
    for name, old in mapping.items():
        current = fields(OUT / (name + '.html'))
        prior = fields(ROOT / 'outputs/private/official_updates_20261014_v1' / (old + '.html'))
        comparison[name] = dict(same_fields=set(current) == set(prior),
            same_bodies=all(normalized(v) == normalized(prior.get(k, '')) for k,v in current.items()),
            fields=list(current))
        write(OUT / (name + '_bodies.json'), current)
    reply = fields(OUT / 'official_ai.html')['reply_nttCn']
    assert '원칙적으로 허용되지' in reply and '생성형 AI를 활용' in reply
    (OUT / 'official_ai_reply.txt').write_text(BeautifulSoup(reply, 'html.parser').get_text('\n', strip=True), encoding='utf-8')
    url = 'https://aida.kisti.re.kr/competition/cmm/fms/FileDown.do?atchFileId=FILE_000000000003138&fileSn=0'
    response = requests.get(url, timeout=(10,40))
    response.raise_for_status()
    path = OUT / 'current_blank_application.hwp'
    path.write_bytes(response.content)
    body, _, _ = hwp_text(path)
    (OUT / 'current_blank_application_body.txt').write_text(body, encoding='utf-8')
    old_hash = read(ROOT / 'config/official_requirements_20261014.json')['application']['current_sha256']
    assert sha(path) == old_hash
    old_reference = ROOT / 'outputs/private/method_blending_references_20261010_v1/spatial_cv2017_university.pdf'
    assert old_reference.exists()
    write(OUT / 'review_receipt.json', dict(status='official_rules_and_reference_scope_reviewed',
        checked_at_utc=datetime.now(timezone.utc).isoformat(), official_bodies=comparison,
        blank_application_unchanged=True, blank_application_sha256=sha(path), blank_application_bytes=len(response.content),
        prior_spatial_cv_author_copy=str(old_reference.relative_to(ROOT)), prior_spatial_cv_author_copy_sha256=sha(old_reference),
        acquisition_note='AMS/MDPI 논문은 이번 직접HTTP403. 웹 검색 도구의 출판사 원문 색인에서 초록·해당 부분만 확인. Wiley403은 기존 저자 대학 사본으로 보완.',
        ai_body_extraction_note='첫 수집의 AI usable_response=false는 짧은 질문만 읽은 상태. 숨김 reply_nttCn 답변을 별도 추출해 확인.',
        participant_application_modified=False, account_login=False, external_messages_sent=False))
    print('공식 본문 동일', comparison, '빈 양식', sha(path))


if __name__ == '__main__':
    main()
