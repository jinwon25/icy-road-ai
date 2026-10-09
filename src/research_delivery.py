"""비공개 연구 인계물의 해시·경로·개발 및 새 지점 경계를 검증한다."""
from pathlib import Path
import hashlib
import json


PROTECTED = {'12410', '33411', '23402'}


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify_delivery(folder):
    root = Path(folder).resolve()
    manifest = json.loads((root / 'manifest.json').read_text('utf-8'))
    if manifest['scope'] != 'private_research_handoff_not_final_competition_submission':
        raise ValueError('Unsupported delivery scope')
    for name, checksum in manifest['files'].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Missing or unsafe manifest path')
        if file_sha(path) != checksum:
            raise ValueError('Changed delivery file: ' + name)
    return manifest


def verify_cohort(training, query, groups):
    train_ids = set(training.station)
    expected = {s for stations in groups.values() for s in stations}
    if len(train_ids) != 23 or len(expected) != 8 or set(query.station) != expected:
        raise ValueError('Unexpected research cohort')
    if (train_ids & expected) or ((train_ids | expected) & PROTECTED):
        raise ValueError('Overlapping or protected stations')
    for frame in (training, query):
        if frame.duplicated(['station', 'time']).any():
            raise ValueError('Duplicate station-time keys')
        if not (frame.time.ge('2024-11-01') & frame.time.lt('2025-03-01')).all():
            raise ValueError('Only first-winter research data allowed')
