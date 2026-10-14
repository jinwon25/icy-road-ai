import unittest
import pandas as pd
from src.event_retention import compare_event_retention


def events(values):
    return pd.DataFrame({'station': ['12207']*3, 'start_kst': ['2024-11-01 00:00:00', '2024-11-02 00:00:00', '2024-11-03 00:00:00'], 'slots': [1, 2, 3], 'detected_slots': values})


class EventRetentionTests(unittest.TestCase):
    def test_count_increase_cannot_hide_a_lost_single_event(self):
        r = compare_event_retention(events([1, 0, 0]), events([0, 1, 1]))
        self.assertGreater(r['candidate_detected'], r['baseline_detected'])
        self.assertEqual(r['lost_events'], 1); self.assertEqual(r['gained_events'], 2)
        self.assertEqual(r['lost_single_slot_events'], 1); self.assertFalse(r['eligible_no_event_loss'])

    def test_detection_can_move_within_the_same_event(self):
        r = compare_event_retention(events([1, 1, 2]), events([1, 2, 1]))
        self.assertTrue(r['eligible_no_event_loss']); self.assertEqual(r['retained_events'], 3)

    def test_event_population_mismatch_and_duplicates_rejected(self):
        a, b = events([1, 0, 1]), events([1, 0, 1]); b.loc[1, 'slots'] = 5
        with self.assertRaises(ValueError): compare_event_retention(a, b)
        with self.assertRaises(ValueError): compare_event_retention(a, pd.concat([a, a]))

    def test_protected_and_opened_station_events_rejected(self):
        for station in ['12410', '23102']:
            f = events([1, 0, 0]); f.station = station
            with self.assertRaises(ValueError): compare_event_retention(f, f)


if __name__ == '__main__': unittest.main()
