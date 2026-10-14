"""차단·404를 보존하고 저자 소속 대학에 있는 공간 검증 원문을 읽는다."""
from datetime import datetime, timezone
import json
from pathlib import Path

import fitz
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/private/method_blending_references_20261010_v1'


def main():
    url = 'https://www.biom.uni-freiburg.de/mitarbeiter/dormann/roberts-et-al-2017-ecography.pdf/at_download/file'
    response = requests.get(url, timeout=(10, 30)); target = OUT / 'spatial_cv2017_university.pdf'
    if target.exists():
        raise FileExistsError('Preserve source')
    target.write_bytes(response.content)
    import hashlib
    receipt = {'requested_url': url, 'status': response.status_code, 'bytes': len(response.content),
               'sha256': hashlib.sha256(response.content).hexdigest(), 'time_utc': datetime.now(timezone.utc).isoformat()}
    if response.status_code == 200 and response.content.startswith(b'%PDF-'):
        pdf = fitz.open(target); receipt['pages'] = len(pdf)
        (OUT / 'spatial_cv2017_university.txt').write_text('\n'.join(p.get_text() for p in pdf), encoding='utf-8')
        pdf[0].get_pixmap(matrix=fitz.Matrix(1.2, 1.2)).save(OUT / 'spatial_cv2017_university_page1.png')
    with (OUT / 'spatial_university_receipt.json').open('x', encoding='utf-8') as f:
        json.dump(receipt, f, indent=2)
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
