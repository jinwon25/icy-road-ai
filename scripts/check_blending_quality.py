"""블렌딩 완료본·봉인·Python 종료 코드·저장소·GFM을 최종 검증한다."""
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import sys

import matplotlib
import numpy
import pandas
import scipy
import sklearn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.fresh_station_validation import old_freezes, verify_seal

OUT = ROOT / 'outputs/private/method_blending_quality_checks_20261010_v1'


def main():
    if OUT.exists():
        raise FileExistsError('Preserve previous quality receipt')
    OUT.mkdir()
    checks = []
    commands = [[sys.executable, '-X', 'utf8', '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                [sys.executable, '-X', 'utf8', 'scripts/check_repository.py', '--include-untracked'],
                [sys.executable, '-X', 'utf8', 'scripts/check_markdown.py', '--include-untracked', '--render-dir', str(OUT / 'rendered')]]
    for name, command in zip(['tests', 'repository', 'markdown'], commands):
        # unittest의 stderr를 PowerShell 오류로 바꾸지 않고 Python returncode를 보존한다.
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log = OUT / (name+'.log'); log.write_bytes(result.stdout)
        checks.append({'name': name, 'returncode': result.returncode, 'log_sha256': sha(log)})
        print(name, result.returncode, result.stdout.decode('utf-8', errors='replace').splitlines()[-4:], flush=True)
        if result.returncode:
            raise RuntimeError('Quality check failed; preserve log and use new receipt version')
    evidence = {}
    for name in ['method_blending_20261010_v2', 'score_blending_20261010_v2', 'temperature_pair_blending_20261010_v1']:
        folder = ROOT / 'outputs/private' / name
        summary = json.loads((folder / 'summary.json').read_text('utf-8'))
        audit = json.loads((folder / 'independent_verification.json').read_text('utf-8'))
        assert audit['summary_sha256'] == sha(folder / 'summary.json') and audit['status'].endswith('_audit_passed')
        for rel, digest in summary['files'].items():
            assert sha(folder / rel) == digest, rel
        for rel, digest in json.loads((folder / 'input_signatures.json').read_text('utf-8')).items():
            assert sha(ROOT / rel) == digest, rel
        evidence[name] = {'summary_sha256': sha(folder / 'summary.json'), 'audit_sha256': sha(folder / 'independent_verification.json'), 'files_verified': len(summary['files'])}
    freezes = old_freezes()
    for name in ['fresh_station_validation_20261009_v2', 'temperature_blind_20261010_v1', 'temperature_mean_blind_20261010_v1']:
        verify_seal(ROOT / 'outputs/private' / name)
    paths = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT).decode('utf-8').split('\0')
    source_hashes = {name: sha(ROOT / name) for name in paths if name and (ROOT / name).is_file()}
    refs = ROOT / 'outputs/private/method_blending_references_20261010_v1'
    reference_hashes = {p.name: sha(p) for p in refs.iterdir() if p.is_file()}
    result = {'status': 'completed_development_blending_review', 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'checks': checks, 'evidence': evidence, 'old_frozen_files': freezes[0], 'reserved_frozen_files': freezes[1],
              'source_file_hashes': source_hashes, 'reference_file_hashes': reference_hashes,
              'runtime': {'python': platform.python_version(), 'numpy': numpy.__version__, 'pandas': pandas.__version__,
                          'scipy': scipy.__version__, 'sklearn': sklearn.__version__, 'matplotlib': matplotlib.__version__},
              'assessment_outcomes_used_for_new_candidates': False, 'new_independent_assessment': False,
              'model_promoted': False, 'competition_submission_made': False}
    with (OUT / 'completion_receipt.json').open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print('블렌딩 검증 완료:', len(source_hashes), '소스 파일, 출처 파일', len(reference_hashes))


if __name__ == '__main__':
    main()
