import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from src.external_reserved import reserved_times, validate_reserved_predictions, seal_reserved_predictions, verify_reserved_freeze, reserved_request_plan
from src.kma_rwis_download import validate_development_request

PROJECT = Path(__file__).resolve().parents[1]


class ExternalReservedTests(unittest.TestCase):
    def plan_and_predictions(self):
        plan = json.loads((PROJECT / 'config/kma_external_validation_plan.json').read_text(encoding='utf-8'))
        plan['reserved_validation_end_kst'] = plan['reserved_validation_start_kst']
        frames = []
        for group, stations in plan['station_groups'].items():
            for station in stations:
                frame = pd.DataFrame({'station': station, 'time': reserved_times(plan), 'group': group,
                    'selected_candidate': 'baseline', 'temperature_candidate': 'baseline',
                    'baseline_ice_score': .2, 'selected_ice_score': .2, 'baseline_prediction': 0, 'selected_prediction': 0,
                    'baseline_threshold': .3, 'selected_threshold': .3, 'baseline_temperature_c': -1., 'selected_temperature_c': -1.})
                frames.append(frame)
        return plan, pd.concat(frames, ignore_index=True)

    def test_full_grid_fixed_threshold_and_no_labels_required(self):
        plan, frame = self.plan_and_predictions(); validate_reserved_predictions(frame, plan)
        for changed in [frame.iloc[:-1], pd.concat([frame, frame.iloc[:1]]), frame.assign(ice=1)]:
            with self.assertRaises(ValueError): validate_reserved_predictions(changed, plan)
        changed = frame.copy(); changed.loc[0, 'selected_threshold'] = .5
        with self.assertRaises(ValueError): validate_reserved_predictions(changed, plan)
        changed = frame.copy(); changed.loc[0, 'selected_prediction'] = 1
        with self.assertRaises(ValueError): validate_reserved_predictions(changed, plan)

    def test_seal_before_outcomes_and_detect_evidence_mutation(self):
        plan, frame = self.plan_and_predictions()
        with TemporaryDirectory() as folder:
            root = Path(folder); out = root / 'outputs/private/external_reserved_predictions_v1'; out.mkdir(parents=True)
            plan_path = root / 'plan.json'; plan_path.write_text(json.dumps(plan), encoding='utf-8')
            model_path = root / 'model.txt'; model_path.write_text('saved model', encoding='utf-8')
            frame.to_parquet(out / 'predictions.parquet', index=False)
            receipt = seal_reserved_predictions(root, out, plan_path, ['model.txt'])
            self.assertEqual(verify_reserved_freeze(root, out), receipt)
            request_plan = reserved_request_plan(receipt)
            validate_development_request(request_plan, '12207', '2025-11-01', '2025-11-01 11:59')
            for station, start in [('12410', '2025-11-01'), ('12207', '2024-11-01')]:
                with self.assertRaises(ValueError): validate_development_request(request_plan, station, start, start)
            model_path.write_text('changed model', encoding='utf-8')
            with self.assertRaises(ValueError): verify_reserved_freeze(root, out)
            with self.assertRaises(FileExistsError): seal_reserved_predictions(root, out, plan_path, ['model.txt'])

    def test_already_acquired_outcomes_prevent_new_prediction_receipt(self):
        plan, frame = self.plan_and_predictions()
        with TemporaryDirectory() as folder:
            root = Path(folder); out = root / 'predictions'; out.mkdir()
            frame.to_parquet(out / 'predictions.parquet', index=False)
            plan_path = root / 'plan.json'; plan_path.write_text(json.dumps(plan), encoding='utf-8')
            (root / 'outputs/private/external/kma_rwis_reserved_v1').mkdir(parents=True)
            with self.assertRaises(ValueError): seal_reserved_predictions(root, out, plan_path, [])


if __name__ == '__main__':
    unittest.main()
