"""기상청 공개 CSV 버튼으로 종관 관측소 이력만 저장한다. API 허가와 별개인 공개 자료다."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_synoptic_icing import write
from src.data_source import sha256_file as sha


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', required=True, type=Path)
    out = p.parse_args().output.resolve()
    if out.exists() or not out.is_relative_to((ROOT / 'outputs/private').resolve()):
        raise ValueError('New private directory required')
    out.mkdir(parents=True); records = []
    origin = 'https://data.kma.go.kr'
    for name, path, method in [('page', '/tmeta/stn/selectStnList.do?pgmNo=123', 'GET'),
                               ('tree', '/cmmn/stnDtaTreeListLayer.do', 'POST')]:
        r = requests.request(method, origin + path, timeout=(10, 40), allow_redirects=False)
        if r.status_code != 200:
            raise ValueError(f'Public metadata {name} status {r.status_code}')
        r.encoding = 'utf-8'; file = out / (name + '.html'); file.write_text(r.text, 'utf-8')
        records.append(dict(url=origin + path, method=method, http_status=r.status_code, sha256=sha(file)))
    page = (out / 'page.html').read_text('utf-8'); tree = (out / 'tree.html').read_text('utf-8')
    assert "id:'SFC01'" in tree and '종관기상관측' in tree
    assert '/tmeta/stn/selectStnListDownload.do' in page
    form = BeautifulSoup(page, 'html.parser').find('form', id='dsForm')
    params = {x.get('name'): x.get('value', '') for x in form.find_all('input') if x.get('name')}
    params.update(fileType='csv', mddlClssCd='SFC01', txtStnNm='종관기상관측')
    url = origin + '/tmeta/stn/selectStnListDownload.do'
    r = requests.post(url, data=params, timeout=(10, 50), allow_redirects=False)
    if r.status_code != 200 or 'text/csv' not in r.headers.get('Content-Type', ''):
        raise ValueError(f'Public CSV unavailable: {r.status_code}')
    file = out / 'asos_history.csv'; file.write_bytes(r.content)
    records.append(dict(url=url, method='POST', parameters=params, http_status=r.status_code, sha256=sha(file)))
    write(out / 'receipt.json', dict(status='public_asos_history_downloaded', at_utc=datetime.now(timezone.utc).isoformat(),
          requests=records, code_sha256=sha(Path(__file__)), authentication=False, road_outcomes_read=False))
    print('Public ASOS history', len(r.content), 'bytes', flush=True)


if __name__ == '__main__':
    main()
