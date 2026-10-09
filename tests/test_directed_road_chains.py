import unittest
from math import cos, sin, pi
from shapely.geometry import LineString, MultiLineString
from src.directed_road_chains import audit_paths, split_path


def edge(key, f, t, xy):
    return {'LINK_ID': key, 'F_NODE': f, 'T_NODE': t, 'geometry': LineString(xy)}


class DirectedRoadTests(unittest.TestCase):
    def test_opposite_carriageway_with_different_nodes_is_not_followed(self):
        rows = [edge('a', 'A', 'B', [(0, 0), (10, 0)]),
                edge('b', 'B', 'C', [(10, 0), (20, 0)]),
                edge('r', 'B', 'D', [(10, 0), (1, 0)])]
        paths, audit = audit_paths(rows)
        self.assertEqual(paths, [['a', 'b'], ['r']])
        reverse = next(r for r in audit if r['from_link'] == 'a' and r['to_link'] == 'r')
        self.assertEqual(reverse['status'], 'turn_angle_exceeds_qa')

    def test_two_forward_branches_remain_separate(self):
        rows = [edge('a', 'A', 'B', [(0, 0), (10, 0)]),
                edge('b', 'B', 'C', [(10, 0), (20, 0)]),
                edge('c', 'B', 'D', [(10, 0), (20, 2)])]
        self.assertEqual(audit_paths(rows)[0], [['a'], ['b'], ['c']])

    def test_gap_and_turn_record_break_paths(self):
        rows = [edge('a', 'A', 'B', [(0, 0), (10, 0)]),
                edge('b', 'B', 'C', [(11, 0), (20, 0)])]
        self.assertEqual(audit_paths(rows, max_gap=.5)[0], [['a'], ['b']])
        self.assertEqual(audit_paths(rows, review_pairs={('a', 'b')})[0], [['a'], ['b']])

    def test_split_crosses_edges_without_inventing_gap_length(self):
        rows = [edge('a', 'A', 'B', [(0, 0), (700, 0)]),
                edge('b', 'B', 'C', [(700.5, 0), (1500.5, 0)])]
        parts = split_path(rows, 1000.)
        self.assertEqual(len(parts), 2)
        self.assertIsInstance(parts[0]['geometry'], MultiLineString)
        self.assertAlmostEqual(parts[0]['geometry'].length, 1000.)
        self.assertAlmostEqual(parts[1]['geometry'].length, 500.)
        self.assertEqual(parts[0]['lineage'][1]['link_m1'], 300.)
        self.assertEqual(parts[0]['geometry'].geoms[1].coords[0], (700.5, 0.))
        self.assertEqual(sum(p['geometry'].length for p in parts), 1500.)

    def test_reviewed_gap_exception_is_pair_specific_and_bounded(self):
        rows = [edge('a', 'A', 'B', [(0, 0), (10, 0)]),
                edge('b', 'B', 'C', [(12, 0), (20, 0)]),
                edge('c', 'C', 'D', [(22, 0), (30, 0)])]
        paths, audit = audit_paths(rows, gap_exceptions={('a', 'b'): 2.})
        self.assertEqual(paths, [['a', 'b'], ['c']])
        self.assertEqual(audit[0]['status'], 'accepted_with_reviewed_source_gap')
        self.assertEqual(audit_paths(rows, gap_exceptions={('a', 'b'): 1.9})[0], [['a'], ['b'], ['c']])
        self.assertEqual(audit_paths(rows, gap_exceptions={('a', 'b'): 2.}, review_pairs={('a', 'b')})[0], [['a'], ['b'], ['c']])

    def test_input_order_does_not_change_paths(self):
        rows = [edge('a', 'A', 'B', [(0, 0), (10, 0)]), edge('b', 'B', 'C', [(10, 0), (20, 0)])]
        self.assertEqual(audit_paths(rows), audit_paths(rows[::-1]))

    def test_cycles_and_disconnected_sequence_are_rejected(self):
        with self.assertRaises(ValueError):
            split_path([edge('a', 'A', 'B', [(0, 0), (10, 0)]), edge('b', 'C', 'D', [(10, 0), (20, 0)])])
        with self.assertRaises(ValueError):
            audit_paths([edge('a', 'A', 'B', [(0, 0), (10, 0)]), edge('a', 'B', 'C', [(10, 0), (20, 0)])])

    def test_smooth_directed_cycle_requires_review(self):
        points = [(100 * cos(i * pi / 6), 100 * sin(i * pi / 6)) for i in range(12)]
        rows = [edge(str(i), str(i), str((i + 1) % 12),
                     [points[i], points[(i + 1) % 12]]) for i in range(12)]
        with self.assertRaisesRegex(ValueError, 'cycle'):
            audit_paths(rows, look_m=5.)


if __name__ == '__main__':
    unittest.main()
