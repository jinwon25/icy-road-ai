"""검증된 두 제출 묶음을 교체하고 이전 원본 폴더는 별도로 보존한다."""
from pathlib import Path
from datetime import datetime,timezone
import sys,shutil,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import read,write,sha
from scripts.review_submission_bundle import verify_directory
P=(ROOT/'outputs/private').resolve();W=P/'precision_submission_update_20261106'
CURRENT=P/'competition_submission';BACKUP=P/'competition_submission_before_error_analysis_20261106';STAGE=W/'release'

def main():
    assert not BACKUP.exists() and not STAGE.exists()
    for path in [CURRENT,BACKUP,STAGE]:
        assert path.resolve().is_relative_to(P),path
    old=read(W/'original_submission_receipt.json');new=read(W/'submission_receipt.json')
    for name in ['documents','model']:
        assert sha(CURRENT/('icy_road_'+name+'.zip'))==old['archives'][name]['sha256']
        assert sha(W/('icy_road_'+name+'.zip'))==new['archives'][name]['sha256']
    assert new['checks']['core_model_and_training_data_unchanged']
    assert new['checks']['numerical_predictions_unchanged']
    STAGE.mkdir()
    for name in ['icy_road_model','icy_road_documents']:
        shutil.copytree(W/name,STAGE/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','local_review'))
        verify_directory(STAGE/name)
    for name in ['icy_road_documents.zip','icy_road_model.zip','submission_receipt.json']:
        shutil.copyfile(W/name,STAGE/name)
    shutil.copyfile(CURRENT/'README.md',STAGE/'README.md')
    # 절대 경로와 비어 있는 보존 경로를 확인한 같은 파일시스템 안의 가역적 이름 변경.
    assert CURRENT.resolve().parent==P and BACKUP.resolve().parent==P
    CURRENT.rename(BACKUP)
    try:
        STAGE.rename(CURRENT)
    except BaseException:
        BACKUP.rename(CURRENT)
        raise
    for name in ['documents','model']:
        assert sha(CURRENT/('icy_road_'+name+'.zip'))==new['archives'][name]['sha256']
        assert sha(BACKUP/('icy_road_'+name+'.zip'))==old['archives'][name]['sha256']
    for name in ['icy_road_model','icy_road_documents']:verify_directory(CURRENT/name)
    write(W/'installed_receipt.json',dict(status='installed_and_verified',at_utc=datetime.now(timezone.utc).isoformat(),
        current=CURRENT.relative_to(ROOT).as_posix(),previous_preserved=BACKUP.relative_to(ROOT).as_posix(),
        archives=new['archives'],report_pages=9,core_model_and_training_data_unchanged=True,
        numerical_predictions_unchanged=True,competition_submitted=False))
    print('INSTALLED',CURRENT,'previous preserved:',BACKUP,flush=True)

if __name__=='__main__':main()
