import hashlib
import json
import pytest
from scripts.review_submission_bundle import verify_directory


def bundle(tmp_path):
    data=b'fixed bytes';(tmp_path/'model.bin').write_bytes(data)
    manifest=dict(package_label='test',files={'model.bin':dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())})
    (tmp_path/'manifest.json').write_text(json.dumps(manifest),encoding='utf8');return manifest


def test_bundle_verifier_accepts_declared_files_and_separate_local_outputs(tmp_path):
    bundle(tmp_path);(tmp_path/'local_review').mkdir();(tmp_path/'local_review/result.txt').write_text('local run')
    assert verify_directory(tmp_path)['files']==1
    (tmp_path/'model.bin').write_bytes(b'changed byt')
    with pytest.raises(ValueError):verify_directory(tmp_path)


def test_bundle_verifier_rejects_extra_files_and_traversal(tmp_path):
    m=bundle(tmp_path);(tmp_path/'undeclared.csv').write_text('unexpected')
    with pytest.raises(ValueError):verify_directory(tmp_path)
    m['files']['../outside']=m['files']['model.bin'];(tmp_path/'manifest.json').write_text(json.dumps(m),encoding='utf8')
    with pytest.raises(ValueError):verify_directory(tmp_path)
