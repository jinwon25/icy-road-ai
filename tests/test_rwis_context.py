import unittest
import numpy as np
import pandas as pd

from src.rwis_context import add_source_history, select_reference, pair_context


class RwisContextTests(unittest.TestCase):
    def test_rain_does_not_cross_midnight_gap_or_reset(self):
        data = pd.DataFrame({'station': ['A'] * 6,
                             'time': pd.to_datetime(['2025-01-01 23:50', '2025-01-02 00:00',
                                                     '2025-01-02 00:10', '2025-01-02 00:30',
                                                     '2025-01-02 00:40', '2025-01-02 00:50']),
                             'rain_cum': [10., 0., .2, .5, .1, .4], 'ice': [0., 1., 0., np.nan, 0., 0.]})
        result = add_source_history(data)
        self.assertTrue(result.rain_10m.iloc[[0, 1, 3, 4]].isna().all())
        np.testing.assert_allclose(result.rain_10m.iloc[[2, 5]], [.2, .3])
        self.assertEqual(result.ice_seen_60m.iloc[-1], 1.)

    def test_entire_inner_and_outer_holdout_removed(self):
        meta = pd.DataFrame({'route': ['R'] * 4, 'lat': [35.] * 4,
                             'lon': [127., 127.01, 127.02, 127.03],
                             'has_moisture': [True] * 4}, index=['A', 'B', 'C', 'D'])
        self.assertEqual(select_reference(meta, 'A', {'B', 'C'})[0], 'D')
        self.assertIsNone(select_reference(meta, 'A', {'B', 'C', 'D'})[0])
        meta.index = ['A', '12410.0', 'C', 'D']
        with self.assertRaises(ValueError):
            select_reference(meta, 'A', set())

    def test_pair_rejects_self_reference(self):
        data = pd.DataFrame({'station': ['A'], 'time': pd.to_datetime(['2025-01-01'])})
        with self.assertRaises(ValueError):
            pair_context(data, data, 'rwis')
        target = data.assign(station='12103')
        source = data.assign(station='12103.0')
        with self.assertRaises(ValueError):
            pair_context(target, source, 'rwis')


if __name__ == '__main__':
    unittest.main()
