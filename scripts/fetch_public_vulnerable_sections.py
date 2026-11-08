"""개인정보 없는 공공데이터포털의 공식 다운로드 절차로 최신 취약구간 CSV를 보존한다."""
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import requests

ROOT=Path(__file__).resolve().parents[1]


def main():
    out=ROOT/'outputs/private/public_vulnerable_sections_20261031_v1'
    out.mkdir(parents=True,exist_ok=False)
    records=[];session=requests.Session();base='https://www.data.go.kr'
    def fetch(name,path,method='GET',values=None):
        response=session.request(method,base+path,timeout=(10,35),
            **({'params':values} if method=='GET' else {'data':values}))
        (out/name).write_bytes(response.content)
        records.append(dict(file=name,url=base+path,method=method,parameters=dict(values) if values is not None else None,
            at_utc=datetime.now(timezone.utc).isoformat(),status=response.status_code,
            bytes=len(response.content),sha256=sha256(response.content).hexdigest()))
        response.raise_for_status()
        return response
    status='incomplete'
    try:
        page=fetch('catalog.html','/data/15102132/fileData.do')
        assert '이용허락범위 제한 없음' in page.text
        match=re.search(r"fn_fileDataDown\('15102132',\s*'([^']+)',\s*'([^']*)',\s*'([^']+)',\s*'([^']+)'\)",page.text)
        assert match,'Official download button is missing'
        detail,attachment,serial,history=match.groups()
        values=dict(publicDataDetailPk=detail,publicDataPk='15102132',atchFileId=attachment,
                    fileDetailSn=serial,publicDataTyCode='PR0051',url='/tcs/dss/selectFileDataDownload.do')
        metadata=fetch('download_metadata.json','/tcs/dss/selectFileDataDownload.do','POST',values).json()
        assert metadata['status'] is True,'Public file metadata unavailable'
        args=dict(atchFileId=metadata['atchFileId'],fileDetailSn=metadata['fileDetailSn'])
        limit=fetch('download_limit.json','/cmm/cmm/check-limit.json','POST',args).json()
        assert limit.get('needCaptcha') is False,'Stop: portal requires manual CAPTCHA'
        info=metadata['dataSetFileDetailInfo']
        args['dataNm']=info['publicDataSj'] if info['publicDataTyDetailCode']=='DATY05' else info['dataNm']
        csv=fetch('vulnerable_sections_20260907.csv','/cmm/cmm/fileDownload.do','GET',args)
        assert len(csv.content)>100 and b'<html' not in csv.content[:1000].lower()
        status='download_complete'
    finally:
        (out/'receipt.json').write_text(json.dumps(dict(status=status,requests=records,
            personal_profile_submitted=False,credentials_used=False,download_limit_respected=True,
            license_evidence='Official catalog: 이용허락범위 제한 없음',
            temporal_use='2026 inventory for retrospective comparison only; not a 2024/2025 training feature'),
            ensure_ascii=False,indent=2),encoding='utf-8')
    print(status,records[-1]['bytes'],flush=True)


if __name__=='__main__':main()
