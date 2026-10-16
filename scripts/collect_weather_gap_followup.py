"""누락 시간의 원 ASOS와 겨울 직전 AWS 접근 상태를 확인한다."""
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

OUT = ROOT / 'outputs/private/weather_gap_source_followup_20261016_v1'
ASOS = 'https://apihub.kma.go.kr/api/typ01/url/kma_sfctm2.php'
AWS = 'https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-aws2_min'


def main():
    if OUT.exists():
        raise FileExistsError('Preserve completed weather source followup')
    key = load_auth_key(ROOT / 'secret.env')
    OUT.mkdir()
    queries = [('second_winter_previous_hour', ASOS, dict(tm='202510312300', stn='146:243:248', help='1')),
               ('jangsu_missing_hour', ASOS, dict(tm='202512191400', stn='248', help='1')),
               ('aws_pre_winter_probe', AWS, dict(tm1='202410312359', tm2='202410312359', stn='733', disp='1', help='1'))]
    receipts = []
    for name, endpoint, params in queries:
        record = dict(name=name, endpoint=endpoint, public_parameters=params,
                      checked_at_utc=datetime.now(timezone.utc).isoformat(), authentication_stored=False)
        try:
            response = requests.get(endpoint, params=params | {'authKey': key}, timeout=(10, 45), allow_redirects=False)
        except requests.RequestException as error:
            record.update(status='request_failed', exception_type=type(error).__name__)
        else:
            body = response.text.replace(key, '[REDACTED]')
            path = OUT / (name+'.txt')
            path.write_text(body, encoding='utf-8')
            record.update(status='response_received', http_status=response.status_code,
                          response_sha256=sha256_file(path), response_bytes=path.stat().st_size,
                          noncomment_rows=sum(bool(line.strip()) and not line.lstrip().startswith('#') for line in body.splitlines()))
        receipts.append(record)
        print(record, flush=True)
        time.sleep(1.3)
    write(OUT / 'receipt.json', dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),
          road_outcomes_read=False, execution_candidate_changed=False, authentication_stored=False, requests=receipts))


if __name__ == '__main__':
    main()
