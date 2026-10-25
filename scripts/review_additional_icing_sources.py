"""공개 제설 이력의 실제 제공 페이지 접근 결과를 원문·해시와 함께 보존한다."""
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup

SOURCES={
    'snow_daily_catalog':'https://www.data.go.kr/data/15045677/fileData.do',
    'snow_daily_provider':'https://data.ex.co.kr/portal/fdwn/view?type=ETC&num=T5&requestfrom=dataset',
    'snow_usage_catalog':'https://www.data.go.kr/data/15045675/fileData.do',
    'snow_usage_provider':'https://data.ex.co.kr/portal/fdwn/view?type=ETC&num=T7&requestfrom=dataset',
    'rscd_author_license':'https://thu-rsxd.com/dxhdiefb/',
    'rscd_mirror_card':'https://huggingface.co/datasets/rezzzq/RSCD-1million/raw/main/README.md'}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve();root=Path(__file__).resolve().parents[1]
    if out.exists() or not out.is_relative_to((root/'outputs/private').resolve()):raise ValueError('New private receipt path required')
    out.mkdir(parents=True);receipts=[]
    for name,url in SOURCES.items():
        record=dict(name=name,url=url,checked_at_utc=datetime.now(timezone.utc).isoformat())
        try:
            response=requests.get(url,timeout=(10,20));content=response.content
            (out/(name+'.body')).write_bytes(content)
            soup=BeautifulSoup(content,'html.parser')
            record.update(http_status=response.status_code,bytes=len(content),sha256=hashlib.sha256(content).hexdigest(),
                final_url=response.url,title=soup.title.get_text(' ',strip=True) if soup.title else None,
                links=[dict(text=a.get_text(' ',strip=True)[:100],href=a.get('href')) for a in soup.find_all('a',href=True)
                       if any(s in (a.get('href','')+' '+a.get_text()).lower() for s in ['download','downfile','.csv','.zip','다운로드','licen'])])
        except requests.RequestException as exc:record.update(http_status=None,error_type=type(exc).__name__)
        receipts.append(record);print(name,record['http_status'],record.get('bytes'),flush=True)
    (out/'receipt.json').write_text(json.dumps(dict(status='public_source_access_review_complete',responses=receipts,
        credentials_used=False,external_messages_sent=False,competition_data_uploaded=False),ensure_ascii=False,indent=2)+'\n','utf-8')

if __name__=='__main__':main()
