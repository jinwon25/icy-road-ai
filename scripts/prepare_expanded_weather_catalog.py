"""새 노면 정답 없이 두 겨울 당시 전국 ASOS 지점 목록을 확보한다."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.kma_rwis_download import load_auth_key
from src.data_source import sha256_file as sha
from scripts.evaluate_synoptic_icing import write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    out = parser.parse_args().output.resolve()
    if out.exists() or not out.is_relative_to((ROOT / 'outputs/private').resolve()):
        raise ValueError('New private directory required')
    out.mkdir(parents=True)
    key = load_auth_key(ROOT / 'secret.env')
    endpoint = 'https://apihub.kma.go.kr/api/typ01/url/stn_inf.php'
    records = []
    for stamp in ['202411010000', '202503010000', '202511010000', '202603010000']:
        params = dict(inf='SFC', stn='0', tm=stamp, help='1')
        record = dict(endpoint=endpoint, parameters=params, at_utc=datetime.now(timezone.utc).isoformat())
        try:
            response = requests.get(endpoint, params=params | dict(authKey=key), timeout=(10, 30), allow_redirects=False)
            body = response.text.replace(key, '[REDACTED]')
            path = out / (stamp + '.txt')
            path.write_text(body, 'utf-8')
            record.update(http_status=response.status_code, bytes=path.stat().st_size, sha256=sha(path))
        except requests.RequestException as exc:
            record['error_type'] = type(exc).__name__
        records.append(record)
        print(stamp, record.get('http_status'), flush=True)
        time.sleep(1.5)
    write(out / 'receipt.json', dict(status='station_metadata_fetched', requests=records,
          official_documentation='https://apihub.kma.go.kr/apiList.do?seqApi=2&seqApiSub=317',
          road_outcomes_read=False, credentials_stored=False, code_sha256=sha(Path(__file__))))


if __name__ == '__main__':
    main()
