"""기상 이력 후속 결과·별도 검산·봉인·테스트·문서의 완료 기록을 남긴다."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import read, write, preservation

OUT = ROOT / 'outputs/private/weather_memory_quality_20261013_v2'
STUDY = ROOT / 'outputs/private/weather_memory_temperature_20261013_v2'
REFS = ROOT / 'outputs/private/weather_memory_references_20261013_v1'


def main():
    if OUT.exists(): raise FileExistsError('Preserve quality receipts')
    OUT.mkdir(); checks = []
    commands = [[sys.executable, '-X', 'utf8', '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                [sys.executable, '-X', 'utf8', 'scripts/check_repository.py', '--include-untracked'],
                [sys.executable, '-X', 'utf8', 'scripts/check_markdown.py', '--include-untracked', '--render-dir', str(OUT / 'rendered')]]
    for name, command in zip(['tests', 'repository', 'markdown'], commands):
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log = OUT / (name+'.log'); log.write_bytes(result.stdout)
        checks.append(dict(name=name, returncode=result.returncode, log_sha256=sha(log)))
        print(name, result.returncode, result.stdout.decode('utf-8', errors='replace').splitlines()[-4:], flush=True)
        if result.returncode: raise RuntimeError('Preserve failed quality log')
    summary, audit = read(STUDY / 'summary.json'), read(STUDY / 'independent_verification.json')
    assert audit['status'] == 'independent_weather_memory_temperature_audit_passed' and audit['summary_sha256'] == sha(STUDY / 'summary.json')
    assert audit['audit_source_sha256'] == sha(ROOT / 'scripts/audit_weather_memory_temperature_stable.py')
    for rel, digest in summary['files'].items(): assert sha(STUDY / rel) == digest, rel
    for rel, digest in read(STUDY / 'input_signatures.json').items(): assert sha(ROOT / rel) == digest, rel
    fetches = read(REFS / 'fetch_receipts.json')
    for r in fetches: assert sha(REFS / r['file']) == r['sha256']
    previous = ROOT / 'outputs/private/weather_memory_temperature_20261013_v1'
    prior_summary, prior_audit = read(previous / 'summary.json'), read(previous / 'independent_verification.json')
    assert prior_audit['summary_sha256'] == sha(previous / 'summary.json')
    for rel, digest in prior_summary['files'].items(): assert sha(previous / rel) == digest, rel
    for rel, digest in read(previous / 'input_signatures.json').items(): assert sha(ROOT / rel) == digest, rel
    failed = ROOT / 'outputs/private/weather_memory_offline_bundle_20261013_v1'
    for rel, digest in read(failed / 'bundle_manifest.json')['files'].items(): assert sha(failed / rel) == digest, rel
    assert 'Mismatched elements: 2 / 144' in (failed / 'replay.log').read_text('utf-8')
    bundle = ROOT / 'outputs/private/weather_memory_offline_bundle_20261013_v2'
    verification, manifest = read(bundle / 'verification.json'), read(bundle / 'bundle_manifest.json')
    assert verification['status'] == 'weather_memory_private_bundle_verified' and verification['returncode'] == 0 and not verification['submitted']
    assert verification['manifest_sha256'] == sha(bundle / 'bundle_manifest.json') and verification['replay_log_sha256'] == sha(bundle / 'replay.log')
    for rel, digest in manifest['files'].items(): assert sha(bundle / rel) == digest, rel
    for rel, digest in manifest['input_signatures'].items(): assert sha(ROOT / rel) == digest, rel
    replay = json.loads((bundle / 'replay.log').read_text('utf-8'))
    assert replay['feature_values_verified'] == 6048 and replay['prediction_values_verified'] == 1296 and replay['network_attempts'] == 0
    event_path = ROOT / 'outputs/private/weather_memory_event_review_20261013_v1/review.json'
    event_review = read(event_path)
    assert event_review['status'] == 'event_identity_review_verified' and event_review['event_tables_independently_reconstructed'] == 6
    for rel, digest in event_review['input_signatures'].items(): assert sha(ROOT / rel) == digest, rel
    assert event_review['comparisons']['equal_trio_memory']['lost_events'] == 1
    controls = ROOT / 'outputs/private/weather_memory_controls_20261013_v1'
    cs, ca = read(controls / 'summary.json'), read(controls / 'independent_verification.json')
    assert ca['status'] == 'independent_same_parameter_memory_controls_audit_passed' and ca['summary_sha256'] == sha(controls / 'summary.json')
    assert ca['audit_source_sha256'] == sha(ROOT / 'scripts/audit_weather_memory_controls.py')
    for rel, digest in cs['files'].items(): assert sha(controls / rel) == digest, rel
    for rel, digest in read(controls / 'input_signatures.json').items(): assert sha(ROOT / rel) == digest, rel
    tradeoff_path = ROOT / 'outputs/private/weather_memory_tradeoffs_20261013_v1/review.json'
    tradeoffs = read(tradeoff_path)
    assert tradeoffs['comparisons']['equal_nohistory_pair']['combined_eligible'] and tradeoffs['comparisons']['equal_trio_nohistory']['combined_eligible']
    for rel, digest in tradeoffs['input_signatures'].items(): assert sha(ROOT / rel) == digest, rel
    control_bundle = ROOT / 'outputs/private/weather_control_offline_bundle_20261013_v1'
    bv, bm = read(control_bundle / 'verification.json'), read(control_bundle / 'bundle_manifest.json')
    assert bv['status'] == 'weather_control_private_bundle_verified' and bv['returncode'] == 0 and not bv['submitted']
    assert bv['manifest_sha256'] == sha(control_bundle / 'bundle_manifest.json') and bv['replay_log_sha256'] == sha(control_bundle / 'replay.log')
    for rel, digest in bm['files'].items(): assert sha(control_bundle / rel) == digest, rel
    for rel, digest in bm['input_signatures'].items(): assert sha(ROOT / rel) == digest, rel
    cr = json.loads((control_bundle / 'replay.log').read_text('utf-8'))
    assert cr['models_loaded'] == 2 and cr['prediction_values_verified'] == 576 and cr['network_attempts'] == 0
    freezes = preservation()
    names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT).decode('utf-8').split('\0')
    result = dict(status='weather_memory_temperature_review_complete', checked_at_utc=datetime.now(timezone.utc).isoformat(), checks=checks,
                  summary_sha256=sha(STUDY / 'summary.json'), audit_sha256=sha(STUDY / 'independent_verification.json'),
                  source_file_hashes={n: sha(ROOT / n) for n in names if n and (ROOT / n).is_file()},
                  reference_file_hashes={p.name: sha(p) for p in REFS.iterdir() if p.is_file()},
                  public_sources=len(fetches), successful_public_responses=sum(r.get('status') == 200 for r in fetches),
                  new_model_fits=60, raw_v1_preserved=True, failed_v1_bundle_preserved=True, audit_refits=6,
                  stable_bundle_verification_sha256=sha(bundle / 'verification.json'),
                  event_identity_review_sha256=sha(event_path),
                  control_summary_sha256=sha(controls / 'summary.json'), control_audit_sha256=sha(controls / 'independent_verification.json'),
                  tradeoff_review_sha256=sha(tradeoff_path), control_bundle_verification_sha256=sha(control_bundle / 'verification.json'),
                  assessment_outcomes_read=False, new_independent_assessment=False,
                  model_promoted=False, competition_submission_made=False, old_frozen_files=freezes[0], reserved_frozen_files=freezes[1])
    write(OUT / 'completion_receipt.json', result); print('완료 소스 파일:', len(result['source_file_hashes']))


if __name__ == '__main__': main()
