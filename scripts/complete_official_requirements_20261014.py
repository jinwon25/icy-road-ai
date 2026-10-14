"""공개 참가양식의 바이트를 대조하고 10월14일 FAQ·신청 답변을 새 설정에 반영."""
from datetime import datetime,timezone
from pathlib import Path
import re
import sys
from urllib.parse import urljoin
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import review_official_updates_20261013 as public
from scripts.evaluate_method_blending import read,write
from src.data_source import sha256_file as sha

OUT=ROOT/'outputs/private/official_updates_20261014_v1'


def main():
    target=OUT/'requirements_receipt.json'
    if target.exists():raise FileExistsError('Preserve completed requirement receipt')
    config=read(ROOT/'config/official_requirements_20261014.json');changes=read(OUT/'change_interpretation.json');review=read(OUT/'summary.json')
    receipts=read(OUT/'fetch_receipts.json');soup=BeautifulSoup((OUT/'problem_page.html').read_bytes(),'html.parser')
    found=[]
    for anchor in soup.select('a[onclick]'):
        m=re.search(r"fn_egov_downFile\('([^']+)','([^']+)','([^']+)'\)",anchor['onclick'])
        if m and '.hwp' in anchor.get_text().lower() and m.group(3)=='anonymous':found.append(m)
    assert len(found)==1
    url=urljoin(public.BASE,f'/competition/cmm/fms/FileDown.do?atchFileId={found[0].group(1)}&fileSn={found[0].group(2)}')
    public.OUT=OUT;public.fetch('current_application',url,receipts);receipts[-1]['checked_date_kst']='2026-10-14'
    assert receipts[-1]['status']==200 and (OUT/'current_application.hwp').exists()
    (OUT/'fetch_receipts.json').write_text(__import__('json').dumps(receipts,ensure_ascii=False,indent=2),encoding='utf-8')
    old=ROOT/'outputs/private/official_updates_20261013_v2/current_application.hwp'
    current=OUT/'current_application.hwp';same=sha(old)==sha(current)
    config['application'].update(handwriting_font_signature_rejected=True,multiple_project_applications_allowed=True,
        multiple_awards_allowed=False,current_bytes=current.stat().st_size,current_sha256=sha(current),bytes_unchanged_since_20261013=same,
        submitted_application_modified=False,participant_account_approval_verified=False)
    config['sources']['general_qa_653']=dict(url=next(r['url'] for r in receipts if r['name']=='general_qa_653'),
        response_sha256=next(r['sha256'] for r in receipts if r['name']=='general_qa_653'),status=200)
    config['sources']['current_application']['response_sha256']=sha(current)
    config['official_review']=dict(checked_date_kst='2026-10-14',problem_question_count=6,general_2026_question_count=17,
        all_current_questions_answered=True,faq_visible_text_changed=True,faq_embedded_images_unchanged=changes['faq_images']['previous']==changes['faq_images']['current'],
        problem_data_tab_contents_unchanged=changes['tabs_unchanged'],full_zip_redownloaded=False)
    (ROOT/'config/official_requirements_20261014.json').write_text(__import__('json').dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    write(target,dict(status='official_requirements_20261014_completed',checked_at_utc=datetime.now(timezone.utc).isoformat(),
        public_responses=len(receipts),application_bytes=current.stat().st_size,application_unchanged=same,
        config_sha256=sha(ROOT/'config/official_requirements_20261014.json'),question_status_verified=True,
        application_or_registration_changed=False,authenticated_submission_form_verified=False,competition_submitted=False))
    print(read(target))


if __name__=='__main__':main()
