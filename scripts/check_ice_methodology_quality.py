"""새 방법론의 실험·감사·봉인·테스트·로컬 GFM을 최종 확인한다."""
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import sys

import catboost
import numpy
import pandas
import sklearn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.fresh_station_validation import old_freezes, verify_seal

OUT = ROOT / 'outputs/private/ice_methodology_quality_checks_20261010_v1'


def main():
    if OUT.exists():
        raise FileExistsError('Preserve earlier quality receipt')
    OUT.mkdir(); checks = []
    commands = [[sys.executable, '-X', 'utf8', '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                [sys.executable, '-X', 'utf8', 'scripts/check_repository.py', '--include-untracked'],
                [sys.executable, '-X', 'utf8', 'scripts/check_markdown.py', '--include-untracked', '--render-dir', str(OUT / 'rendered')]]
    for name, command in zip(['tests', 'repository', 'markdown'], commands):
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log = OUT / (name+'.log'); log.write_bytes(result.stdout)
        checks.append(dict(name=name, returncode=result.returncode, log_sha256=sha(log)))
        print(name, result.returncode, result.stdout.decode('utf-8', errors='replace').splitlines()[-4:], flush=True)
        if result.returncode:
            raise RuntimeError('Quality check failed; preserve failed log')
    experiment = ROOT / 'outputs/private/ice_methodology_20261010_v1'
    summary = json.loads((experiment / 'summary.json').read_text('utf-8')); audit = json.loads((experiment / 'independent_verification.json').read_text('utf-8'))
    assert audit['status'] == 'independent_ice_methodology_audit_passed' and audit['summary_sha256'] == sha(experiment / 'summary.json')
    for rel, digest in summary['files'].items():
        assert sha(experiment / rel) == digest, rel
    for rel, digest in json.loads((experiment / 'input_signatures.json').read_text('utf-8')).items():
        assert sha(ROOT / rel) == digest, rel
    interval_folder = ROOT / 'outputs/private/temperature_uncertainty_20261010_v1'
    interval_summary = json.loads((interval_folder / 'summary.json').read_text('utf-8')); interval_audit = json.loads((interval_folder / 'independent_verification.json').read_text('utf-8'))
    assert interval_audit['status'] == 'independent_temperature_range_audit_passed' and interval_audit['summary_sha256'] == sha(interval_folder / 'summary.json')
    for rel, digest in interval_summary['files'].items():
        assert sha(interval_folder / rel) == digest, rel
    for rel, digest in json.loads((interval_folder / 'input_signatures.json').read_text('utf-8')).items():
        assert sha(ROOT / rel) == digest, rel
    freeze = old_freezes()
    for name in ['fresh_station_validation_20261009_v2', 'temperature_blind_20261010_v1', 'temperature_mean_blind_20261010_v1']:
        verify_seal(ROOT / 'outputs/private' / name)
    paths = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT).decode('utf-8').split('\0')
    sources = {name: sha(ROOT / name) for name in paths if name and (ROOT / name).is_file()}
    refs = ROOT / 'outputs/private/ice_methodology_references_20261010_v1'
    interval_refs = ROOT / 'outputs/private/temperature_uncertainty_references_20261010_v1'
    result = dict(status='completed_ice_methodology_review', checked_at_utc=datetime.now(timezone.utc).isoformat(), checks=checks,
                  experiment_summary_sha256=sha(experiment / 'summary.json'), experiment_audit_sha256=sha(experiment / 'independent_verification.json'),
                  source_file_hashes=sources, reference_file_hashes={p.name: sha(p) for p in refs.iterdir() if p.is_file()},
                  interval_summary_sha256=sha(interval_folder / 'summary.json'), interval_audit_sha256=sha(interval_folder / 'independent_verification.json'),
                  interval_reference_file_hashes={p.name: sha(p) for p in interval_refs.iterdir() if p.is_file()},
                  old_frozen_files=freeze[0], reserved_frozen_files=freeze[1],
                  runtime=dict(python=platform.python_version(), sklearn=sklearn.__version__, catboost=catboost.__version__, numpy=numpy.__version__, pandas=pandas.__version__),
                  assessment_outcomes_used_for_new_candidates=False, new_independent_assessment=False, model_promoted=False, competition_submission_made=False)
    (OUT / 'completion_receipt.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('방법론 검증 완료', len(sources), '소스 파일')


if __name__ == '__main__':
    main()
