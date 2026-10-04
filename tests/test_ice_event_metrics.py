import unittest
import pandas as pd

from src.ice_event_metrics import event_metrics


class IceEventMetricsTests(unittest.TestCase):
    def test_time_gaps_and_unknown_labels_break_episodes(self):
        data = pd.DataFrame({'station': ['A'] * 6,
                             'time': pd.to_datetime(['2025-01-01 00:00', '2025-01-01 00:10',
                                                     '2025-01-01 00:30', '2025-01-01 00:40',
                                                     '2025-01-01 00:50', '2025-01-01 01:00']),
                             'ice': [1, 1, 1, None, 0, 0], 'predicted_ice': [0, 1, 0, 1, 1, 1]})
        result = event_metrics(data)
        self.assertEqual(result['observed_events'], 2)
        self.assertEqual(result['detected_events'], 1)
        self.assertEqual(result['predicted_events'], 2)
        self.assertEqual(result['false_alarm_events'], 1)
        self.assertEqual(result['max_predicted_event_slots'], 2)
        self.assertEqual(result['event_recall'], .5)


if __name__ == '__main__':
    unittest.main()
