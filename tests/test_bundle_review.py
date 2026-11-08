import hashlib
import json
import pytest
from scripts.review_submission_bundle import verify_directory, select_notebook


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


def notebook_bundle(tmp_path, label='v7', current=None):
    names = ['notebooks/submission_review_v7.ipynb', 'notebooks/extended_submission_review.ipynb']
    manifest = bundle(tmp_path)
    manifest['package_label'] = label
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_text('{}', encoding='utf8')
        manifest['files'][name] = {'bytes': 2, 'sha256': hashlib.sha256(b'{}').hexdigest()}
    if current is not None:
        manifest['current_notebook'] = current
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest), encoding='utf8')
    return manifest


def test_bundle_smoke_uses_current_v7_not_previous_notebook(tmp_path):
    notebook_bundle(tmp_path)
    assert select_notebook(tmp_path) == 'notebooks/submission_review_v7.ipynb'
    assert select_notebook(tmp_path, 'notebooks/extended_submission_review.ipynb').endswith('extended_submission_review.ipynb')


def test_bundle_smoke_honors_declared_entrypoint_and_legacy_v6(tmp_path):
    notebook_bundle(tmp_path, label='v6')
    assert select_notebook(tmp_path).endswith('extended_submission_review.ipynb')
    notebook_bundle(tmp_path, label='v8', current='notebooks/submission_review_v7.ipynb')
    assert select_notebook(tmp_path).endswith('submission_review_v7.ipynb')


@pytest.mark.parametrize('name', ['../outside.ipynb', '/outside.ipynb', 'C:/outside.ipynb',
                                'notebooks\\outside.ipynb', 'notebooks/missing.ipynb', 'model.bin'])
def test_bundle_smoke_rejects_undeclared_or_escaping_notebooks(tmp_path, name):
    notebook_bundle(tmp_path, current=name)
    with pytest.raises(ValueError):
        select_notebook(tmp_path)
