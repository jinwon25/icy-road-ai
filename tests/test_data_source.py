import json
import tempfile
import unittest
from pathlib import Path

from src.data_source import competition_archive, sha256_file


class DataSourceTests(unittest.TestCase):
    def test_explicit_selection_and_replacement_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            chosen = root / "original.zip"
            chosen.write_bytes(b"original")
            (root / "new_release.zip").write_bytes(b"new")
            config = {"archive_filename": chosen.name, "sha256": sha256_file(chosen)}
            (root / "config/data_source.json").write_text(json.dumps(config), encoding="utf-8")
            self.assertEqual(competition_archive(root), chosen.resolve())
            chosen.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                competition_archive(root)
            chosen.unlink()
            with self.assertRaises(FileNotFoundError):
                competition_archive(root)


if __name__ == "__main__":
    unittest.main()
