"""공식 ASOS 원 관측 접근 가능 여부를 인증값을 기록하지 않고 확인한다."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.kma_rwis_download import load_auth_key
from scripts.evaluate_method_blending import write
from src.data_source import sha256_file

OUT = ROOT / 'outputs/private/asos_original_source_probe_20261016_v1'
ENDPOINT = 'https://apihub.kma.go.kr/api/typ01/url/kma_sfctm2.php'


def main():
    if OUT.exists():
        raise FileExistsError('Preserve completed original ASOS probe')
    key = load_auth_key(ROOT / 'secret.env')
    OUT.mkdir()
    params = {'tm': '202602111300', 'stn': '243', 'help': '1'}
    result = dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  endpoint=ENDPOINT, public_parameters=params,
                  purpose='Missing original ASOS air observation only; no road outcomes',
                  authentication_stored=False, redirects_allowed=False)
    try:
        response = requests.get(ENDPOINT, params=params | {'authKey': key},
                                timeout=(10, 45), allow_redirects=False)
    except requests.RequestException as error:
        result.update(status='request_failed', exception_type=type(error).__name__)
    else:
        # Error pages can echo a request. Remove the key before any persistence.
        body = response.text.replace(key, '[REDACTED]')
        path = OUT / 'response.txt'
        path.write_text(body, encoding='utf-8')
        result.update(status='response_received', http_status=response.status_code,
                      response_sha256=sha256_file(path), response_bytes=path.stat().st_size,
                      noncomment_rows=sum(bool(line.strip()) and not line.lstrip().startswith('#')
                                          for line in body.splitlines()))
    write(OUT / 'receipt.json', result)
    print(result, flush=True)


if __name__ == '__main__':
    main()
