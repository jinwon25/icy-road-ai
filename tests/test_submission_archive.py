import hashlib
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
import warnings
import zipfile
from src.submission_archive import restore_archive, verify_archive


class ArchiveTests(unittest.TestCase):
    def archive(self, folder, name='model/card.json', tamper=False, duplicate=False):
        content=b'{"example":true}'
        manifest={'files':{name:{'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}}}
        path=Path(folder)/'package.zip'
        with zipfile.ZipFile(path,'x') as z:
            z.writestr('manifest.json',json.dumps(manifest))
            z.writestr(name,b'changed' if tamper else content)
            if duplicate:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore',UserWarning); z.writestr(name,content)
        return path

    def test_verified_archive_restores_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            archive=self.archive(folder); target=Path(folder)/'restore'
            restore_archive(archive,target)
            self.assertTrue((target/'model/card.json').exists())
            with self.assertRaises(FileExistsError): restore_archive(archive,target)

    def test_hash_mismatch_rejected_before_restoration(self):
        with tempfile.TemporaryDirectory() as folder:
            archive=self.archive(folder,tamper=True); target=Path(folder)/'restore'
            with self.assertRaises(ValueError): restore_archive(archive,target)
            self.assertFalse(target.exists())

    def test_traversal_and_duplicate_members_rejected(self):
        for name, duplicate in [('../escape',False),('C:/escape',False),('safe',True)]:
            with tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(ValueError): verify_archive(self.archive(folder,name,duplicate=duplicate))

    def test_expected_archive_digest_is_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            archive=self.archive(folder); target=Path(folder)/'restore'
            with self.assertRaises(ValueError): restore_archive(archive,target,'0'*64)
            self.assertFalse(target.exists())

    def test_documented_module_cli_restores_package(self):
        with tempfile.TemporaryDirectory() as folder:
            archive=self.archive(folder); target=Path(folder)/'restore'
            result=subprocess.run([sys.executable,'-m','src.submission_archive','--archive',str(archive),'--output',str(target)],
                cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'],'verified_archive_restored')
