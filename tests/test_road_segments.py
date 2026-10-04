import unittest
from shapely.geometry import LineString

from src.road_segments import prepare_chains, split_chain, endpoint_topology


class RoadSegmentTests(unittest.TestCase):
    def test_length_conserved_and_short_tail_retained(self):
        line = LineString([(0, 0), (1200, 0), (1200, 1300)])
        pieces = split_chain(line)
        self.assertEqual([round(p[2].length) for p in pieces], [1000, 1000, 500])
        self.assertAlmostEqual(sum(p[2].length for p in pieces), line.length)

    def test_gap_and_crossing_are_not_connected(self):
        chains = prepare_chains([LineString([(0, 0), (100, 0)]),
                                 LineString([(101, 0), (200, 0)]),
                                 LineString([(50, -10), (50, 10)])])
        self.assertEqual(len(chains), 3)
        self.assertEqual(endpoint_topology(chains)['endpoint_components'], 3)

    def test_shared_endpoint_merged_and_order_deterministic(self):
        a, b = LineString([(0, 0), (100, 0)]), LineString([(100, 0), (200, 0)])
        forward, reverse = prepare_chains([a, b]), prepare_chains([b, a])
        self.assertEqual(len(forward), 1)
        self.assertEqual(forward[0].wkb, reverse[0].wkb)


if __name__ == '__main__':
    unittest.main()
