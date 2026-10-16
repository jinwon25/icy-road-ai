"""원 ASOS 조회의 정상 시각 대조군과 겨울 시작 이전 관측을 최소 조회한다."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_method_blending import write
from src.kma_rwis_download import load_auth_key
from src.data_source import sha256_file

OUT = ROOT / 'outputs/private/asos_original_source_controls_20261016_v1'
ENDPOINT = 'https://apihub.kma.go.kr/api/typ01/url/kma_sfctm2.php'


def main():
    if OUT.exists():
        raise FileExistsError('Preserve completed ASOS controls')
    key = load_auth_key(ROOT / 'secret.env')
    OUT.mkdir()
    queries = [('cached_first_hour', '202411010000', '243'),
               ('cached_gap_previous_hour', '202602111200', '243'),
               ('winter_start_previous_hour', '202410312300', '146:243:248')]
    receipts = []
    for name, tm, stations in queries:
        params = dict(tm=tm, stn=stations, help='1')
        record = dict(name=name, checked_at_utc=datetime.now(timezone.utc).isoformat(),
                      endpoint=ENDPOINT, public_parameters=params, authentication_stored=False)
        try:
            response = requests.get(ENDPOINT, params=params | {'authKey': key}, timeout=(10, 45), allow_redirects=False)
        except requests.RequestException as error:
            record.update(status='request_failed', exception_type=type(error).__name__)
        else:
            body = response.text.replace(key, '[REDACTED]')
            path = OUT / (name+'.txt')
            path.write_text(body, encoding='utf-8')
            rows = [line for line in body.splitlines() if line.strip() and not line.lstrip().startswith('#')]
            record.update(status='response_received', http_status=response.status_code,
                          response_sha256=sha256_file(path), response_bytes=path.stat().st_size,
                          noncomment_rows=len(rows))
        receipts.append(record)
        print(record, flush=True)
        time.sleep(1.3)
    write(OUT / 'receipt.json', dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),
          purpose='Official raw weather only; cached nonmissing controls before considering repair',
          road_outcomes_read=False, execution_candidate_changed=False, requests=receipts))


if __name__ == '__main__':
    main()
