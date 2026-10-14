"""공식 사실·로컬 추론·작은 묶음·봉인·전체 코드/문서를 최종 검증한다."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.fresh_station_validation import old_freezes, verify_seal

OUT = ROOT / 'outputs/private/official_updates_quality_20261013_v1'
REFS = ROOT / 'outputs/private/official_updates_20261013_v1'


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


def main():
    if OUT.exists():
        raise FileExistsError('Preserve prior quality receipt')
    OUT.mkdir(); checks = []
    commands = [[sys.executable, '-X', 'utf8', '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                [sys.executable, '-X', 'utf8', 'scripts/check_repository.py', '--include-untracked'],
                [sys.executable, '-X', 'utf8', 'scripts/check_markdown.py', '--include-untracked', '--render-dir', str(OUT / 'rendered')]]
    for name, command in zip(['tests', 'repository', 'markdown'], commands):
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log = OUT / (name+'.log'); log.write_bytes(result.stdout); checks.append(dict(name=name, returncode=result.returncode, log_sha256=sha(log)))
        print(name, result.returncode, result.stdout.decode('utf-8', errors='replace').splitlines()[-4:], flush=True)
        if result.returncode:
            raise RuntimeError('Quality check failed; preserve failed log')
    fetches = read(REFS / 'fetch_receipts.json'); assert len(fetches) == 27 and all(r['status'] == 200 for r in fetches)
    for r in fetches:
        assert sha(REFS / r['file']) == r['sha256']
    evidence = read(REFS / 'change_comparison.json'); answers = read(REFS / 'answer_comparison.json')
    assert all(t['exact_content_equal'] for t in evidence['tabs']) and not evidence['application_bytes_equal']
    assert all(r['normalized_bodies_equal'] for r in answers['problem_questions'].values()) and not answers['problem_questions']['633']['official_answer_present']
    for r in answers['problem_questions'].values():
        assert sha(ROOT / r['old_path']) == r['old_sha256']
    config = read(ROOT / 'config/official_requirements_20261013.json')
    assert config['result_submission']['opening_date'] is None and config['result_submission']['deadline_date'] is None
    assert config['result_submission']['deadline_time_if_announced'] == '23:59' and not config['application_deadline_is_result_deadline']
    assert config['application']['current_sha256'] == sha(REFS / 'current_application.hwp')
    for source in config['sources'].values():
        r = next(r for r in fetches if r['url'] == source['url']); assert source['response_sha256'] == r['sha256']
    inference = ROOT / 'outputs/private/offline_inference_20261013_v1'; receipt = read(inference / 'verification_receipt.json')
    assert receipt['status'] == 'offline_inference_replay_passed' and receipt['network_attempts'] == 0 and receipt['external_prediction_api_calls'] == 0
    assert receipt['rows'] == 144 and receipt['verified_prediction_values'] == 1008 and receipt['local_models_loaded'] == 4 and receipt['new_model_fits'] == 0
    for rel, digest in receipt['input_signatures'].items():
        assert sha(ROOT / rel) == digest, rel
    assert sha(inference / 'development_day_inference.parquet') == receipt['result_sha256']
    bundle = ROOT / 'outputs/private/offline_review_bundle_20261013_v1'; manifest = read(bundle / 'bundle_manifest.json'); verification = read(bundle / 'verification.json')
    assert verification['status'] == 'private_bundle_replay_passed' and verification['returncode'] == 0 and not verification['submitted']
    assert sha(bundle / 'bundle_manifest.json') == verification['manifest_sha256'] and sha(bundle / 'replay.log') == verification['replay_log_sha256']
    for name, digest in manifest['files'].items():
        assert sha(bundle / name) == digest, name
    for rel, digest in manifest['input_signatures'].items():
        assert sha(ROOT / rel) == digest, rel
    assert len(manifest['files']) == 11 and not manifest['external_prediction_api_required'] and not manifest['final_submission_model']
    for name in ['weather_day', 'classifier_day', 'reference_predictions']:
        frame = pd.read_parquet(bundle / 'data' / (name+'.parquet'))
        assert len(frame) == 144 and set(frame.station) == {'12207'}
        assert not {'ice', 'state_raw', 'road_temp', 'observed_road_temp'}.intersection(frame.columns)
    freezes = old_freezes()
    for name in ['fresh_station_validation_20261009_v2', 'temperature_blind_20261010_v1', 'temperature_mean_blind_20261010_v1']:
        verify_seal(ROOT / 'outputs/private' / name)
    names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT).decode('utf-8').split('\0')
    receipt = dict(status='official_update_and_offline_review_complete', checked_at_utc=datetime.now(timezone.utc).isoformat(), checked_date_kst='2026-10-13', checks=checks,
                   public_responses_verified=27, current_application_sha256=sha(REFS / 'current_application.hwp'), requirements_sha256=sha(ROOT / 'config/official_requirements_20261013.json'),
                   inference_receipt_sha256=sha(inference / 'verification_receipt.json'), bundle_verification_sha256=sha(bundle / 'verification.json'),
                   source_file_hashes={name: sha(ROOT / name) for name in names if name and (ROOT / name).is_file()},
                   reference_file_hashes={p.name: sha(p) for p in REFS.iterdir() if p.is_file()}, old_frozen_files=freezes[0], reserved_frozen_files=freezes[1],
                   assessment_outcomes_read_for_new_work=False, model_promoted=False, account_login_performed=False, external_message_sent=False, competition_submission_made=False)
    (OUT / 'completion_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8'); print('공식 확인 완료', len(receipt['source_file_hashes']), '소스 파일')


if __name__ == '__main__':
    main()
