import hashlib
import json
import zipfile

import pytest

from scripts.package_submission_channels import verify_channel_archive, archive_channel


def model_folder(tmp_path):
    folder = tmp_path / 'model'
    folder.mkdir()
    data = b'fixed model content'
    (folder / 'model.bin').write_bytes(data)
    (folder / 'manifest.json').write_text(json.dumps({'files': {
        'model.bin': {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    }}), encoding='utf8')
    return folder


def test_submission_archive_has_one_top_level_folder_and_verified_content(tmp_path):
    folder = model_folder(tmp_path)
    result = archive_channel(folder)
    assert result['files'] == 1
    assert result['root'] == 'model'
    with zipfile.ZipFile(folder.with_suffix('.zip')) as archive:
        assert set(archive.namelist()) == {'model/model.bin', 'model/manifest.json'}


@pytest.mark.parametrize('member', ['second/file.txt', 'model/extra.txt', 'model/../escape.txt'])
def test_submission_archive_rejects_extra_root_or_undeclared_member(tmp_path, member):
    folder = model_folder(tmp_path)
    archive_channel(folder)
    path = folder.with_suffix('.zip')
    with zipfile.ZipFile(path, 'a') as archive:
        archive.writestr(member, b'extra')
    with pytest.raises(ValueError):
        verify_channel_archive(path, 'model')


def test_submission_archive_detects_changed_content(tmp_path):
    folder = model_folder(tmp_path)
    path = tmp_path / 'changed.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.write(folder / 'manifest.json', 'model/manifest.json')
        archive.writestr('model/model.bin', b'altered')
    with pytest.raises(ValueError, match='hash or size'):
        verify_channel_archive(path, 'model')
