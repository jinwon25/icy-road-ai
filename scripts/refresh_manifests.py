"""수정본의 소스·유효 산출물 해시와 무효화 기록을 별도로 갱신한다."""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file


def main():
    for name in ('workspace_manifest', 'artifact_manifest'):
        original = ROOT / f'{name}.json'; backup = ROOT / f'{name}_before_final_assessment_20261008.json'
        if original.exists() and not backup.exists(): shutil.copy2(original, backup)
    workspace = json.loads((ROOT / 'workspace_manifest.json').read_text(encoding='utf-8'))
    workspace['source_files'] = {p.relative_to(ROOT).as_posix(): sha256_file(p) for directory in ('src', 'scripts', 'config', 'tests', 'notebooks', 'docs') for p in (ROOT / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    for name in ('README.md', 'AI_USAGE.md', 'requirements.txt'): workspace['source_files'][name] = sha256_file(ROOT / name)
    workspace['status'] = 'development_and_frozen_assessment_preserved'
    (ROOT / 'workspace_manifest.json').write_text(json.dumps(workspace, ensure_ascii=False, indent=2), encoding='utf-8')
    private = ROOT / 'outputs/private'; artifacts = {}; invalidated = []
    for child in private.iterdir():
        if child.name.startswith(('submission_', 'package_')): continue
        if child.name.startswith('invalid_route_'):
            note = child / 'INVALIDATED.json'
            invalidated.append({'path': child.relative_to(ROOT).as_posix(), 'usable': False,
                                'reason_record': json.loads(note.read_text(encoding='utf-8')) if note.exists() else 'Route reference mapping invalidated'})
            continue
        for p in child.rglob('*') if child.is_dir() else [child]:
            if p.is_file() and '__pycache__' not in p.parts: artifacts[p.relative_to(ROOT).as_posix()] = sha256_file(p)
    (ROOT / 'artifact_manifest.json').write_text(json.dumps(artifacts, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'invalidated_artifacts.json').write_text(json.dumps(invalidated, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'source_files': len(workspace['source_files']), 'usable_artifacts': len(artifacts), 'invalidated_directories': len(invalidated)}), flush=True)


if __name__ == '__main__': main()
