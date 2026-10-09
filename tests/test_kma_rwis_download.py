import json
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch
import pandas as pd

from src.kma_rwis_download import parse_observations, exact_ten_minute_grid, daily_requests, validate_development_request, load_auth_key, RwisResponseError

PLAN = json.loads((Path(__file__).resolve().parents[1] / 'config/kma_external_validation_plan.json').read_text(encoding='utf-8'))
COLUMNS = ['TM', 'STN_ID', 'LAT', 'LON', 'HT', 'SFS', 'TR1']


def response(rows):
    return '\n'.join([*(f'# {i}. {name} : description' for i, name in enumerate(COLUMNS, 1)), *rows, '#7777END'])


class RwisDownloadTests(unittest.TestCase):
    def test_missing_time_rows_are_excluded_without_reconstructing_labels(self):
        body = response(['202411010000,12207,36.1289,126.6282,69,01,0.5',
                         '0,12207,0,0,0,04,-999',
                         '-999,12207,0,0,0,04,-999',
                         '202411010020,12207,36.1289,126.6282,69,13,-0.5'])
        frame = parse_observations(body, '12207', '2024-11-01', '2024-11-01 23:59')
        self.assertEqual(frame.time.tolist(), [pd.Timestamp('2024-11-01'), pd.Timestamp('2024-11-01 00:20')])
        self.assertEqual(frame.ice.tolist(), [0., 0.])
        self.assertEqual(frame.attrs['invalid_timestamp_rows_excluded'], 2)
        self.assertEqual(frame.attrs['raw_response_rows'], 4)
        self.assertEqual(frame.attrs['excluded_timestamp_token_counts'], {'0': 1, '-999': 1})
        with self.assertRaises(RwisResponseError): parse_observations(body.replace('202411010020', '202413010020'), '12207', '2024-11-01', '2024-11-01 23:59')

    def test_quoted_csv_timestamp_padding_preserves_original_field(self):
        body = response(['" 202411010000"," 12207",36.1289,126.6282,69," 04",-0.5'])
        frame = parse_observations(body, '12207', '2024-11-01', '2024-11-01 23:59')
        self.assertEqual(frame.time.iloc[0], pd.Timestamp('2024-11-01'))
        self.assertEqual(frame.TM.iloc[0], ' 202411010000')
        self.assertEqual(frame.station.iloc[0], '12207')
        self.assertEqual(frame.state_raw.iloc[0], '04')
        self.assertEqual(frame.ice.iloc[0], 1.)

    def test_credential_assignment_spacing_quotes_and_duplicate_rejection(self):
        with TemporaryDirectory() as folder, patch.dict('os.environ', {'KMA_AUTH_KEY': ''}):
            path = Path(folder) / 'secret.env'
            path.write_text('\ufeff# comment\nexport KMA_AUTH_KEY = "synthetic-test-value"\n', encoding='utf-8')
            self.assertEqual(load_auth_key(path), 'synthetic-test-value')
            path.write_text('KMA_AUTH_KEY=a\nKMA_AUTH_KEY=b\n', encoding='utf-8')
            with self.assertRaises(ValueError) as error: load_auth_key(path)
            self.assertNotIn('KMA_AUTH_KEY=a', str(error.exception))

    def test_reserved_winter_and_protected_station_are_closed(self):
        for station, start, end in [('12410', '2024-11-01', '2024-11-01'), ('12207', '2025-11-01', '2025-11-01'),
                                    ('12207', '2025-02-28', '2025-03-01'), ('0', '2024-11-01', '2024-11-01')]:
            with self.assertRaises(ValueError): validate_development_request(PLAN, station, start, end)
        jobs = list(daily_requests(PLAN, '2024-11-01', '2024-11-02', ['12207']))
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0][2], pd.Timestamp('2024-11-01 23:59'))
        self.assertEqual(jobs[1][1], pd.Timestamp('2024-11-02 00:00'))
        halves = list(daily_requests(PLAN, '2024-11-01', '2024-11-01', ['12207'], window_minutes=720))
        self.assertEqual(len(halves), 2)
        self.assertEqual(halves[0][2], pd.Timestamp('2024-11-01 11:59'))
        self.assertEqual(halves[1][1], halves[0][2] + pd.Timedelta(minutes=1))
        self.assertEqual(halves[1][2], pd.Timestamp('2024-11-01 23:59'))

    def test_target_codes_missing_values_and_exact_grid_preserved(self):
        body = response(['202411010000,12207,36.1289,126.6282,69,04,-99.9',
                         '202411010001,12207,36.1289,126.6282,69,04,-0.5',
                         '202411010010,12207,36.1289,126.6282,69,13,-1.0',
                         '202411010020,12207,36.1289,126.6282,69,15,-99.2',
                         '202411010030,12207,36.1289,126.6282,69,0,-999',
                         '202411010040,12207,36.1289,126.6282,69,-999,-99.7'])
        frame = parse_observations(body, '12207', '2024-11-01', '2024-11-01 23:59')
        ten = exact_ten_minute_grid(frame)
        self.assertEqual(ten.time.dt.minute.tolist(), [0, 10, 20, 30, 40])
        self.assertEqual(ten.ice.iloc[:3].tolist(), [1., 0., 0.])
        self.assertTrue(ten.ice.iloc[3:].isna().all())
        self.assertTrue(pd.isna(ten.road_temp.iloc[0]))
        self.assertEqual(ten.road_temp.iloc[1], -1.)
        self.assertTrue(ten.road_temp.iloc[2:].isna().all())

    def test_schema_wrong_station_range_duplicates_and_empty_data(self):
        row = '202411010000 12207 36.1289 126.6282 69 04 -0.5'
        for body in ['HTTP authentication error', response([row.replace('12207', '12410')]),
                     response([row.replace('202411010000', '202411020000')]), response([row, row]), response([row + ' extra'])]:
            with self.assertRaises(RwisResponseError): parse_observations(body, '12207', '2024-11-01', '2024-11-01 23:59')
        empty = parse_observations(response([]), '12207', '2024-11-01', '2024-11-01 23:59')
        self.assertTrue(empty.empty)
        self.assertIn('state_raw', empty.columns)


if __name__ == '__main__':
    unittest.main()
