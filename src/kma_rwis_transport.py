"""인증을 숨기고 실패 구간을 분할하는 계획 범위 내 관측 전송."""
import hashlib
from pathlib import Path
import time

import pandas as pd
import requests

from src.kma_rwis_download import parse_observations, validate_development_request, RwisResponseError


class ValidatedRoadClient:
    MINIMUM_SPLIT_MINUTES = 15
    def __init__(self, plan, key, cache, session=None):
        self.plan, self.key, self.cache = plan, key, Path(cache)
        self.session = requests.Session() if session is None else session
        self.last_call = 0.

    def fetch(self, station, start, end):
        station, start, end = validate_development_request(self.plan, station, start, end)
        path = self.cache / station / f'{start:%Y%m%d%H%M}_{end:%Y%m%d%H%M}.txt'
        if path.exists():
            body = path.read_text(encoding='utf-8')
            if self.key in body:
                raise RwisResponseError('Authentication material found in cached body; value suppressed')
            frame = parse_observations(body, station, start, end)
            return body, [self._record(path, station, start, end, frame, True)]
        minutes = int((end - start).total_seconds() / 60) + 1
        for attempt in range(3):
            time.sleep(max(0., self.plan['minimum_request_interval_seconds'] - (time.monotonic() - self.last_call)))
            self.last_call = time.monotonic()
            params = {'mode': 1, 'var': station, 'tm1': start.strftime('%Y%m%d%H%M'), 'tm2': end.strftime('%Y%m%d%H%M'), 'disp': 1, 'help': 1, 'authKey': self.key}
            try:
                response = self.session.get(self.plan['endpoint'], params=params, timeout=(10, 20))
            except requests.RequestException as error:
                if minutes > self.MINIMUM_SPLIT_MINUTES:
                    return self._split(station, start, end)
                if attempt == 2:
                    raise RuntimeError(f'API transport failure: {type(error).__name__}; credential URL suppressed') from None
                time.sleep(2 ** attempt)
                continue
            if response.status_code in (500, 502, 503, 504) and minutes > self.MINIMUM_SPLIT_MINUTES:
                return self._split(station, start, end)
            if response.status_code != 200:
                if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f'API HTTP {response.status_code}; credential URL suppressed')
            body = response.text
            if self.key in body:
                raise RwisResponseError('Response echoes authentication material; not saved')
            frame = parse_observations(body, station, start, end)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.txt.tmp')
            temporary.write_text(body, encoding='utf-8')
            temporary.replace(path)
            return body, [self._record(path, station, start, end, frame, False)]
        raise RuntimeError('No validated transport response')

    def _split(self, station, start, end):
        minutes = int((end - start).total_seconds() / 60) + 1
        middle = start + pd.Timedelta(minutes=minutes // 2)
        left, left_records = self.fetch(station, start, middle - pd.Timedelta(minutes=1))
        right, right_records = self.fetch(station, middle, end)
        headers = [line for line in left.splitlines() if line.startswith('#') and line.strip() != '#7777END']
        data = [line for body in (left, right) for line in body.splitlines() if line.strip() and not line.startswith('#')]
        combined = '\n'.join([*headers, '# Combined from validated shorter requests; originals retained in transport cache.', *data, '#7777END']) + '\n'
        parse_observations(combined, station, start, end)
        return combined, left_records + right_records

    def _record(self, path, station, start, end, frame, reused):
        return {'station': station, 'start_kst': start.isoformat(), 'end_kst': end.isoformat(),
                'transport_cache_path': path.relative_to(self.cache).as_posix(),
                'transport_response_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'one_minute_rows': len(frame), 'reused_validated_transport': reused,
                'raw_response_rows': int(frame.attrs.get('raw_response_rows', len(frame))),
                'invalid_timestamp_rows_excluded': int(frame.attrs.get('invalid_timestamp_rows_excluded', 0))}
