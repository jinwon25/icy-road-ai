"""위치만으로 고른 ASOS의 두 겨울 시간 입력을 받는다. 도로 정답 요청 기능은 없다."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
import requests
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.kma_rwis_download import load_auth_key
from src.data_source import sha256_file as sha
from scripts.evaluate_synoptic_icing import read, write

COLUMNS = 'TM STN WD WS GST_WD GST_WS GST_TM PA PS PT PR TA TD HM PV RN RN_DAY RN_JUN RN_INT SD_HR3 SD_DAY SD_TOT WC WP WW CA_TOT CA_MID CH_MIN CT CT_TOP CT_MID CT_LOW VS SS SI ST_GD TS TE_005 TE_01 TE_02 TE_03 ST_SEA WH BF IR IX'.split()


def parse_weather(body, allowed, start, end):
    if '#7777END' not in body or '# YYMMDDHHMI STN' not in body:
        raise ValueError('Incomplete or unexpected ASOS response')
    rows = [line.split() for line in body.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if not rows or any(len(row) != len(COLUMNS) for row in rows):
        raise ValueError('Unexpected ASOS field count')
    f = pd.DataFrame(rows, columns=COLUMNS)
    f['time'] = pd.to_datetime(f.TM, format='%Y%m%d%H%M', errors='raise')
    if not set(f.STN).issubset(set(map(str, allowed))) or not f.time.between(start, end).all() or f.duplicated(['STN','time']).any():
        raise ValueError('Wrong station, time or duplicate weather rows')
    return f


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--screen', required=True, type=Path); p.add_argument('--output', required=True, type=Path)
    args = p.parse_args(); out = args.output.resolve(); screen = args.screen.resolve()
    if out.exists() or not out.is_relative_to((ROOT / 'outputs/private').resolve()):
        raise ValueError('New private output required')
    receipt = read(screen / 'receipt.json')
    assert receipt['status'] == 'expanded_weather_metadata_screened' and sha(screen / 'screen.csv') == receipt['screen_sha256']
    for name, digest in receipt['source_signatures'].items():
        assert sha(ROOT / name) == digest
    cfg = ROOT / 'config/expanded_icing_validation_20261025.json'; plan = read(cfg)
    ids = receipt['selected_weather_stations']; out.mkdir(parents=True)
    endpoint = 'https://apihub.kma.go.kr/api/typ01/url/kma_sfctm3.php'
    key = load_auth_key(ROOT / 'secret.env'); requests_log = []; frames = []; windows = []
    for lo, hi in plan['winters']:
        start, end = pd.Timestamp(lo), pd.Timestamp(hi)
        windows.append((start - pd.Timedelta(hours=1), start - pd.Timedelta(hours=1)))
        boundaries = pd.date_range(start, end, freq='MS')
        windows += [(a, b - pd.Timedelta(hours=1)) for a,b in zip(boundaries[:-1], boundaries[1:])]
    write(out / 'plan.json', dict(stations=ids, windows=[(str(a),str(b)) for a,b in windows],
          screen_receipt_sha256=sha(screen / 'receipt.json'), code_sha256=sha(Path(__file__)), road_outcomes_read=False))
    for start, end in windows:
        assert end-start < pd.Timedelta(days=31)
        params = dict(tm1=start.strftime('%Y%m%d%H%M'), tm2=end.strftime('%Y%m%d%H%M'), stn=':'.join(map(str,ids)), help='1')
        record = dict(endpoint=endpoint, parameters=params, at_utc=datetime.now(timezone.utc).isoformat())
        try:
            r = requests.get(endpoint, params=params | dict(authKey=key), timeout=(10,45), allow_redirects=False)
            record['http_status'] = r.status_code
            file = out / (params['tm1'] + '.txt'); file.write_text(r.text.replace(key,'[REDACTED]'), 'utf-8')
            record['sha256'] = sha(file)
            if r.status_code == 200:
                f = parse_weather(file.read_text('utf-8'), ids, start, end)
                frames.append(f); record['observation_rows'] = len(f)
        except (requests.RequestException, ValueError) as exc:
            record['error_type'] = type(exc).__name__
        requests_log.append(record); print(params['tm1'], record.get('http_status'), record.get('observation_rows'), flush=True)
        write(out / 'progress.json', dict(requests=requests_log))
        if record.get('http_status') != 200 or 'error_type' in record:
            break
        time.sleep(1.5)
    if frames:
        combined = pd.concat(frames, ignore_index=True).sort_values(['STN','time'])
        assert not combined.duplicated(['STN','time']).any()
        combined.to_parquet(out / 'asos_raw_fields.parquet', index=False, compression='zstd')
        coverage = combined.groupby('STN').agg(rows=('time','size'), first=('time','min'), last=('time','max'))
        coverage.to_csv(out / 'coverage.csv')
    else:
        combined = pd.DataFrame(); coverage = pd.DataFrame()
    expected = sum(int((b-a)/pd.Timedelta(hours=1))+1 for a,b in windows) * len(ids)
    complete = len(combined) == expected and len(requests_log) == len(windows) and all('observation_rows' in r for r in requests_log)
    write(out / 'receipt.json', dict(status='weather_inputs_complete' if complete else 'weather_inputs_incomplete',
        requests=requests_log, expected_rows=expected, received_rows=len(combined), stations=ids,
        raw_fields_not_yet_model_features=True, missing_codes_not_filled=True, road_outcomes_read=False,
        independent_validation_completed=False, screen_receipt_sha256=sha(screen / 'receipt.json'),
        code_sha256=sha(Path(__file__)), files={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    print('complete', complete, 'rows', len(combined), 'expected', expected, flush=True)


if __name__ == '__main__':
    main()
