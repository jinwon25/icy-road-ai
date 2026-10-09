import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import numpy as np
import pandas as pd

from src.external_augmentation import FixedDonorStateContext, matrix_with_context, select_group_candidate
from scripts.evaluate_external_augmentation import json_write


class ExternalAugmentationTests(unittest.TestCase):
    def test_missing_reference_saved_as_null_without_imputing_predictors(self):
        frame, context = self.context()
        values, refs = matrix_with_context(frame, context, {'12103', '12209'}, ['aws_air_temp'])
        self.assertTrue(values.near_road_temp.isna().all())
        self.assertTrue(values.near_distance_km.isna().all())
        self.assertTrue(values.moisture_humidity.isna().all())
        self.assertTrue(all(r['source'] is None and r['distance_km'] is None for r in refs))
        with TemporaryDirectory() as folder:
            p = Path(folder) / 'references.json'
            json_write(p, refs)
            self.assertEqual(json.loads(p.read_text(encoding='utf-8')), refs)
        with patch.object(context, 'reference', return_value=('12209', np.nan)):
            with self.assertRaises(ValueError):
                matrix_with_context(frame, context, set(), ['aws_air_temp'])

    def context(self, mutate=False):
        time = pd.Timestamp('2024-12-01 01:00')
        frame = pd.DataFrame({'station': ['12207'], 'time': [time], 'aws_dewpoint': [-3.], 'aws_air_temp': [-2.],
                              'ice': [0. if mutate else 1.], 'road_temp': [99. if mutate else -2.], 'state_raw': ['01' if mutate else '04']})
        metadata = pd.DataFrame({'station': ['12207', '12408', '12103', '12209'], 'route': ['서해안'] * 4,
                                 'lat': [36., 36.00001, 36.01, 36.02], 'lon': [126.6] * 4})
        source = pd.DataFrame({'station': ['12103', '12209'], 'time': [time - pd.Timedelta(minutes=10)] * 2,
                               'road_temp': [99. if mutate else -1., -2.], 'temp_min60': [-2., -3.], 'temp_trend60': [-.1, -.2],
                               'humidity': [90., 80.], 'rain10': [0., 0.]})
        states = source[['station', 'time']].copy();states['state_raw'] = ['01' if mutate else '04', '01']
        context = FixedDonorStateContext(frame, source, metadata, states, ['12103', '12209'], '2025-03-01')
        return frame, context

    def test_targets_near_external_neighbors_and_excluded_sources_cannot_change_inputs(self):
        frame, context = self.context()
        values, refs = matrix_with_context(frame, context, {'12103', '12408'}, ['aws_air_temp'], state=True)
        changed_frame, changed_context = self.context(mutate=True)
        changed, changed_refs = matrix_with_context(changed_frame, changed_context, {'12103', '12408'}, ['aws_air_temp'], state=True)
        pd.testing.assert_frame_equal(values, changed)
        self.assertEqual(refs, changed_refs)
        self.assertTrue(all(r['source'] == '12209' for r in refs))
        self.assertEqual(values.near_road_temp.iloc[0], -2.)
        with self.assertRaises(ValueError): matrix_with_context(frame, context, set(), ['road_temp'])

    def test_external_dynamic_source_rejected_and_future_inventory_not_used(self):
        frame, context = self.context()
        source = context.source.copy();source.loc[0, 'station'] = '12408'
        states = context.state_source[['station', 'time']].copy();states['state_raw'] = '01'
        with self.assertRaises(ValueError): FixedDonorStateContext(frame, source, context.metadata.reset_index(), states, ['12103', '12209'], '2025-03-01')
        source = context.source.copy();source['time'] = pd.Timestamp('2025-12-01')
        later = FixedDonorStateContext(frame, source, context.metadata.reset_index().drop(columns='has_moisture'), states, ['12103', '12209'], '2025-03-01')
        self.assertIsNone(later.reference('12207', set(), moisture=True)[0])

    def test_group_selection_never_uses_its_own_labels_and_requires_both_improvements(self):
        rows = []
        for group in ['B', 'C', 'D']:
            for name, tp, fp, fn in [('baseline', 2, 10, 3), ('augmented_thermal', 3, 9, 2), ('augmented_surface_state_v2', 4, 12, 1)]:
                rows.append({'outer_held_group': 'A', 'validation_group': group, 'candidate': name, 'n': 100, 'tp': tp, 'fp': fp, 'fn': fn, 'tn': 100-tp-fp-fn, 'training_excluded_groups': ['A', group]})
        table = pd.DataFrame(rows);result = select_group_candidate(table, 'A', ['augmented_thermal', 'augmented_surface_state_v2'])
        self.assertEqual(result['selected_candidate'], 'augmented_thermal')
        poisoned = pd.concat([table, pd.DataFrame([{'outer_held_group': 'A', 'validation_group': 'A', 'candidate': 'augmented_thermal', 'n': np.nan, 'tp': 999999, 'fp': 0, 'fn': 0, 'tn': 0, 'training_excluded_groups': []}])], ignore_index=True)
        self.assertEqual(result, select_group_candidate(poisoned, 'A', ['augmented_thermal', 'augmented_surface_state_v2']))
        table.loc[table.candidate.eq('augmented_thermal'), 'fp'] = 11
        self.assertEqual(select_group_candidate(table, 'A', ['augmented_thermal', 'augmented_surface_state_v2'])['selected_candidate'], 'baseline')
        table.at[0, 'training_excluded_groups'] = ['B']
        with self.assertRaises(ValueError): select_group_candidate(table, 'A', ['augmented_thermal', 'augmented_surface_state_v2'])


if __name__ == '__main__':
    unittest.main()
