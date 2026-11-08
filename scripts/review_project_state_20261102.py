"""기존 v12 폴더·두 ZIP의 현재 바이트와 완료 연구의 영수증을 읽기 전용 검증한다."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_objective_icing import read, write, now, verify_preserved
from scripts.review_submission_bundle import verify_directory
from scripts.package_submission_channels import verify_channel_archive
from src.data_source import sha256_file as sha


def main():
    out = ROOT/'outputs/private/project_review_20261102_v1'
    if out.exists(): raise FileExistsError('Preserve completed project review')
    private = ROOT/'outputs/private'
    channels = private/'submission_channels_20261101_v12'
    receipt = read(channels/'submission_receipt.json')
    assert receipt['status'] == 'two_channel_archives_verified'
    folder = verify_directory(ROOT/receipt['model_source'])
    checked = {}
    for channel, name in [('documents', 'icy_road_documents.zip'), ('model', 'icy_road_model.zip')]:
        expected = receipt['archives'][channel]; path = channels/name
        assert sha(path) == expected['sha256'] and path.stat().st_size == expected['bytes']
        actual = verify_channel_archive(path, expected['root'])
        assert actual['files'] == expected['files']
        checked[channel] = dict(actual, sha256=sha(path), bytes=path.stat().st_size)
    studies = {}
    for name in ['weather_network_20261101_v1', 'weather_humidity_stable_20261101_v1']:
        path = private/name
        proof = read(path/'independent_verification.json')
        assert proof['status'] == 'passed' and proof['summary_sha256'] == sha(path/'summary.json')
        studies[name] = dict(status=proof['status'], summary_sha256=sha(path/'summary.json'))
    preservation = verify_preserved()
    out.mkdir()
    write(out/'receipt.json', dict(status='project_state_verified', at_utc=now(), folder=folder,
        archives=checked, audited_research=studies, preservation=preservation,
        source_receipt_sha256=sha(channels/'submission_receipt.json'),
        code_signatures={p.relative_to(ROOT).as_posix(): sha(p) for p in [Path(__file__),
            ROOT/'scripts/review_submission_bundle.py', ROOT/'scripts/package_submission_channels.py']},
        existing_outputs_modified=False, protected_outcomes_read=False, competition_submitted=False))
    print('PROJECT VERIFIED', folder['files'], 'folder files,',
          sum(c['files'] for c in checked.values()), 'archived files', flush=True)


if __name__ == '__main__':
    main()
