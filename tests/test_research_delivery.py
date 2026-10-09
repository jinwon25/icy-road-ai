from pathlib import Path
import json
import tempfile
import unittest
from src.research_delivery import file_sha, verify_delivery


class ResearchDeliveryTests(unittest.TestCase):
    def test_changed_asset_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); asset = root / 'model.txt'; asset.write_text('frozen', 'utf-8')
            manifest = dict(scope='private_research_handoff_not_final_competition_submission', files={'model.txt': file_sha(asset)})
            (root / 'manifest.json').write_text(json.dumps(manifest), 'utf-8')
            self.assertEqual(len(verify_delivery(root)['files']), 1)
            asset.write_text('changed', 'utf-8')
            with self.assertRaisesRegex(ValueError, 'Changed'): verify_delivery(root)

    def test_manifest_cannot_read_outside_delivery(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'package'; root.mkdir(); outside = root.parent / 'outside.txt'; outside.write_text('x', 'utf-8')
            manifest = dict(scope='private_research_handoff_not_final_competition_submission', files={'../outside.txt': file_sha(outside)})
            (root / 'manifest.json').write_text(json.dumps(manifest), 'utf-8')
            with self.assertRaisesRegex(ValueError, 'unsafe'): verify_delivery(root)


if __name__ == '__main__': unittest.main()
