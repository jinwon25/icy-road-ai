"""공개 제설 파일 목록과 기상 입력 접근만 확인한다. 새 노면 정답은 요청하지 않는다."""
import argparse,json,time,hashlib,re
from datetime import datetime,timezone
from pathlib import Path
import sys
import requests
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.kma_rwis_download import load_auth_key


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve()
    if out.exists() or not out.is_relative_to((ROOT/'outputs/private').resolve()):raise ValueError('New private output required')
    out.mkdir(parents=True);records=[];key=load_auth_key(ROOT/'secret.env')
    def fetch(name,url,params,method='GET',auth=False):
        r=dict(name=name,endpoint=url,public_parameters=params,at_utc=datetime.now(timezone.utc).isoformat())
        try:
            kwargs={'params' if method=='GET' else 'data':params|({'authKey':key} if auth else {})}
            response=requests.request(method,url,**kwargs,timeout=(10,25),allow_redirects=False)
            body=response.text.replace(key,'[REDACTED]');file=out/(name+'.txt');file.write_text(body,'utf-8')
            r.update(http_status=response.status_code,bytes=file.stat().st_size,sha256=hashlib.sha256(file.read_bytes()).hexdigest())
            result=response.json() if response.status_code==200 and not auth else None
            if auth:
                r['observation_rows']=sum(bool(re.match(r'^\d{12}\s+\d+\s',x.strip())) for x in body.splitlines()) if response.status_code==200 else 0
        except (requests.RequestException,ValueError) as exc:r['error_type']=type(exc).__name__;result=None
        records.append(r);print(name,r.get('http_status'),r.get('observation_rows'),flush=True)
        time.sleep(1.3);return result
    metadata={}
    for num in ['T5','T7']:
        terms=fetch(num+'_terms','https://data.ex.co.kr/portal/fdwn/getSupplyTerm',dict(type='ETC',num=num,collectCycle='07'),'POST')
        metadata[num]=dict(terms=terms)
        if not isinstance(terms,dict) or not terms.get('List'):continue
        cycle=terms['List'][0]['commDtCdId'];params=dict(collectType='ETC',dataType=num,collectCycle='07',supplyCycle=cycle)
        years=fetch(num+'_years','https://data.ex.co.kr/portal/fdwn/collectYearList',params,'POST');metadata[num]['years']=years
        if not isinstance(years,dict):continue
        for year in [str(y) for y in years.get('List',[]) if str(y) in ['2024','2025','2026']]:
            query=params|dict(dataSupplyDate='',dataSupplyYear='',dataSupplyMonth='',dataSupplyYearQ='',dataSupplyQuater='',dataSupplyYearY=year)
            details=fetch(num+'_'+year,'https://data.ex.co.kr/portal/fdwn/search',query,'POST');metadata[num][year]=details
    fetch('asos_input_probe','https://apihub.kma.go.kr/api/typ01/url/kma_sfctm2.php',dict(tm='202501150000',stn='108',help='1'),auth=True)
    fetch('aws_input_probe','https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-aws2_min',dict(tm1='202501150000',tm2='202501150000',stn='733',disp='1',help='1'),auth=True)
    receipt=dict(status='acquisition_metadata_probed',requests=records,provider_metadata=metadata,road_outcomes_read=False,
        credentials_stored=False,profile_submitted=False,files_downloaded=False,external_messages_sent=False)
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf-8')
    print('provider years', {n:v.get('years') for n,v in metadata.items()},flush=True)


if __name__=='__main__':main()
