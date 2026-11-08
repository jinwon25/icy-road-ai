"""새 원 논문의 코드 목록과 기상청 500m 입력의 한 시간 가용성만 확인한다."""
from pathlib import Path
import hashlib
import json
import sys
import requests
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.kma_rwis_download import load_auth_key


def main():
    out=ROOT/'outputs/private/forcing_source_probe_20261031_v1';out.mkdir(parents=True,exist_ok=False)
    records=[];session=requests.Session()
    public={
        'repository_tree.json':'https://api.github.com/repos/yunam-seo/road-icing-forced-threshold/git/trees/main?recursive=1',
        'grid_catalog.html':'https://apihub.kma.go.kr/apiList.do?seqApi=971',
    }
    for name,url in public.items():
        try:
            r=session.get(url,timeout=45);(out/name).write_bytes(r.content)
            records.append(dict(file=name,url=url,status=r.status_code,bytes=len(r.content),sha256=hashlib.sha256(r.content).hexdigest()))
        except requests.RequestException as error:records.append(dict(file=name,url=url,error=type(error).__name__))
    # 허용 개발 지점 한 곳의 기상 입력만 요청한다. RWIS 정답 API를 호출하지 않는다.
    coords=pd.read_csv(ROOT/'outputs/private/weather_network_review_20261010_v1/metadata_analysis/development_points.csv')
    row=coords.loc[coords.station.eq(23205)].iloc[0]
    key=load_auth_key(ROOT/'secret.env')
    url='https://apihub.kma.go.kr/api/typ01/url/sfc_nc_var.php'
    params=dict(tm1='202411010000',tm2='202411010100',lon=float(row.lon),lat=float(row.lat),
                obs='ta,td,hm,ws_10m,rn_15m',itv=10,help=1)
    try:
        r=session.get(url,params={**params,'authKey':key},timeout=60)
        raw=r.content.replace(key.encode(),b'[REDACTED]')
        (out/'grid_probe.txt').write_bytes(raw)
        records.append(dict(file='grid_probe.txt',endpoint=url,parameters=params,status=r.status_code,
            bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),credential_redacted=True))
    except requests.RequestException as error:
        records.append(dict(endpoint=url,parameters=params,error=type(error).__name__))
    (out/'receipt.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(records,ensure_ascii=False))


if __name__=='__main__':main()
