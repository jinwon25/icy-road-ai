"""오차 범위와 포함 보장의 가정을 구분하는 원문을 보존한다."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import fitz
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/private/temperature_uncertainty_references_20261010_v1'


def main():
    if OUT.exists():
        raise FileExistsError('Preserve uncertainty references')
    OUT.mkdir(); url = 'https://arxiv.org/pdf/2107.07511'
    response = requests.get(url, timeout=(10, 25), headers={'User-Agent': 'icy-road-ai research verification'})
    receipt = dict(url=url, fetched_at_utc=datetime.now(timezone.utc).isoformat(), status=response.status_code, sha256=hashlib.sha256(response.content).hexdigest(), bytes=len(response.content))
    path = OUT / ('conformal_introduction.pdf' if response.content.startswith(b'%PDF-') else 'fetch_failure.bin'); path.write_bytes(response.content)
    if response.status_code == 200 and path.suffix == '.pdf':
        doc = fitz.open(path); receipt['pages'] = len(doc)
        (OUT / 'conformal_introduction.txt').write_text('\n'.join(p.get_text() for p in doc), encoding='utf-8')
        for page in (4, 14):
            doc[page].get_pixmap(matrix=fitz.Matrix(1.2, 1.2)).save(OUT / f'conformal_page{page+1}.png')
    (OUT / 'fetch_receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8'); print(receipt)


if __name__ == '__main__':
    main()
