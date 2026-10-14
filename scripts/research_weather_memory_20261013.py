"""기상 이력·오차 범위 후속 연구의 일차 문헌과 공식 공개 현황을 보존한다."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import fitz
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/private/weather_memory_references_20261013_v1'
SOURCES = {
    'official_notice_index': 'https://aida.kisti.re.kr/competition/main/notice.do',
    'official_submission_notice': 'https://aida.kisti.re.kr/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId=564',
    'official_qa633': 'https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=633',
    'road_lstm_stacking2026': 'https://gmd.copernicus.org/articles/19/9035/2026/gmd-19-9035-2026.pdf',
    'spatial_local_quantile2026': 'https://raw.githubusercontent.com/mlresearch/v306/main/assets/jiang26at/jiang26at.pdf',
    'covariate_shift2019': 'https://arxiv.org/pdf/1904.06019',
    'interval_scoring2007': 'https://sites.stat.washington.edu/raftery/Research/PDF/Gneiting2007jasa.pdf',
    'metro_primary': 'https://journals.ametsoc.org/view/journals/apme/40/11/1520-0450_2001_040_2026_manmfr_2.0.co_2.xml',
    'hgb_official': 'https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html',
    'selection_bias2010': 'https://jmlr.org/papers/volume11/cawley10a/cawley10a.pdf',
}


def fetch(item):
    name, url = item
    receipt = dict(name=name, requested_url=url, checked_at_utc=datetime.now(timezone.utc).isoformat())
    try:
        response = requests.get(url, timeout=(10, 40), headers={'User-Agent': 'icy-road-ai primary reference research'})
        payload = response.content
        receipt.update(status=response.status_code, bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(), final_url=response.url)
        is_pdf = payload.startswith(b'%PDF-')
        path = OUT / (name+('.pdf' if is_pdf else '.html'))
        path.write_bytes(payload); receipt['file'] = path.name
        if response.status_code == 200 and is_pdf:
            with fitz.open(path) as doc:
                text = '\n'.join(p.get_text() for p in doc)
                receipt['pages'] = len(doc)
                if name in ('road_lstm_stacking2026', 'spatial_local_quantile2026', 'interval_scoring2007'):
                    for page in (0, min(3, len(doc)-1)):
                        doc[page].get_pixmap(matrix=fitz.Matrix(1.25, 1.25)).save(OUT / f'{name}_page{page+1}.png')
        else:
            soup = BeautifulSoup(payload, 'html.parser')
            body = soup.find(id='nttCn')
            text = body.get('value', body.get_text()) if body is not None else soup.get_text('\n', strip=True)
            text = re.sub(r'data:image/[^;,]+;base64,[A-Za-z0-9+/=]+', '[embedded image omitted]', text)
            if name == 'official_qa633':
                receipt['answer_texts'] = [n.get_text(' ', strip=True) for n in soup.select('textarea[id^=commentNttCn_]')]
        (OUT / (name+'.txt')).write_text(text, encoding='utf-8')
    except requests.RequestException as e:
        receipt['error_type'] = type(e).__name__
    return receipt


def main():
    if OUT.exists():
        raise FileExistsError('Preserve reference receipts')
    OUT.mkdir()
    with ThreadPoolExecutor(max_workers=3) as pool:
        receipts = list(pool.map(fetch, SOURCES.items()))
    (OUT / 'fetch_receipts.json').write_text(json.dumps(receipts, ensure_ascii=False, indent=2), encoding='utf-8')
    for r in receipts:
        print(r['name'], r.get('status'), r.get('pages'), r.get('answer_texts'), flush=True)


if __name__ == '__main__':
    main()
