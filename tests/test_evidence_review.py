"""위치·결측 분모·완전 미탐일과 학습 범위의 의미를 합성 자료로 검사한다."""
import unittest

import numpy as np
import pandas as pd

from src.evidence_review import (review_domain, coordinate_review, day_counts,
                                 aggregate_days, fit_feature_envelope, feature_support)


def frame(y, p, station='12103', start='2024-11-01'):
    return pd.DataFrame({'station': station, 'time': pd.date_range(start, periods=len(y), freq='10min'),
                         'ice': y, 'prediction': p})


class EvidenceReviewTests(unittest.TestCase):
    def test_miss_day_f1_zero_even_when_precision_undefined(self):
        days = day_counts(frame([1] + [0] * 143, [0] * 144), 'prediction')
        self.assertTrue(np.isnan(days.precision.iloc[0]))
        self.assertEqual(days.recall.iloc[0], 0)
        self.assertEqual(days.f1.iloc[0], 0)
        normal = aggregate_days(days, 144, 'metricwise_omit', ['12103'])
        joint = aggregate_days(days, 144, 'joint_defined_only', ['12103'])
        self.assertEqual(normal['f1_days'], 1)
        self.assertEqual(joint['f1_days'], 0)
        self.assertEqual(joint['included_ice_days'], 0)

    def test_false_alarm_day_f1_zero_even_when_recall_undefined(self):
        days = day_counts(frame([0] * 144, [1] + [0] * 143), 'prediction')
        result = aggregate_days(days, 144, 'metricwise_omit', ['12103'])
        self.assertEqual(result['f1_available_station_macro'], 0)
        self.assertEqual(result['precision_days'], 1)
        self.assertEqual(result['recall_days'], 0)
        self.assertEqual(result['included_false_alarm_only_days'], 1)

    def test_both_zero_days_omitted_even_under_zero_fill_variant(self):
        days = day_counts(frame([0] * 144, [0] * 144), 'prediction')
        result = aggregate_days(days, 144, 'undefined_zero', ['12103'])
        self.assertEqual(result['both_zero_days'], 1)
        self.assertEqual(result['f1_days'], 0)
        self.assertIsNone(result['f1_available_station_macro'])
        self.assertEqual(result['f1_fixed_station_zero_undefined'], 0)

    def test_missing_label_does_not_become_nonice_or_complete(self):
        days = day_counts(frame([1] + [0] * 142 + [np.nan], [1] + [0] * 143), 'prediction')
        self.assertEqual(days.slots.iloc[0], 143)
        complete = aggregate_days(days, 144, 'metricwise_omit', ['12103'])
        partial = aggregate_days(days, 130, 'metricwise_omit', ['12103'])
        self.assertEqual(complete['excluded_by_coverage_ice_days'], 1)
        self.assertEqual(partial['f1_available_station_macro'], 1)

    def test_station_macro_does_not_weight_by_number_of_days(self):
        a = frame([1] * 288, [1] * 288)
        b = frame([1] * 144, [0] * 144, station='12209')
        days = day_counts(pd.concat([a, b], ignore_index=True), 'prediction')
        result = aggregate_days(days, 144, 'metricwise_omit', ['12103', '12209'])
        self.assertEqual(result['f1_available_station_macro'], .5)
        self.assertEqual(result['f1_days'], 3)

    def test_normalized_protected_id_and_next_winter_rejected(self):
        for station in [' 12410.0 ', '33411', '23402']:
            with self.assertRaisesRegex(ValueError, 'protected'):
                review_domain(frame([1], [1], station=station))
        with self.assertRaises(ValueError):
            review_domain(frame([1], [1], start='2025-11-01'))

    def test_duplicate_and_fractional_timestamp_rejected(self):
        data = frame([1, 0], [1, 0])
        with self.assertRaises(ValueError):
            review_domain(pd.concat([data, data], ignore_index=True))
        data.loc[0, 'time'] += pd.Timedelta(microseconds=1)
        with self.assertRaises(ValueError):
            review_domain(data)

    def test_coordinate_match_is_not_physical_verification(self):
        data = frame([1, 0], [1, 0]); data['lat'] = [36., np.nan]; data['lon'] = [127., 127.]
        catalog = pd.DataFrame({'station': ['12103'], 'name': ['synthetic'], 'lat': [36.], 'lon': [127.]})
        summary, pairs = coordinate_review(data, catalog)
        self.assertEqual(summary.coordinate_rows.iloc[0], 1)
        self.assertEqual(summary.missing_or_invalid_rows.iloc[0], 1)
        self.assertEqual(pairs.distance_m.iloc[0], 0)
        self.assertFalse(summary.physical_location_verified.iloc[0])
        data['lat'] = 36.01
        summary, _ = coordinate_review(data, catalog)
        self.assertEqual(summary.status.iloc[0], 'catalogue_response_discrepancy')

    def test_feature_envelope_uses_training_only_and_preserves_missing(self):
        train = frame([0, 1, 0], [0, 1, 0]); train['weather'] = [0., 1., 2.]
        envelope = fit_feature_envelope(train, ['weather'])
        target = frame([1, 0, 1], [1, 0, 1], station='12209'); target['weather'] = [1., 10., np.nan]
        summary, detail = feature_support(target, envelope)
        self.assertEqual(envelope.loc['weather', 'maximum'], 2)
        self.assertAlmostEqual(summary.any_missing_fraction.iloc[0], 1 / 3)
        self.assertAlmostEqual(summary.any_outside_training_range_fraction.iloc[0], 1 / 3)
        self.assertFalse(summary.predictive_reliability_verified.iloc[0])
        self.assertEqual(detail.outside_range_fraction.iloc[0], 1 / 3)

    def test_outcomes_and_infinite_features_rejected(self):
        data = frame([0, 1], [0, 1]); data['weather'] = [0., np.inf]
        with self.assertRaises(ValueError):
            fit_feature_envelope(data, ['weather'])
        with self.assertRaises(ValueError):
            fit_feature_envelope(data, ['ice'])
        with self.assertRaises(ValueError):
            day_counts(frame([0, 1], [0, np.nan]), 'prediction')


if __name__ == '__main__':
    unittest.main()
