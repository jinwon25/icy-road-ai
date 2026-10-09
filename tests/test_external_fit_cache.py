import json
import tempfile
import unittest
from pathlib import Path
import pandas as pd
from src.data_source import sha256_file
from src.external_augmentation import fit_cache_key, CompletedFitCache


class CompletedFitTests(unittest.TestCase):
    def source(self, root):
        path = root / 'original'
        path.mkdir()
        (path / 'model.joblib').write_bytes(b'completed model artifact')
        info = {'fit_cache_key': 'key', 'threshold': .25,
                'files': {'model.joblib': sha256_file(path / 'model.joblib')}}
        (path / 'fit_manifest.json').write_text(json.dumps(info), encoding='utf-8')
        cache = CompletedFitCache();cache.register('key', path)
        return path, cache

    def test_training_identity_includes_values_labels_order_exclusions_and_signature(self):
        frame = pd.DataFrame({'station': ['a', 'b'], 'time': pd.to_datetime(['2024-11-01', '2024-11-02']),
                              'ice': [1., 0.], 'feature': [2., 3.]})
        key = fit_cache_key(frame, {'z', 'x'}, 'thermal', {'config': 'one'})
        self.assertEqual(key, fit_cache_key(frame.copy(), {'x', 'z'}, 'thermal', {'config': 'one'}))
        changes = [frame.iloc[::-1], frame.assign(ice=[0., 0.]), frame.assign(feature=[9., 3.]),
                   frame.assign(ice=frame.ice.astype('int64'))]
        for changed in changes:
            self.assertNotEqual(key, fit_cache_key(changed, {'z', 'x'}, 'thermal', {'config': 'one'}))
        self.assertNotEqual(key, fit_cache_key(frame, {'z'}, 'thermal', {'config': 'one'}))
        self.assertNotEqual(key, fit_cache_key(frame, {'z', 'x'}, 'thermal', {'config': 'two'}))

    def test_complete_files_and_threshold_are_copied_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);source, cache = self.source(root);target = root / 'copy'
            self.assertFalse(cache.materialize('different', target))
            self.assertFalse(target.exists())
            self.assertTrue(cache.materialize('key', target))
            for name in ['model.joblib', 'fit_manifest.json']:
                self.assertEqual((source / name).read_bytes(), (target / name).read_bytes())
            self.assertEqual(json.loads((target / 'cache_reuse_receipt.json').read_text())['source_fit_manifest_sha256'],
                             sha256_file(source / 'fit_manifest.json'))

    def test_changed_model_or_receipt_is_rejected_before_copy(self):
        for change in ['model.joblib', 'fit_manifest.json']:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory);source, cache = self.source(root)
                (source / change).write_bytes(b'changed')
                with self.assertRaises(ValueError):cache.materialize('key', root / 'copy')
                self.assertFalse((root / 'copy').exists())

    def test_existing_conflicting_files_and_unsafe_names_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);source, cache = self.source(root);target = root / 'copy';target.mkdir()
            (target / 'model.joblib').write_bytes(b'old evidence')
            with self.assertRaises(ValueError):cache.materialize('key', target)
            self.assertEqual((target / 'model.joblib').read_bytes(), b'old evidence')
            info = {'fit_cache_key': 'unsafe', 'files': {'../outside': 'irrelevant'}}
            (source / 'fit_manifest.json').write_text(json.dumps(info), encoding='utf-8')
            cache.register('unsafe', source)
            with self.assertRaises(ValueError):cache.materialize('unsafe', root / 'new')
            self.assertFalse((root / 'new').exists())


if __name__ == '__main__':
    unittest.main()
