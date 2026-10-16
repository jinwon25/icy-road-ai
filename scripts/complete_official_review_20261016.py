"""공식 서약과 기준선·지표·CSV 관련 1차 자료를 추가 확인한다."""
from datetime import datetime,timezone
from pathlib import Path
import json
import sys
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write,preservation
from scripts.inspect_official_updates_20261013 import hwp_text
from src.data_source import sha256_file as sha

OUT=ROOT/'outputs/private/official_updates_20261016_v1'
REF=ROOT/'outputs/private/baseline_references_20261016_v1'
SOURCES={
    'f1_thresholds':'https://arxiv.org/abs/1402.1892',
    'metric_pitfalls':'https://www.nature.com/articles/s41592-023-02150-0',
    'precision_recall':'https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0118432',
    'dummy_classifier':'https://scikit-learn.org/1.6/modules/generated/sklearn.dummy.DummyClassifier.html',
    'csv_parser':'https://pandas.pydata.org/pandas-docs/version/2.2.3/reference/api/pandas.read_csv.html',
}


def main():
    if (OUT/'completion_receipt.json').exists():raise FileExistsError('Preserve official review')
    freeze=preservation(); summary=read(OUT/'summary.json');REF.mkdir(exist_ok=True)
    assert all(v['normalized_fields_unchanged'] for v in summary['detail_comparisons'].values())
    assert all(v['content_unchanged'] for v in summary['tabs'])
    config=read(ROOT/'config/official_requirements_20261014.json')
    url='https://aida.kisti.re.kr/competition/cmm/fms/FileDown.do?atchFileId=FILE_000000000003138&fileSn=0'
    response=requests.get(url,timeout=(10,40));response.raise_for_status()
    application=OUT/'current_blank_application.hwp';application.write_bytes(response.content)
    text,_,_=hwp_text(application);(OUT/'current_blank_application_body.txt').write_text(text,'utf-8')
    assert sha(application)==config['application']['current_sha256']
    refs=[]
    for name,url in SOURCES.items():
        response=requests.get(url,timeout=(10,35),headers={'User-Agent':'icy-road-ai source review'})
        path=REF/(name+'.html');path.write_bytes(response.content)
        soup=BeautifulSoup(response.content,'html.parser')
        for node in soup(['script','style']):node.decompose()
        (REF/(name+'.txt')).write_text(soup.get_text('\n',strip=True),'utf-8')
        refs.append(dict(name=name,url=url,status=response.status_code,bytes=len(response.content),sha256=sha(path),checked_at_utc=datetime.now(timezone.utc).isoformat()))
        print(name,response.status_code,flush=True)
    write(REF/'fetch_receipts.json',refs)
    config.update(checked_date_kst='2026-10-16',snapshot_version=4)
    for source in config['sources'].values():
        matched=[r for r in read(OUT/'fetch_receipts.json') if r['url']==source['url']]
        if matched:source.update(response_sha256=matched[-1]['sha256'],status=matched[-1]['status'])
    config['application']['bytes_unchanged_since_20261014']=True
    config['result_submission']['open_as_of_check']=None
    config['result_submission']['last_public_reply_not_open_date']='2026-10-13'
    config['result_submission']['authenticated_submission_form_verified']=False
    config['result_submission']['status_basis']='2026-10-16 public notice564 and general reply632 unchanged; authenticated form not inspected'
    write(ROOT/'config/official_requirements_20261016.json',config)
    assert preservation()==freeze
    write(OUT/'completion_receipt.json',dict(status='official_public_and_pledge_review_complete',checked_date_kst='2026-10-16',
        checked_at_utc=datetime.now(timezone.utc).isoformat(),responses=len(read(OUT/'fetch_receipts.json'))+1,
        notices=len(summary['notice_ids']),problem_questions=len(summary['problem_question_ids']),general_2026_questions=len(summary['general_2026_question_ids']),
        new_or_changed_details=[],blank_application_sha256=sha(application),blank_application_bytes=application.stat().st_size,
        blank_application_unchanged=True,reference_fetches=refs,result_deadline_date=None,
        participant_account_inspected=False,application_modified=False,external_messages_sent=False,official_submission=False,
        old_frozen_files=freeze[0],reserved_frozen_files=freeze[1]))
    print('Official review and pledge unchanged; sources recorded.')


if __name__=='__main__':main()
