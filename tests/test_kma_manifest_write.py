"""목록 교체가 잠시 거부되거나 계속 실패해도 기존·임시 증거를 보존한다."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.download_kma_external_development import write_json


class ManifestWriteTests(unittest.TestCase):
    def denied(self):
        error = PermissionError('temporary sharing denial')
        error.winerror = 5
        return error

    def test_temporary_windows_denial_retries_without_losing_previous_receipt(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'manifest.json'
            path.write_text('{"old": true}', encoding='utf-8')
            replace = Path.replace
            attempts = []
            def sharing_guard(source, target):
                attempts.append(source)
                if len(attempts) < 3:
                    self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'old': True})
                    self.assertEqual(json.loads(source.read_text(encoding='utf-8')), {'new': True})
                    raise self.denied()
                return replace(source, target)
            with patch.object(Path, 'replace', sharing_guard), patch('scripts.download_kma_external_development.time.sleep') as sleep:
                write_json(path, {'new': True})
            self.assertEqual(len(attempts), 3)
            self.assertEqual(sleep.call_count, 2)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'new': True})

    def test_persistent_denial_preserves_old_and_completed_pending_manifest(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'manifest.json'
            path.write_text('{"old": true}', encoding='utf-8')
            with patch.object(Path, 'replace', side_effect=self.denied()) as replace, patch('scripts.download_kma_external_development.time.sleep'):
                with self.assertRaises(PermissionError):
                    write_json(path, {'new': True})
            self.assertEqual(replace.call_count, 8)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'old': True})
            self.assertEqual(json.loads(path.with_suffix('.json.tmp').read_text(encoding='utf-8')), {'new': True})

    def test_unrelated_permission_failure_is_not_retried(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'manifest.json'
            with patch.object(Path, 'replace', side_effect=PermissionError('permanent denial')) as replace, patch('scripts.download_kma_external_development.time.sleep') as sleep:
                with self.assertRaises(PermissionError):
                    write_json(path, {'new': True})
            self.assertEqual(replace.call_count, 1)
            sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
