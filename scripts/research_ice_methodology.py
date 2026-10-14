"""공식 규정과 결빙 분류·기상 이력의 1차 자료를 익명 조회해 보존한다."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import fitz
import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/private/ice_methodology_references_20261010_v1'
SOURCES = {
    'official_problem': 'https://aida.kisti.re.kr/competition/main/problem/PROB_000000000004604/detail.do',
    'official_notice': 'https://aida.kisti.re.kr/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId=564',
    'official_pledge': 'https://aida.kisti.re.kr/competition/cmm/fms/FileDown.do?atchFileId=FILE_000000000003138&fileSn=0',
    'official_qa633': 'https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=633',
    'official_board': 'https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuBoard.do',
    'sklearn_hgb': 'https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html',
    'sklearn_lag': 'https://scikit-learn.org/1.6/auto_examples/applications/plot_time_series_lagged_features.html',
    'catboost_parameters': 'https://catboost.ai/en/docs/references/training-parameters/common',
    'catboost2018': 'https://papers.neurips.cc/paper_files/paper/2018/file/14491b756b3a51daac41c24863285549-Paper.pdf',
    'road_nowcast2023': 'https://journals.ametsoc.org/view/journals/wefo/38/12/WAF-D-23-0137.1.xml',
    'road_history2026': 'https://www.mdpi.com/2076-3417/16/19/9487',
    'selection_bias2010': 'https://jmlr.org/papers/v11/cawley10a.html',
    'spatial_cv2017': 'https://www.biom.uni-freiburg.de/mitarbeiter/dormann/roberts-et-al-2017-ecography.pdf/at_download/file'
}


def fetch(item):
    name, url = item
    receipt = dict(name=name, requested_url=url, time_utc=datetime.now(timezone.utc).isoformat())
    try:
        response = requests.get(url, timeout=(10, 25), headers={'User-Agent': 'icy-road-ai research reference verification'})
        receipt.update(status=response.status_code, bytes=len(response.content), sha256=hashlib.sha256(response.content).hexdigest(), final_url=response.url)
        pdf = response.content.startswith(b'%PDF-'); html = 'html' in response.headers.get('Content-Type', '')
        path = OUT / (name+('.pdf' if pdf else '.html' if html else '.bin'))
        path.write_bytes(response.content); receipt['file'] = path.name
        if response.status_code == 200 and pdf:
            doc = fitz.open(path); receipt['pages'] = len(doc)
            (OUT / (name+'.txt')).write_text('\n'.join(p.get_text() for p in doc), encoding='utf-8')
            if name == 'catboost2018':
                for page in (0, 3):
                    doc[page].get_pixmap(matrix=fitz.Matrix(1.3, 1.3)).save(OUT / f'catboost_page{page+1}.png')
        elif response.status_code == 200 and html:
            soup = BeautifulSoup(response.content, 'html.parser')
            for node in soup(['script', 'style']):
                node.decompose()
            body = soup.find(id='nttCn')
            text = soup.get_text('\n', strip=True)
            if body is not None:
                text += '\n\nHIDDEN_OFFICIAL_BODY\n'+str(body.get('value', body.get_text()))
            (OUT / (name+'.txt')).write_text(text, encoding='utf-8')
            if name == 'official_board':
                receipt['qa633_rows'] = [row.get_text(' ', strip=True) for row in soup.select('tr') if any('nttId=633' in a.get('href', '') for a in row.select('a'))]
    except requests.RequestException as e:
        receipt['error_type'] = type(e).__name__
    print(name, receipt.get('status'), receipt.get('bytes'), flush=True)
    return receipt


def main():
    if OUT.exists():
        raise FileExistsError('Preserve previous reference receipt')
    OUT.mkdir()
    with ThreadPoolExecutor(max_workers=3) as pool:
        receipts = list(pool.map(fetch, SOURCES.items()))
    (OUT / 'fetch_receipts.json').write_text(json.dumps(receipts, ensure_ascii=False, indent=2), encoding='utf-8')
    folder = ROOT / 'outputs/private/joint_surface_20261009_v1/contexts/honam_baekyang'
    train = pd.read_parquet(folder / 'training_features.parquet'); query = pd.read_parquet(folder / 'query_predictions.parquet')
    description = dict(installed={p: bool(importlib.util.find_spec(p)) for p in ['catboost', 'xgboost', 'fitz']}, training_shape=list(train.shape), training_columns=list(train.columns), query_shape=list(query.shape), query_columns=list(query.columns))
    (OUT / 'development_schema.json').write_text(json.dumps(description, indent=2), encoding='utf-8')
    print(json.dumps(description))


if __name__ == '__main__':
    main()
