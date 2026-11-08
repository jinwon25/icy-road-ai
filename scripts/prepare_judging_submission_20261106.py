"""보존한 제출본을 바탕으로 심사 근거 보강용 작업 사본을 만든다."""
from pathlib import Path
import shutil,json
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'outputs/private';W=P/'judging_upgrade_20261106'
source=P/'competition_submission'
assert not (W/'icy_road_model').exists()
for name in ['icy_road_model','icy_road_documents']:
    shutil.copytree(source/name,W/name,ignore=shutil.ignore_patterns('__pycache__','local_review'))
for name in ['submission_receipt.json','README.md']:
    shutil.copyfile(source/name,W/('original_'+name))
for name in ['icy_road_model','icy_road_documents']:
    p=W/name/'manifest.json';target=W/('original_'+name+'_manifest.json')
    assert p.resolve().is_relative_to(W.resolve()) and target.resolve().is_relative_to(W.resolve())
    p.replace(target)
print('심사 근거 보강용 작업 사본 준비 완료')
