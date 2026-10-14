"""블렌딩의 1차 문헌과 공식 규정을 익명 GET으로 보존한다."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import fitz
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/private/method_blending_references_20261010_v1'
SOURCES = {
    'official_problem': 'https://aida.kisti.re.kr/competition/main/problem/PROB_000000000004604/detail.do',
    'official_notice': 'https://aida.kisti.re.kr/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId=564',
    'official_pledge': 'https://aida.kisti.re.kr/competition/cmm/fms/FileDown.do?atchFileId=FILE_000000000003138&fileSn=0',
    'official_qa633': 'https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=633',
    'official_board': 'https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuBoard.do',
    'breiman1996': 'https://statistics.berkeley.edu/sites/default/files/tech-reports/367.pdf',
    'superlearner2007': 'https://biostats.bepress.com/ucbbiostat/paper222/',
    'superlearner2010': 'https://biostats.bepress.com/ucbbiostat/paper266/',
    'selection_bias2010': 'https://jmlr.org/papers/v11/cawley10a.html',
    'combination_review2023': 'https://arxiv.org/pdf/2205.04216',
    'sklearn_stacking': 'https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.StackingRegressor.html',
    'sklearn_voting': 'https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.VotingClassifier.html',
    'spatial_cv2017': 'https://doi.org/10.1111/ecog.02881',
}


def main():
    if OUT.exists():
        raise FileExistsError('Preserve original fetch receipt')
    OUT.mkdir(); receipts = []
    for name, url in SOURCES.items():
        r = {'name': name, 'requested_url': url, 'time_utc': datetime.now(timezone.utc).isoformat()}
        try:
            response = requests.get(url, timeout=(10, 30), headers={'User-Agent': 'icy-road-ai research reference verification'})
            r.update(status=response.status_code, bytes=len(response.content), content_type=response.headers.get('Content-Type', ''),
                     sha256=hashlib.sha256(response.content).hexdigest(), final_url=response.url)
            is_pdf = response.content.startswith(b'%PDF-'); ext = '.pdf' if is_pdf else '.html' if 'html' in r['content_type'] else '.bin'
            path = OUT / (name+ext); path.write_bytes(response.content); r['file'] = path.name
            if response.status_code == 200 and is_pdf:
                pdf = fitz.open(path); text = '\n'.join(p.get_text() for p in pdf)
                (OUT / (name+'.txt')).write_text(text, encoding='utf-8'); r['pages'] = len(pdf)
                if name == 'breiman1996':
                    for page in [0, 2, 3]:
                        pdf[page].get_pixmap(matrix=fitz.Matrix(1.4, 1.4)).save(OUT / f'breiman_page{page+1}.png')
            elif response.status_code == 200 and 'html' in r['content_type']:
                soup = BeautifulSoup(response.content, 'html.parser')
                for node in soup(['script', 'style']):
                    node.decompose()
                text = soup.get_text('\n', strip=True)
                (OUT / (name+'.txt')).write_text(text, encoding='utf-8')
                r['text_sha256'] = hashlib.sha256(text.encode()).hexdigest()
                if name == 'official_board':
                    r['qa633_line_matches'] = [s for s in text.splitlines() if '답변' in s or '633' in s]
        except requests.RequestException as e:
            # 인증 없는 요청이며 오류에는 요청 종류만 기록한다.
            r['error_type'] = type(e).__name__
        receipts.append(r)
        print(name, r.get('status'), r.get('bytes'), flush=True)
    (OUT / 'fetch_receipts.json').write_text(json.dumps(receipts, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
