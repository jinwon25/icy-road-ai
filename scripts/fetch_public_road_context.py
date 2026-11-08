"""공식 공개 암거 좌표·사고 이력을 내려받는다. 인증·프로필 제출이나 대회 정답 조회는 없다."""
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import requests

ROOT=Path(__file__).resolve().parents[1]
SPECIFICATIONS=[('15159523','culvert_coordinates_20260514.zip'),('15145192','accidents_20251231.csv')]


def main():
    out=ROOT/'outputs/private/public_road_context_20261031_v1';out.mkdir(parents=True,exist_ok=False)
    session=requests.Session();records=[];base='https://www.data.go.kr';status='incomplete'
    def fetch(file,path,method='GET',params=None):
        response=session.request(method,base+path,timeout=(10,45),
            **({'params':params} if method=='GET' else {'data':params}))
        if len(response.content)>50*1024*1024:raise ValueError('Unexpectedly large public response')
        (out/file).write_bytes(response.content)
        records.append(dict(file=file,url=base+path,method=method,parameters=dict(params) if params else None,
            status=response.status_code,bytes=len(response.content),sha256=sha256(response.content).hexdigest(),
            at_utc=datetime.now(timezone.utc).isoformat()))
        response.raise_for_status();return response
    try:
        for pk,filename in SPECIFICATIONS:
            page=fetch(pk+'_catalog.html','/data/'+pk+'/fileData.do')
            assert '이용허락범위 제한 없음' in page.text
            pattern=r"fn_fileDataDown\('"+pk+r"',\s*'([^']+)',\s*'([^']*)',\s*'([^']+)',\s*'([^']+)'\)"
            match=re.search(pattern,page.text);assert match,'Public download button unavailable'
            detail,attachment,serial,history=match.groups()
            metadata=fetch(pk+'_metadata.json','/tcs/dss/selectFileDataDownload.do','POST',dict(publicDataPk=pk,
                publicDataDetailPk=detail,atchFileId=attachment,fileDetailSn=serial,publicDataTyCode='PR0051',
                url='/tcs/dss/selectFileDataDownload.do')).json()
            assert metadata['status'] is True
            args=dict(atchFileId=metadata['atchFileId'],fileDetailSn=metadata['fileDetailSn'])
            limit=fetch(pk+'_limit.json','/cmm/cmm/check-limit.json','POST',args).json()
            assert limit.get('needCaptcha') is False,'Stop: public portal requires manual CAPTCHA'
            info=metadata['dataSetFileDetailInfo']
            args['dataNm']=info['publicDataSj'] if info['publicDataTyDetailCode']=='DATY05' else info['dataNm']
            downloaded=fetch(filename,'/cmm/cmm/fileDownload.do','GET',args)
            assert b'<html' not in downloaded.content[:1000].lower() and len(downloaded.content)>100
            if filename.endswith('.zip'):assert downloaded.content.startswith(b'PK')
            print('DOWNLOADED',pk,len(downloaded.content),flush=True)
        status='download_complete'
    finally:
        (out/'receipt.json').write_text(json.dumps(dict(status=status,requests=records,
            personal_profile_submitted=False,credentials_used=False,download_limit_respected=True,
            use='Geometry and consequence context. Not an icing outcome or a historical feature before availability.',
            collector_sha256=sha256(Path(__file__).read_bytes()).hexdigest()),ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
