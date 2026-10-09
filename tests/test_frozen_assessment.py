import json
import tempfile
import unittest
from pathlib import Path
import pandas as pd
from src.data_source import sha256_file
from src.frozen_assessment import verify_freeze, protected_point_inputs
from src.validation import PROTECTED_STATIONS


class FrozenAssessmentTests(unittest.TestCase):
    def test_changed_file_and_wrong_target_set_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); target = root / 'model.bin'; target.write_bytes(b'fixed')
            out = root / 'outputs/private/frozen_assessment_v1'; out.mkdir(parents=True)
            manifest = {'protected_outcomes_opened_at_freeze': False, 'target_stations': sorted(PROTECTED_STATIONS), 'files': {'model.bin': sha256_file(target)}}
            (out / 'freeze.json').write_text(json.dumps(manifest), encoding='utf-8')
            verify_freeze(root)
            target.write_bytes(b'changed')
            with self.assertRaises(ValueError): verify_freeze(root)

    def test_only_static_metadata_and_development_references(self):
        class Builder:
            def build(self, point, times, forbidden):
                assert point['station'] == 'frozen_target_12410'
                assert forbidden == PROTECTED_STATIONS
                return pd.DataFrame({'time': times}), {'near_source': '12103', 'moisture_source': None}
        point = {'station': '12410', 'route': 'R', 'lat': 35., 'lon': 127., 'elevation_m': 100.}
        frozen = {'target_stations': sorted(PROTECTED_STATIONS)}
        result, mapping = protected_point_inputs(Builder(), point, pd.to_datetime(['2025-01-01']), frozen)
        self.assertEqual(result.station.iloc[0], '12410')
        self.assertEqual(result.elevation_m.iloc[0], 100.)
        with self.assertRaises(ValueError): protected_point_inputs(Builder(), {**point, 'road_temp': -1}, [], frozen)
        with self.assertRaises(ValueError): protected_point_inputs(Builder(), {**point, 'station': '12103'}, [], frozen)

    def test_protected_reference_rejected(self):
        class Builder:
            def build(self, point, times, forbidden):
                return pd.DataFrame(), {'near_source': '23402', 'moisture_source': None}
        point = {'station': '12410', 'route': 'R', 'lat': 35., 'lon': 127., 'elevation_m': 100.}
        with self.assertRaises(ValueError): protected_point_inputs(Builder(), point, [], {'target_stations': sorted(PROTECTED_STATIONS)})


if __name__ == '__main__': unittest.main()
