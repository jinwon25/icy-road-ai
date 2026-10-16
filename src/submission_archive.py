"""해시 목록을 검증한 제출 ZIP을 새 폴더로 복원한다."""
import hashlib
import argparse
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile


def safe_name(name):
    p=PurePosixPath(name)
    if not p.parts or '\\' in name or ':' in name or p.is_absolute() or '..' in p.parts or name!=p.as_posix():
        raise ValueError('Unsafe archive member path')
    return name


def verify_archive(archive):
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist(); names=[i.filename for i in infos]
        if len(names)!=len(set(names)):
            raise ValueError('Duplicate archive member')
        for item in infos:
            safe_name(item.filename)
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('Archive symlink is forbidden')
        manifest_name='manifest.json' if 'manifest.json' in names else 'candidate_manifest.json'
        manifest=json.loads(z.read(manifest_name)); files=manifest['files']
        if set(names)!=set(files)|{manifest_name}:
            raise ValueError('Archive membership differs from manifest')
        for name, record in files.items():
            safe_name(name)
            with z.open(name) as source:
                digest=hashlib.file_digest(source,'sha256').hexdigest()
            if digest!=record['sha256'] or z.getinfo(name).file_size!=record['bytes']:
                raise ValueError('Archive hash or size mismatch: '+name)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--sha256')
    args=parser.parse_args()
    manifest=restore_archive(args.archive,args.output,args.sha256)
    print(json.dumps({'status':'verified_archive_restored','files':len(manifest['files']),'output':str(args.output)}))


def restore_archive(archive, destination, expected_sha256=None):
    archive, destination=Path(archive), Path(destination)
    if destination.exists():
        raise FileExistsError('Existing restored package is preserved')
    if expected_sha256:
        with archive.open('rb') as source:
            if hashlib.file_digest(source,'sha256').hexdigest()!=expected_sha256:
                raise ValueError('Base archive SHA-256 mismatch')
    manifest=verify_archive(archive)
    destination.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            target=destination/safe_name(name)
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError('Archive member escapes destination')
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(name) as source, target.open('xb') as output:
                shutil.copyfileobj(source,output)
    return manifest


if __name__=='__main__': main()
