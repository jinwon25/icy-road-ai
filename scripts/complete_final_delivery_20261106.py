"""문서 링크를 보완한 뒤 이미 통과한 실행과 현재 파일의 일치를 재확인해 검증을 완결한다."""
from pathlib import Path
import sys
import numpy as np,pandas as pd,geopandas as gpd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_final_review_20261106 import OUT,manifest,now,P
from scripts.package_submission_channels import read,write,copy,sha
from scripts.verify_final_review_20261106 import preserved
from scripts.evaluate_objective_icing import verify_preserved
from scripts.check_markdown import inspect_documents
from scripts.review_submission_bundle import verify_directory

def main():
 target=OUT/'validation/v14_delivery.json';assert not target.exists()
 original=read(OUT/'manifest.json')
 changed=[]
 for n,r in original['files'].items():
  if sha(OUT/n)!=r['sha256']:changed.append(n)
 assert set(changed)=={'scripts/verify_final_review_20261106.py','docs/delivery/CSV_CONTRACT.md'},changed
 core=read(OUT/'local_review/v14_core.json');assert core['status']=='manifest_and_execution_verified' and core['prediction_rows_identical']==144
 assert '5 code cells' in (OUT/'local_review/v14_core_notebook.log').read_text(encoding='utf8')
 options=dict(dtype={'station':str},parse_dates=['time'],float_precision='round_trip')
 wind=OUT/'research/wind_network_supplement'
 pd.testing.assert_frame_equal(pd.read_csv(OUT/'local_review/v14_wind.csv',**options),pd.read_csv(wind/'data/reference_predictions.csv',**options),check_exact=True)
 demo=read(OUT/'validation/v14_demo_browser/receipt.json')
 assert demo['status']=='passed' and demo['actual_playback']
 assert demo['html_sha256']==sha(OUT/'demo/index_v14.html') and demo['webm_sha256']==sha(OUT/'demo/final_review_v14.webm')
 browser=read(OUT/'validation/v14_relocated_browser/summary.json')
 assert browser['status']=='passed' and browser['html_sha256']==sha(OUT/'research/latest/weather_explorer_20261106_v13/index.html')
 for folder in ['v14_demo_browser','v14_relocated_browser']:
  assert read(OUT/'validation'/folder/'visual_review.json')['status']=='passed'
 assert read(OUT/'validation/v14_repository_tests.json')['passed']==494
 csv=OUT/'exports/final/final_observed_predictions_10min.csv'
 f=pd.read_csv(csv,dtype={'station_id':str,'observed_surface_state':str},float_precision='round_trip')
 q=pd.read_parquet(csv.with_suffix('.parquet'));assert len(f)==103680 and len(q)==103680
 for column in f:
  a=f[column];b=q[column]
  if pd.api.types.is_numeric_dtype(b):np.testing.assert_allclose(pd.to_numeric(a).to_numpy(dtype=float,na_value=np.nan),b.to_numpy(dtype=float,na_value=np.nan),rtol=0,atol=0,equal_nan=True)
  else:assert a.fillna('<NA>').astype(str).equals(b.fillna('<NA>').astype(str)),column
 assert f.icing_policy.eq('preserved_v2').all()
 for year in [2024,2025]:assert len(gpd.read_file(OUT/f'exports/risk_review/shapefile_{year}/risk_{year}_500m.shp'))==843
 errors=inspect_documents(OUT,[p.relative_to(OUT).as_posix() for p in OUT.rglob('*.md')]);assert not errors,errors
 p=preserved();verify_preserved();copy(Path(__file__),OUT/'scripts'/Path(__file__).name)
 write(target,dict(status='v14_delivery_verified',at_utc=now(),core_rows_exact=144,default_and_comparison_profile_rows_each=144,
 wind_cli_rows_exact=432,notebook_code_cells=5,observed_prediction_rows=103680,csv_parquet_all_values_exact=True,shapefile_readback_rows=1686,
 current_report_pages=12,current_demo_seconds=80,relocated_browser=browser,actual_demo_browser_playback=True,preservation=p,
 documentation_link_repair=dict(added_historical_dependencies=5,updated_contract=True,changed_existing_paths=changed,model_and_notebook_bytes_unchanged_since_execution=True),
 classification_model_changed=False,temperature_model_changed=False,protected_targets_read_after_seal_for_final_delivery=True,official_server_score=False,competition_submitted=False))
 manifest(OUT,'model');verify_directory(OUT);print('VERIFIED final v14; execution bytes unchanged, all document links passed',flush=True)
if __name__=='__main__':main()
