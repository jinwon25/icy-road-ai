"""입력 캐시의 정답 혼입·시각 오류·원천 변경을 거부한다."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from src.external_development_inputs import CACHE_RELATIVE, load_cached_inputs


class DevelopmentInputCacheTest(unittest.TestCase):
    def make_cache(self, folder, label=False):
        root = Path(folder)
        (root / 'config').mkdir()
        plan = {'development_start_kst': '2024-11-01', 'development_end_kst': '2024-11-01',
                'station_groups': {'a': ['12207', '12408'], 'b': ['23205', '23404'],
                                   'c': ['33205', '33408'], 'd': ['33207', '33413', '33414']}}
        (root / 'config/kma_external_validation_plan.json').write_text(json.dumps(plan), encoding='utf-8')
        cache = root / CACHE_RELATIVE
        cache.mkdir(parents=True)
        times = pd.date_range('2024-11-01', periods=144, freq='10min')
        frame = pd.DataFrame({'station': '12207', 'time': times, 'aws_air_temp': range(144)})
        if label:
            frame['road_temp'] = 0.
        path = cache / '12207.parquet'
        frame.to_parquet(path, index=False)
        records = {station: {} for group in plan['station_groups'].values() for station in group}
        records['12207'] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                             'rows': 144, 'columns': frame.columns.tolist(), 'references': {'near_source': '12103'}}
        manifest = {'status': 'development_inputs_complete_without_target_observations',
                    'signature': {'source': 'fixed'}, 'records': records,
                    'target_observations_used': False, 'reserved_outcomes_used': False}
        (cache / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        return root, times

    def test_selects_exact_sparse_observed_keys_without_filling_labels(self):
        with TemporaryDirectory() as folder:
            root, times = self.make_cache(folder)
            selected, references = load_cached_inputs(root, '12207', times[[0, 5, 143]], {'source': 'fixed'})
            self.assertEqual(selected.aws_air_temp.tolist(), [0, 5, 143])
            self.assertEqual(references['near_source'], '12103')
            self.assertFalse({'ice', 'state_raw', 'road_temp'} & set(selected))

    def test_rejects_target_temperature_even_when_file_hash_matches(self):
        with TemporaryDirectory() as folder:
            root, times = self.make_cache(folder, label=True)
            with self.assertRaisesRegex(ValueError, 'target observations'):
                load_cached_inputs(root, '12207', times, {'source': 'fixed'})

    def test_rejects_changed_sources_corrupt_file_and_invalid_requested_keys(self):
        with TemporaryDirectory() as folder:
            root, times = self.make_cache(folder)
            with self.assertRaisesRegex(ValueError, 'sources changed'):
                load_cached_inputs(root, '12207', times, {'source': 'changed'})
            for requested in [times[[0, 0]], pd.DatetimeIndex(['2024-11-01 00:05']),
                              pd.DatetimeIndex(['2024-11-02 00:00'])]:
                with self.assertRaisesRegex(ValueError, 'outside the fixed input grid'):
                    load_cached_inputs(root, '12207', requested, {'source': 'fixed'})
            path = root / CACHE_RELATIVE / '12207.parquet'
            path.write_bytes(path.read_bytes() + b'changed')
            with self.assertRaisesRegex(ValueError, 'file changed'):
                load_cached_inputs(root, '12207', times, {'source': 'fixed'})


if __name__ == '__main__':
    unittest.main()
