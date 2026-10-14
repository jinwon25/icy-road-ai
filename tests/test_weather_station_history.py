"""날짜 단위 메타데이터를 정확한 관측 가용성으로 오해하지 않도록 검사한다."""
import unittest
import pandas as pd

from src.weather_station_history import normalize_history, stable_candidates, rank_candidates


def row(station='101', start='2020-01-01', end=None, lat=36., lon=127.):
    return {'지점': station, '시작일': start, '종료일': end, '지점명': '합성 지점',
            '위도': lat, '경도': lon, '노장해발고도(m)': 100.}


class StationHistoryTests(unittest.TestCase):
    def test_open_end_metadata_is_not_observation_availability(self):
        data = normalize_history(pd.DataFrame([row()]), 'AWS')
        stable, excluded = stable_candidates(data)
        self.assertEqual(len(stable), 1)
        self.assertFalse(stable.observations_available_verified.iloc[0])
        self.assertTrue(excluded.empty)

    def test_change_during_winter_rejected_for_static_selection(self):
        data = normalize_history(pd.DataFrame([row(end='2025-01-01'), row(start='2025-01-01', lat=36.1)]), 'AWS')
        stable, excluded = stable_candidates(data)
        self.assertTrue(stable.empty)
        self.assertEqual(excluded.overlapping_records.iloc[0], 2)

    def test_date_precision_boundary_is_not_midnight_precision(self):
        data = normalize_history(pd.DataFrame([row(start='2024-11-01')]), 'AWS')
        stable, _ = stable_candidates(data)
        self.assertTrue(stable.empty)
        data = normalize_history(pd.DataFrame([row(end='2025-03-01')]), 'AWS')
        stable, _ = stable_candidates(data)
        self.assertEqual(len(stable), 1)

    def test_stopped_station_and_invalid_coordinate_excluded(self):
        data = normalize_history(pd.DataFrame([row(end='2024-09-01'), row('102', lat=-999.)]), 'AWS')
        stable, excluded = stable_candidates(data)
        self.assertTrue(stable.empty)
        self.assertEqual(len(excluded), 1)

    def test_nearest_rank_uses_metadata_and_reports_cache_status(self):
        data = normalize_history(pd.DataFrame([row(), row('102', lat=37.)]), 'AWS')
        stable, _ = stable_candidates(data)
        points = pd.DataFrame({'station': ['12103'], 'lat': [36.], 'lon': [127.]})
        ranked = rank_candidates(points, stable, {('AWS', '102')}, limit=2)
        self.assertEqual(ranked.weather_station.tolist(), ['101', '102'])
        self.assertEqual(ranked.distance_km.iloc[0], 0)
        self.assertFalse(ranked.already_in_weather_cache.iloc[0])
        self.assertFalse(ranked.observation_data_verified.any())

    def test_outcome_and_protected_target_rejected(self):
        stable, _ = stable_candidates(normalize_history(pd.DataFrame([row()]), 'AWS'))
        points = pd.DataFrame({'station': ['12410.0'], 'lat': [36.], 'lon': [127.]})
        with self.assertRaises(ValueError):
            rank_candidates(points, stable, set())
        points['station'] = '12103'; points['road_temp'] = 0.
        with self.assertRaises(ValueError):
            rank_candidates(points, stable, set())


if __name__ == '__main__':
    unittest.main()
