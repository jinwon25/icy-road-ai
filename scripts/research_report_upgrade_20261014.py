"""보고서 개편의 공식 근거와 일차 문헌을 익명 조회하고 응답을 보존한다."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/private/report_references_20261014_v1'
SOURCES = {
    'official_problem': 'https://aida.kisti.re.kr/competition/main/problem/PROB_000000000004604/detail.do',
    'official_tabs': 'https://aida.kisti.re.kr/competition/main/problem/loadOverview.do?probId=PROB_000000000004604',
    'official_submission': 'https://aida.kisti.re.kr/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId=564',
    'official_faq': 'https://aida.kisti.re.kr/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId=639',
    'official_ai': 'https://aida.kisti.re.kr/competition/main/selectQna.do?bbsId=BBSMSTR_BBBBBBBBBBBB&nttId=618',
    'official_metric': 'https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=633',
    'official_public_weather': 'https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=588',
    'weighted_rst_2026': 'https://journals.ametsoc.org/view/journals/apme/65/6/JAMC-D-25-0189.1.xml',
    'korean_lstm_2026': 'https://www.mdpi.com/2076-3417/16/19/9487',
    'stacking_rst_2026': 'https://gmd.copernicus.org/articles/19/9035/2026/',
    'traffic_rst_2025': 'https://gmd.copernicus.org/articles/18/9945/2025/',
    'roadsurf_2024': 'https://gmd.copernicus.org/articles/17/4837/2024/',
    'anti_icing_fhwa': 'https://www.fhwa.dot.gov/publications/research/safety/95202/002.cfm',
    'selection_bias_2010': 'https://jmlr.org/papers/v11/cawley10a.html',
    'spatial_cv_2017': 'https://doi.org/10.1111/ecog.02881',
    'hgb_1_6': 'https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html',
    'block_bootstrap': 'https://scores.readthedocs.io/en/stable/tutorials/Block_Bootstrapping.html',
    'time_series_bootstrap_2024': 'https://proceedings.mlr.press/v238/palm24a.html',
}


def fetch(item):
    name, url = item
    receipt = dict(name=name, url=url, checked_at_utc=datetime.now(timezone.utc).isoformat())
    try:
        response = requests.get(url, timeout=(10, 40), headers={'User-Agent': 'icy-road-ai reference review'})
        receipt.update(status=response.status_code, final_url=response.url, bytes=len(response.content),
                       sha256=hashlib.sha256(response.content).hexdigest())
        (OUT / (name + '.html')).write_bytes(response.content)
        soup = BeautifulSoup(response.content, 'html.parser')
        body = soup.find(id='nttCn')
        visible = body.get('value', body.get_text()) if body else soup.get_text('\n', strip=True)
        if body:
            visible = BeautifulSoup(visible, 'html.parser').get_text('\n', strip=True)
        answers = [x.get_text(' ', strip=True) for x in soup.select('textarea[id^=commentNttCn_]')]
        visible += '\n' + '\n'.join(answers)
        visible = re.sub(r'data:image/[^;,]+;base64,[A-Za-z0-9+/=]+', '[image]', visible)
        (OUT / (name + '.txt')).write_text(visible, encoding='utf-8')
        receipt['answers'] = answers
        receipt['text_sha256'] = hashlib.sha256(visible.encode()).hexdigest()
        receipt['usable_response'] = response.status_code == 200 and len(visible) > 200
    except requests.RequestException as exc:
        receipt['error_type'] = type(exc).__name__
        receipt['usable_response'] = False
    return receipt


def main():
    OUT.mkdir(exist_ok=False)
    with ThreadPoolExecutor(max_workers=3) as pool:
        receipts = list(pool.map(fetch, SOURCES.items()))
    (OUT / 'fetch_receipts.json').write_text(json.dumps(receipts, ensure_ascii=False, indent=2), encoding='utf-8')
    for r in receipts:
        print(r['name'], r.get('status'), r['usable_response'], flush=True)


if __name__ == '__main__':
    main()
