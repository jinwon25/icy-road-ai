from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd
import requests

from src.kma_rwis_transport import ValidatedRoadClient
from src.kma_rwis_download import parse_observations

PLAN = json.loads((Path(__file__).resolve().parents[1] / 'config/kma_external_validation_plan.json').read_text(encoding='utf-8'))


class FakeSession:
    def __init__(self): self.calls = []
    def get(self, url, params, timeout):
        self.calls.append({k: v for k, v in params.items() if k != 'authKey'})
        start = pd.to_datetime(params['tm1'], format='%Y%m%d%H%M')
        end = pd.to_datetime(params['tm2'], format='%Y%m%d%H%M')
        if end - start >= pd.Timedelta(minutes=60): return SimpleNamespace(status_code=504)
        columns = ['TM', 'STN_ID', 'LAT', 'LON', 'HT', 'SFS', 'TR1']
        headers = [f'# {i}. {name} : description' for i, name in enumerate(columns, 1)]
        data = [f'{t:%Y%m%d%H%M},12207,36.1289,126.6282,69,04,-0.5' for t in pd.date_range(start, end, freq='min')]
        return SimpleNamespace(status_code=200, text='\n'.join([*headers, *data, '#7777END']))


class TransportTests(unittest.TestCase):
    def test_subhour_timeout_splits_into_valid_quarter_hour_responses(self):
        plan = deepcopy(PLAN); plan['minimum_request_interval_seconds'] = 0

        class SubhourSession(FakeSession):
            def get(self, url, params, timeout):
                start = pd.to_datetime(params['tm1'], format='%Y%m%d%H%M')
                end = pd.to_datetime(params['tm2'], format='%Y%m%d%H%M')
                if end - start >= pd.Timedelta(minutes=15):
                    raise requests.ReadTimeout('synthetic transport timeout')
                return super().get(url, params, timeout)

        with TemporaryDirectory() as folder, patch('src.kma_rwis_transport.time.sleep'):
            body, records = ValidatedRoadClient(plan, 'synthetic-only-key', folder, SubhourSession()).fetch('12207', '2024-11-01', '2024-11-01 00:59')
            frame = parse_observations(body, '12207', '2024-11-01', '2024-11-01 00:59')
            self.assertEqual(len(frame),60);self.assertEqual(len(records),4)
            self.assertTrue(all(record['one_minute_rows']==15 for record in records))

    def test_504_split_preserves_all_minutes_and_reuses_original_responses(self):
        plan = deepcopy(PLAN); plan['minimum_request_interval_seconds'] = 0
        with TemporaryDirectory() as folder, patch('src.kma_rwis_transport.time.sleep'):
            session = FakeSession();client = ValidatedRoadClient(plan, 'synthetic-only-key', folder, session)
            body, records = client.fetch('12207', '2024-11-01', '2024-11-01 01:59')
            frame = parse_observations(body, '12207', '2024-11-01', '2024-11-01 01:59')
            self.assertEqual(len(frame), 120)
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]['end_kst'], '2024-11-01T00:59:00')
            self.assertEqual(records[1]['start_kst'], '2024-11-01T01:00:00')
            self.assertNotIn('synthetic-only-key', json.dumps(records))
            before = len(session.calls)
            body2, records2 = client.fetch('12207', '2024-11-01', '2024-11-01 01:59')
            self.assertEqual(body, body2)
            self.assertEqual(len(session.calls), before + 1)  # only failed parent; successful children are cached
            self.assertTrue(all(r['reused_validated_transport'] for r in records2))
            with self.assertRaises(ValueError): client.fetch('12410', '2024-11-01', '2024-11-01')
            self.assertEqual(len(session.calls), before + 1)


if __name__ == '__main__':
    unittest.main()
