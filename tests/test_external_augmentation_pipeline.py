"""작은 합성 자료로 중첩 실행 전체의 행 보존과 그룹 제외를 검증한다."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts import evaluate_external_augmentation as runner
from scripts import evaluate_external_temperature as temperature_runner
from scripts import predict_external_reserved as prediction_runner
from scripts import download_kma_external_reserved as reserved_collector
from scripts import evaluate_external_reserved as reserved_evaluator
from scripts.baseline_ice_logistic import FEATURES
from src.external_reserved import verify_reserved_freeze

PROJECT = Path(__file__).resolve().parents[1]
ADDITIONAL = ['air_min_3h', 'humidity_max_3h', 'dewpoint_gap_min_3h', 'rain15_max_3h', 'wet_observations_3h',
              'air_observations_3h', 'asos_rain_mm', 'asos_cloud_tenths', 'asos_solar_mj_m2', 'asos_snow_cm',
              'asos_ground_temp', 'asos_humidity', 'elevation_m', 'air_dewpoint_gap', 'air_asos_gap', 'ground_air_gap']
DONORS = ['12103', '12209', '12210', '12211', '12409', '23202', '23203', '23204', '23403', '33103', '33206', '33409', '33410', '33412']


class AugmentationPipelineTest(unittest.TestCase):
    def test_nested_execution_preserves_gold_rows_and_excludes_held_groups(self):
        with TemporaryDirectory() as folder:
            root = Path(folder);private = root / 'outputs/private'
            for name in ['config', 'src', 'scripts', 'outputs/private/physical_features', 'outputs/private/external_development_features_v1',
                         'outputs/private/external/kma_rwis_development_v1', 'outputs/private/external/kma_rwis_reference',
                         'outputs/private/sensor_availability', 'outputs/private/point_sources']:
                (root / name).mkdir(parents=True, exist_ok=True)
            plan = json.loads((PROJECT / 'config/kma_external_validation_plan.json').read_text(encoding='utf-8'))
            plan['development_end_kst'] = '2024-11-01'
            plan['reserved_validation_end_kst'] = '2025-11-01'
            (root / 'config/kma_external_validation_plan.json').write_text(json.dumps(plan), encoding='utf-8')
            config = json.loads((PROJECT / 'config/external_augmentation_experiment.json').read_text(encoding='utf-8'))
            config['model'].update(max_iter=2, max_leaf_nodes=3, min_samples_leaf=10)
            (root / 'config/external_augmentation_experiment.json').write_text(json.dumps(config), encoding='utf-8')
            shutil.copy2(PROJECT / 'config/external_temperature_experiment.json', root / 'config/external_temperature_experiment.json')
            for name in ['external_augmentation.py', 'physical_features.py', 'surface_state_context_v2.py', 'external_temperature.py']:
                shutil.copy2(PROJECT / 'src' / name, root / 'src' / name)
            for name in ['evaluate_external_augmentation.py', 'evaluate_external_temperature.py']:
                shutil.copy2(PROJECT / 'scripts' / name, root / 'scripts' / name)
            routes = {'12': '서해안', '23': '호남선', '33': '통영-대전중부선'}
            external_groups = {station: group for group, stations in plan['station_groups'].items() for station in stations}
            stations = DONORS + sorted(external_groups)
            metadata = pd.DataFrame([{'station': station, 'kind': 'RWIS', 'route': routes[station[:2]],
                                      'lat': 36. + i*.001, 'lon': 126.8} for i, station in enumerate(stations)])
            metadata.loc[metadata.station.isin(DONORS)].to_csv(private / 'sensor_availability/metadata.csv', index=False)
            catalog = metadata.loc[metadata.station.isin(external_groups), ['station', 'route', 'lat', 'lon']].copy()
            catalog['route'] = catalog.route.replace({'통영-대전중부선': '통영-대전중부'})
            catalog['elevation_m'] = 100.
            catalog.to_csv(private / 'external/kma_rwis_reference/station_catalog.csv', index=False)
            time = pd.date_range('2024-11-01', periods=144, freq='10min')
            frames = []
            for station in stations:
                frame = pd.DataFrame({'station': station, 'route': routes[station[:2]], 'time': time})
                for column in FEATURES + ADDITIONAL:
                    frame[column] = np.sin(np.arange(144)/20.) if column.endswith('temp') else 1.
                frame['ice'] = (np.arange(144) % 30 < 3).astype(float)
                frame['state_raw'] = np.where(frame.ice.eq(1), '04', '01')
                frame['road_temp'] = frame.asos_air_temp - 1.
                frame['neighbor_road_temp'] = -1.
                frame['spatial_group'] = external_groups.get(station, 'competition_' + station)
                frames.append(frame)
            data = pd.concat(frames, ignore_index=True)
            comp = data.loc[data.station.isin(DONORS)]
            external = data.loc[data.station.isin(external_groups)]
            # Match the actual classification cache: it deliberately has no own temperature label.
            comp.drop(columns=['road_temp', 'neighbor_road_temp']).to_parquet(private / 'physical_features/features.parquet', index=False)
            (private / 'physical_features/summary.json').write_text(json.dumps({'additional_features': ADDITIONAL}), encoding='utf-8')
            feature_path = private / 'external_development_features_v1/features.parquet'
            external.to_parquet(feature_path, index=False)
            (feature_path.parent / 'summary.json').write_text(json.dumps({'model_training_permitted': True,
                'reserved_validation_opened': False, 'features_sha256': hashlib.sha256(feature_path.read_bytes()).hexdigest()}), encoding='utf-8')
            (private / 'external/kma_rwis_development_v1/summary.json').write_text(json.dumps({'status': 'development_download_complete', 'reserved_validation_opened': False}), encoding='utf-8')
            thermal = comp[['station', 'route', 'time']].copy()
            for column, value in [('road_temp', -1.), ('temp_min60', -2.), ('temp_trend60', 0.), ('humidity', 90.), ('rain10', 0.)]:
                thermal[column] = value
            thermal.to_parquet(private / 'point_sources/rwis.parquet', index=False)
            with patch.object(runner, 'ROOT', root), patch.object(runner, 'verify_freeze', return_value={'files': list(range(47))}), patch('sys.argv', ['evaluate_external_augmentation.py']), redirect_stdout(io.StringIO()):
                runner.main()
            out = private / 'external_augmentation_nested_v1'
            summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
            self.assertFalse(summary['reserved_validation_opened'])
            self.assertEqual(summary['rows'], 9*144)
            self.assertEqual(summary['slot_micro']['baseline']['n'], 9*144)
            self.assertEqual(summary['slot_micro']['selected']['n'], 9*144)
            predictions = pd.read_parquet(out / 'outer_development_predictions.parquet')
            pd.testing.assert_frame_equal(predictions[['station', 'time', 'ice']].sort_values(['station', 'time']).reset_index(drop=True),
                external[['station', 'time', 'ice']].sort_values(['station', 'time']).reset_index(drop=True), check_dtype=False)
            for group, decision in summary['group_choices'].items():
                self.assertNotIn(group, decision['selection_groups'])
                self.assertFalse(set(plan['station_groups'][group]) & set(decision['training_stations']))
                self.assertFalse({'ice', 'state_raw', 'road_temp'} & set(decision['features']))
            for receipt in out.rglob('fit_manifest.json'):
                info = json.loads(receipt.read_text(encoding='utf-8'))
                self.assertFalse(set(info['training_stations']) & set(info['forbidden_stations']))
                self.assertEqual(info['calibration_stations'], sorted(DONORS))
                self.assertFalse(set(external_groups) & set(info['calibration_stations']))
            with patch.object(temperature_runner, 'ROOT', root), patch.object(temperature_runner, 'verify_freeze', return_value={'files': list(range(47))}), patch('sys.argv', ['evaluate_external_temperature.py']), redirect_stdout(io.StringIO()):
                temperature_runner.main()
            temp_out = private / 'external_temperature_nested_v1'
            temp_summary = json.loads((temp_out / 'summary.json').read_text(encoding='utf-8'))
            self.assertEqual(temp_summary['rows'], 9*144)
            self.assertFalse(temp_summary['reserved_validation_opened'])
            for group, decision in temp_summary['group_choices'].items():
                self.assertNotIn(group, decision['selection_groups'])
                self.assertFalse(set(plan['station_groups'][group]) & set(decision['training_stations']))
            # The point builder has separate source-time tests. Here a static fixture
            # verifies saved real models -> reserved prediction -> sealed receipt wiring.
            coordinates = pd.DataFrame({'station_id': ['100'], 'kind': ['AWS']})
            coordinates.to_csv(private / 'point_sources/weather_coordinates.csv', index=False)
            for name in ['aws', 'asos']:
                pd.DataFrame({'station': ['100'], 'source_time': [time[0]], 'air_temp': [0.]}).to_parquet(private / f'point_sources/{name}.parquet', index=False)

            class StaticPointBuilder:
                def __init__(self, *args):
                    self.aws = {'100': pd.DataFrame()}; self.asos = {'100': pd.DataFrame()}; self.moisture = set(DONORS)

                def build(self, point, times):
                    values = pd.DataFrame({'station': point['station'], 'route': point['route'], 'time': times})
                    for column in FEATURES + ADDITIONAL:
                        values[column] = 1.
                    values['neighbor_road_temp'] = -1.
                    return values, {'near_source': DONORS[0], 'moisture_source': DONORS[0]}

            with patch.object(prediction_runner, 'ROOT', root), patch.object(prediction_runner, 'verify_freeze', return_value={'files': list(range(47))}), patch.object(prediction_runner, 'PointInputBuilder', StaticPointBuilder), patch('sys.argv', ['predict_external_reserved.py']), redirect_stdout(io.StringIO()):
                prediction_runner.main()
            reserved_out = private / 'external_reserved_predictions_v1'
            receipt = verify_reserved_freeze(root, reserved_out)
            self.assertEqual(receipt['rows'], 9*144)
            self.assertFalse(receipt['reserved_outcomes_opened_at_seal'])
            reserved = pd.read_parquet(reserved_out / 'predictions.parquet')
            self.assertFalse({'ice', 'state_raw', 'road_temp'} & set(reserved))
            self.assertFalse((private / 'external/kma_rwis_reserved_v1').exists())

            class SyntheticApiSession:
                def __init__(self): self.calls = []

                def get(self, url, params, timeout):
                    station = params['var']; self.calls.append(station)
                    begin = pd.to_datetime(params['tm1'], format='%Y%m%d%H%M')
                    finish = pd.to_datetime(params['tm2'], format='%Y%m%d%H%M')
                    headers = [f'# {i}. {name} : description' for i, name in enumerate(['TM', 'STN_ID', 'LAT', 'LON', 'HT', 'SFS', 'TR1'], 1)]
                    lines = []
                    for i, stamp in enumerate(pd.date_range(begin, finish, freq='min')):
                        clock = '0' if i == 1 else stamp.strftime('%Y%m%d%H%M')
                        state = '0' if i == 0 else '04' if stamp.minute % 30 == 0 else '01'
                        lines.append(f'{clock},{station},36,126.8,100,{state},-1')
                    return SimpleNamespace(status_code=200, text='\n'.join([*headers, *lines, '#7777END']))

            session = SyntheticApiSession()
            with patch.object(reserved_collector, 'ROOT', root), patch.object(reserved_collector, 'verify_freeze', return_value={'files': list(range(47))}), patch.object(reserved_collector, 'load_auth_key', return_value='synthetic-only-key'), patch('src.kma_rwis_transport.requests.Session', return_value=session), patch('src.kma_rwis_transport.time.sleep'), patch('sys.argv', ['download_kma_external_reserved.py']), redirect_stdout(io.StringIO()):
                reserved_collector.main()
            self.assertEqual(len(session.calls), 18)
            self.assertEqual(set(session.calls), set(external_groups))
            with patch.object(reserved_evaluator, 'ROOT', root), patch.object(reserved_evaluator, 'verify_freeze', return_value={'files': list(range(47))}), patch('sys.argv', ['evaluate_external_reserved.py']), redirect_stdout(io.StringIO()):
                reserved_evaluator.main()
            report = json.loads((private / 'external_reserved_assessment_v1/summary.json').read_text(encoding='utf-8'))
            self.assertEqual(report['prediction_rows'], 9*144)
            self.assertEqual(report['valid_state_rows'], 9*142)
            self.assertEqual(report['invalid_timestamp_rows_excluded'], 18)
            self.assertEqual(report['coverage']['full_valid_state_days'], 0)
            self.assertEqual(report['classification']['baseline']['slot_micro']['n'], report['classification']['selected']['slot_micro']['n'])
            self.assertEqual(len(report['classification_by_group']),4)
            self.assertEqual(len(report['classification_by_station']),9)
            for prefix in ['baseline','selected']:
                expected=report['classification'][prefix]['slot_micro']['n']
                self.assertEqual(sum(row[prefix]['slot_micro']['n'] for row in report['classification_by_group'].values()),expected)
                self.assertEqual(sum(row[prefix]['slot_micro']['n'] for row in report['classification_by_station'].values()),expected)
            with patch.object(reserved_evaluator, 'ROOT', root), patch('sys.argv', ['evaluate_external_reserved.py']), self.assertRaises(FileExistsError):
                reserved_evaluator.main()


if __name__ == '__main__':
    unittest.main()
