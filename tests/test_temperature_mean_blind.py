"""미개봉 평가의 동일 분모·빈 양성·지점/사건 손실 방지 조건을 검증한다."""
import copy
import json
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from scripts.audit_temperature_mean_blind import temperature_gate, ice_gate
from scripts.audit_temperature_blind_validation import reference_temperature
from src.kma_rwis_download import daily_requests

ROOT = Path(__file__).resolve().parents[1]


class MeanBlindTests(unittest.TestCase):
    def test_request_plan_only_full_first_winter_two_unopened_stations(self):
        plan = json.loads((ROOT / 'config/temperature_mean_blind_validation_20261010.json').read_text(encoding='utf-8'))
        jobs = list(daily_requests(plan, plan['development_start_kst'], plan['development_end_kst'], window_minutes=1440))
        self.assertEqual(len(jobs), 240)
        self.assertEqual({s for s, _, _ in jobs}, {'23102', '23407'})
        self.assertFalse({s for s, _, _ in jobs} & set(plan['competition_stations_excluded_from_external_requests']))
        self.assertTrue(all(pd.Timestamp('2024-11-01') <= a <= b < pd.Timestamp('2025-03-01') for _, a, b in jobs))

    def temperature_reports(self):
        frame = pd.DataFrame({'station': ['a', 'a', 'b', 'b'], 'road_temp': [0., 1., 0., 1.],
                              'base': [1., 2., 1., 2.], 'candidate': [.5, 1.5, .5, 1.5]})
        b, c = (reference_temperature(frame, n) for n in ['base', 'candidate'])
        return b, c

    def test_temperature_good_and_missing_station(self):
        b, c = self.temperature_reports()
        self.assertTrue(temperature_gate(b, c, b, c))
        for r in [b, c]:
            r['stations']['b']['n'] = 0
        self.assertFalse(temperature_gate(b, c, b, c))

    def test_temperature_different_denominators_are_rejected(self):
        b, c = self.temperature_reports(); c['stations']['b']['n'] = 1
        with self.assertRaisesRegex(ValueError, 'denominators'):
            temperature_gate(b, c, b, c)

    def test_average_improvement_does_not_override_station_or_near_freezing_loss(self):
        b, c = self.temperature_reports(); c['stations']['b']['mae'] = 1.06
        self.assertFalse(temperature_gate(b, c, b, c))
        b, c = self.temperature_reports(); bad_near = copy.deepcopy(c); bad_near['pooled']['mae'] = 1.1
        self.assertFalse(temperature_gate(b, c, b, bad_near))

    def ice_frame(self):
        frame = pd.DataFrame({'station': 'a', 'time': pd.date_range('2024-11-01', periods=144, freq='10min'),
                              'ice': np.zeros(144), 'thermal_weather14': np.zeros(144, dtype=int),
                              'thermal_equal_mean': np.zeros(144, dtype=int)})
        return frame

    def test_no_positive_ice_cannot_establish_ice_performance(self):
        gate = ice_gate(self.ice_frame())
        self.assertFalse(gate['passed']); self.assertEqual(gate['status'], 'not_estimable_without_positive_ice')

    def test_lower_false_alarms_cannot_hide_missed_single_event(self):
        f = self.ice_frame(); f.loc[10, 'ice'] = 1; f.loc[[10, 20], 'thermal_weather14'] = 1
        gate = ice_gate(f)
        self.assertTrue(gate['checks']['false_positives_nonincreasing'])
        self.assertFalse(gate['checks']['false_negatives_nonincreasing'])
        self.assertFalse(gate['checks']['single_slot_detection_nonworse']); self.assertFalse(gate['passed'])

    def test_aggregate_recall_cannot_hide_loss_at_one_positive_station(self):
        a, b = self.ice_frame(), self.ice_frame(); b['station'] = 'b'
        a.loc[10, 'ice'] = 1; a.loc[10, 'thermal_weather14'] = 1
        b.loc[[10, 11], 'ice'] = 1; b.loc[[10, 11], 'thermal_equal_mean'] = 1
        gate = ice_gate(pd.concat([a, b], ignore_index=True))
        self.assertTrue(gate['checks']['false_negatives_nonincreasing'])
        self.assertFalse(gate['checks']['each_positive_station_recall_nonworse']); self.assertFalse(gate['passed'])

    def test_equal_recall_with_lower_false_alarms_passes(self):
        f = self.ice_frame(); f.loc[10, 'ice'] = 1; f.loc[[10, 20], 'thermal_weather14'] = 1
        f.loc[10, 'thermal_equal_mean'] = 1
        self.assertTrue(ice_gate(f)['passed'])


if __name__ == '__main__':
    unittest.main()
