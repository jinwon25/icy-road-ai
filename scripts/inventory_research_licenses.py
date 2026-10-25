"""실제 설치 연구 라이브러리의 버전·배포 고지·해시를 비공개 검토 폴더에 보존한다."""
from importlib.metadata import distribution
import json
from pathlib import Path
import hashlib

ROOT=Path(__file__).resolve().parents[1]
PACKAGES=['scikit-learn','catboost','lightgbm','xgboost','torch','numpy','pandas','joblib','scipy','threadpoolctl']


def main():
    out=ROOT/'outputs/private/research_license_inventory_20261024_v1'
    if out.exists():raise FileExistsError('Preserve license inventory')
    out.mkdir();records=[]
    for name in PACKAGES:
        dist=distribution(name);folder=out/name;folder.mkdir()
        # 라이선스 파일만 복사한다. 패키지 코드·모델·사용자 설정은 복사하지 않는다.
        files=[f for f in (dist.files or []) if Path(str(f)).name.lower() in ['license','license.txt','license.md','copying','notice','notice.txt']]
        saved=[]
        for i,file in enumerate(files):
            data=Path(dist.locate_file(file)).read_bytes();dest=folder/(str(i)+'_'+Path(str(file)).name)
            dest.write_bytes(data);saved.append(dict(installed_relative_path=str(file),saved_file=str(dest.relative_to(out)),
                sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
        license_text=dist.metadata.get('License-Expression') or dist.metadata.get('License') or ''
        (folder/'license_metadata.txt').write_text(license_text+'\n','utf-8')
        records.append(dict(package=name,version=dist.version,license_metadata_file=str((folder/'license_metadata.txt').relative_to(out)),
            license_files=saved,full_notice_file_found=bool(saved),
            redistribution_review='최종 묶음의 실제 배포 범위에 따라 고지 포함. 의존성 설치와 코드 재배포를 구분.'))
    report=dict(status='installed_metadata_and_license_files_inventoried',records=records,external_weights_used=False,
        upstream_files_with_no_full_license=[r['package'] for r in records if not r['full_notice_file_found']])
    (out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({r['package']:dict(version=r['version'],license_files=len(r['license_files'])) for r in records},ensure_ascii=False))

if __name__=='__main__':main()
