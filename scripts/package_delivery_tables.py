"""기존 후보와 검증한 CSV를 새 ZIP에 통합한다. 기존 ZIP과 산출물을 덮어쓰지 않는다."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.submission_archive import verify_archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, type=Path)
    parser.add_argument('--tables', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix('.receipt.json').exists():
        raise FileExistsError('Preserve completed package')
    old = verify_archive(args.base)
    audit = json.loads((args.tables/'manifest.json').read_text('utf-8'))
    if audit['status'] != 'delivery_tables_verified':
        raise ValueError('Completed table export required')
    if audit['generator_sha256'] != sha(ROOT/'scripts/export_delivery_tables.py') or audit['aggregation_module_sha256'] != sha(ROOT/'src/delivery_tables.py'):
        raise ValueError('Export implementation changed after completed audit')
    with zipfile.ZipFile(args.base) as base:
        if hashlib.sha256(base.read('manifest.json')).hexdigest() != audit['candidate_manifest_sha256']:
            raise ValueError('Exported tables belong to a different base candidate')
    for name, expected in audit['sources'].items():
        if old['files'][name] != expected:
            raise ValueError('Export source manifest mismatch')
    new = {}
    for entry in audit['tables']:
        path = args.tables/entry['file']
        if sha(path) != entry['sha256'] or path.stat().st_size != entry['bytes']:
            raise ValueError('CSV export modified after verification')
        new['exports/'+entry['file']] = path
    new['exports/manifest.json'] = args.tables/'manifest.json'
    updated = ['src/delivery_tables.py', 'scripts/export_delivery_tables.py', 'scripts/package_delivery_tables.py',
        'tests/test_delivery_tables.py', 'docs/delivery/CSV_CONTRACT.md',
        'docs/delivery/DELIVERY_UPGRADE_20261024.md', 'docs/research/DELIVERY_REFERENCES_20261024.md',
        'docs/STATUS.md', 'docs/README.md', 'AI_USAGE.md', 'scripts/README.md']
    for name in updated:
        new[name] = ROOT/name
    new['validation/unit_tests_20261024.log'] = ROOT/'outputs/private/unit_tests_20261024.log'
    for path in new.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    files = dict(old['files'])
    for name, path in new.items():
        files[name] = dict(sha256=sha(path), bytes=path.stat().st_size)
    with zipfile.ZipFile(args.base) as base:
        readme = ('''# 2026년 10월 24일 CSV 보강 후보

검토 시작: docs/delivery/DELIVERY_UPGRADE_20261024.md
CSV 열·단위·키·결측·집계: docs/delivery/CSV_CONTRACT.md
산출물: exports/manifest.json 및 exports/*.csv, exports/prediction_groups_10min.csv.gz

보호 3곳 103,680행, 500m 843개·1km 423개 구간 두 겨울의 추정을 일반 CSV로 제공합니다.
구간별 10분 예측은 point_prediction_index.csv와 prediction_groups_10min.csv.gz를
prediction_group·winter로 결합해 복원합니다. 공유 그룹을 독립 검증 표본으로 세지 않습니다.
보호 정답은 없으며 입력 부족 18행은 NA입니다. 개발 지표는 공식 점수가 아닙니다.

모델·기존 예측·기존 16쪽 보고서·데모는 이전 후보와 같습니다.
성능 적합 판정은 보류합니다. 결과물 접수 마감과 최신 데모 답변 본문은 미확인입니다.
11월 6일은 확인한 참가신청 종료일입니다. 대회 제출·외부 공개는 수행하지 않았습니다.

기존 실행 안내와 제출용 노트북은 아래 내용을 따릅니다.

'''+base.read('README.md').decode('utf-8')).encode('utf-8')
        files['README.md'] = dict(sha256=hashlib.sha256(readme).hexdigest(), bytes=len(readme))
        manifest = dict(version=5, status='private_candidate_performance_not_qualified',
            created_at_utc=datetime.now(timezone.utc).isoformat(), files=files)
        with zipfile.ZipFile(args.output, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as target:
            for name in old['files']:
                if name in new or name == 'README.md':
                    continue
                with base.open(name) as source, target.open(name, 'w') as dest:
                    shutil.copyfileobj(source, dest)
            for name, path in new.items():
                target.write(path, name)
            target.writestr('README.md', readme)
            target.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    verified = verify_archive(args.output)
    immutable = [n for n in old['files'] if n.startswith(('data/','model/','research/','figures/','demo/','reports/current/'))]
    assert all(old['files'][n] == verified['files'][n] for n in immutable)
    receipt = dict(status='delivery_upgrade_packaged', archive_sha256=sha(args.output),
        archive_bytes=args.output.stat().st_size, verified_files=len(verified['files']),
        preserved_core_files=len(immutable), source_archive_sha256=sha(args.base),
        exported_csv_tables=len(audit['tables']), competition_submitted=False, model_promoted=False)
    args.output.with_suffix('.receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
