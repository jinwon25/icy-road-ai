"""센서 이상 원인 검토용 공식 공개 원문을 보존한다. 로그인·신청·정답 수집은 하지 않는다."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sys
import time
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    out = p.parse_args().output.resolve()
    if out.exists() or not out.is_relative_to((ROOT / 'outputs/private').resolve()):
        raise ValueError('New private folder required')
    out.mkdir(parents=True)
    old = ROOT / 'outputs/private/releases/20261007/outputs/private/external/kma_rwis_reference'
    manifest = json.loads((old / 'manifest.json').read_text(encoding='utf-8'))
    urls = {r['path']: r['url'] for r in manifest['files']}
    urls.update({
        'road_api.html': manifest['source_page'],
        'deicing_openapi.html': 'https://www.data.go.kr/data/15012002/openapi.do',
        'deicing_openapi.json': 'https://www.data.go.kr/catalog/15012002/openapi.json',
        'deicing_daily.html': 'https://www.data.go.kr/data/15045677/fileData.do',
        'provider_daily.html': 'https://data.ex.co.kr/portal/fdwn/view?type=ETC&num=T5&requestfrom=dataset',
        'lufft_manual.pdf': 'https://www.lufft.com/download/manual-lufft-nirs31-umb-en/',
    })
    records = []
    for name, url in urls.items():
        r = dict(name=name, url=url, at_utc=datetime.now(timezone.utc).isoformat())
        try:
            response = requests.get(url, timeout=(10, 45))
            path = out / name
            path.write_bytes(response.content)
            r.update(status=response.status_code, bytes=len(response.content), sha256=hashlib.sha256(response.content).hexdigest(),
                     content_type=response.headers.get('Content-Type'), is_pdf=response.content.startswith(b'%PDF-'))
            if (old / name).exists():
                r['same_as_previous'] = (old / name).read_bytes() == response.content
        except requests.RequestException as exc:
            r['error_type'] = type(exc).__name__
        records.append(r)
        (out / 'receipt.json').write_text(json.dumps(dict(status='public_source_review', records=records,
            logged_in=False, external_messages_sent=False, road_observations_requested=False), ensure_ascii=False, indent=2), encoding='utf-8')
        print(name, r.get('status'), r.get('bytes'), 'same', r.get('same_as_previous'), flush=True)
        time.sleep(1.3)


if __name__ == '__main__':
    main()
