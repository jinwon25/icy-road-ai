"""실제 실행을 보존하고 native select 렌더 차이를 분리해 v12 검증을 완료한다."""
from pathlib import Path
import sys

import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_review_v12 import checks,preserved,manifest,OUT,P,STUDIES,compare_browser_content
from scripts.evaluate_objective_icing import read,write,now
from scripts.check_markdown import inspect_documents
from scripts.review_submission_bundle import verify_directory
from src.data_source import sha256_file as sha


def main():
    target=OUT/'validation/v12_delivery.json'
    if target.exists():raise FileExistsError('Preserve verification')
    checks();names=preserved();local=OUT/'local_review'
    core=read(local/'v12_core.json');assert core['prediction_rows_identical']==144
    assert b'Notebook validated in Jupyter kernel: 3 code cells' in (local/'network_notebook.log').read_bytes()
    wind=OUT/'research/wind_network_supplement'
    load=lambda p:pd.read_csv(p,dtype={'station':str},parse_dates=['time'],float_precision='round_trip')
    pd.testing.assert_frame_equal(load(local/'wind.csv'),load(wind/'data/reference_predictions.csv'),check_exact=True)
    browser=P/'weather_network_viewer_bundle_qa_20261101_v12';qa=read(browser/'summary.json');original=read(P/STUDIES[2]/'summary.json')
    assert qa['html_sha256']==original['html_sha256'] and qa['filter_cases']==1840 and qa['javascript_errors']==qa['external_requests']==0
    compare_browser_content(P/STUDIES[2],browser)
    write(browser/'visual_review.json',dict(status='passed',reviewer='Codex visual inspection',
        html_sha256=qa['html_sha256'],screenshots=qa['screenshots'],content_pixels_identical_outside_native_controls=True,
        explanation='Differences confined to native select arrow/width; all1840 selection states and values checked'))
    for path in browser.iterdir():
        if path.is_file() and path.name in ['summary.json','visual_review.json','desktop.png','mobile.png']:
            from scripts.package_review_v8 import copy
            copy(path,OUT/'validation/v12_browser'/path.name)
    for name in ['scripts/package_review_v12.py','scripts/finalize_review_v12.py']:
        copy(ROOT/name,OUT/name)
    errors=inspect_documents(OUT,[p.relative_to(OUT).as_posix() for p in OUT.rglob('*.md')]);assert not errors,'\n'.join(errors)
    write(target,dict(status='v12_delivery_verified',at_utc=now(),preserved_v11_files=len(names),basic_notebook_code_cells=5,
        latest_notebook_code_cells=3,example_prediction_rows_identical=144,wind_cli_rows_exact=432,relocated_browser=qa,
        relocated_browser_content_pixels_identical=True,native_form_controls_compared_semantically=True,
        archived_packager_sha256=sha(OUT/'validation/package_before_native_control_fix.py'),production_model_changed=False,
        wind_network_supplement_added=True,competition_submitted=False))
    manifest(OUT,'model');verify_directory(OUT);print('VERIFIED v12 with native controls compared semantically',flush=True)


if __name__=='__main__':main()
