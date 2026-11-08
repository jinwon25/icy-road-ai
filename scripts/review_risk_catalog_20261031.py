"""공개 결빙취약구간 카탈로그와 제공처 응답을 인증 없이 보존한다."""
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]


def main():
    out=ROOT/'outputs/private/risk_catalog_review_20261031_v1'
    out.mkdir(parents=True,exist_ok=False)
    urls={
        'catalog.html':'https://www.data.go.kr/data/1757/linkedData.do',
        'provider.html':'https://data.ex.co.kr/portal/docu/docuList?datasetId=749',
        'daily_snow_catalog.html':'https://www.data.go.kr/data/15045677/fileData.do',
    }
    records=[]
    for name,url in urls.items():
        record=dict(name=name,url=url,at_utc=datetime.now(timezone.utc).isoformat())
        try:
            response=requests.get(url,timeout=(10,35))
            (out/name).write_bytes(response.content)
            record.update(status=response.status_code,final_url=response.url,bytes=len(response.content),
                          content_type=response.headers.get('content-type'),sha256=sha256(response.content).hexdigest())
        except requests.RequestException as exc:
            record.update(error=type(exc).__name__)
        records.append(record)
        print(name,record.get('status',record.get('error')),flush=True)
    (out/'receipt.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
