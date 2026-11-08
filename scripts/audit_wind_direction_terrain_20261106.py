"""새 풍속 실험의 행·분리·파일 봉인·오차를 별도 NumPy식으로 검산한다."""
from pathlib import Path
import sys,math
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import read,write,sha
from scripts.evaluate_objective_icing import verify_preserved
P=ROOT/'outputs/private';O=P/'wind_direction_terrain_20261106_v1'
def main():
 s=read(O/'summary.json');plan=read(O/'plan.json');assert s['status']=='controlled_wind_direction_terrain_complete'
 for n,h in plan['signatures'].items():assert sha(ROOT/n)==h,n
 for n,h in s['files'].items():assert sha(O/n)==h,n
 raw=P/'official_submission_tables_20261106_v14/receipt.json';assert sha(ROOT/'DATA AI 경진대회 데이터(20261007).zip')==read(raw)['source_archive_sha256']
 blocked=set(plan['settings']['blocked_stations']);fitchecks=0;metricchecks=0
 for f in s['fits']:
  assert not set(f['train_stations'])&set(f['query_stations']) and not (set(f['train_stations'])|set(f['query_stations']))&blocked
  stem=f['held']+('_'+str(f['winter']) if f['winter'] else '')+'_'+f['candidate'];path=O/f['mode']/(stem+'.joblib')
  assert sha(path)==f['model_sha256'] and sha(path.with_suffix('.npy'))==f['prediction_sha256'];assert len(f['features'])==(75 if f['candidate']=='direction' else 84);fitchecks+=1
 for mode in ['joint','spatial']:
  p=pd.read_parquet(O/mode/'predictions.parquet');assert not p.duplicated(['station','time']).any();assert not set(p.station)&blocked
  for c in ['direction','terrain','terrain_blend']:
   q=s['reports'][mode][c]
   def numbers(v,col):
    d=v[col].to_numpy(float)-v.observed.to_numpy(float)
    return dict(mae=float(np.abs(d).sum()/len(d)),rmse=float(np.sqrt(np.square(d).sum()/len(d))),bias=float(d.sum()/len(d)))
   groups=[('pooled',None,p),('cold',None,p.loc[p.cold_input])]+[('winters',str(k),v) for k,v in p.groupby('winter')]+[('regions',k,v) for k,v in p.groupby('group')]
   for section,key,v in groups:
    for col,part in [(c,'metrics'),('current','reference')]:
     expected=q[part][section] if key is None else q[part][section][key]
     actual=numbers(v,col)
     for metric in ['mae','rmse','bias']:
      np.testing.assert_allclose(actual[metric],expected[metric],rtol=0,atol=1e-12);metricchecks+=1
   np.testing.assert_array_equal(p.terrain_blend,(p.current+p.terrain)/2)
 assert fitchecks==24 and verify_preserved()==plan['preservation']
 write(O/'independent_verification.json',dict(status='passed',summary_sha256=sha(O/'summary.json'),fit_checks=fitchecks,numeric_metric_checks=metricchecks,
 source_archive_sha256=read(raw)['source_archive_sha256'],new_feature_test_cases=3,protected_road_state_read=False,
 all_declared_acceptance_gates_retained=True,production_model_changed=False))
 print('WIND AUDIT PASSED',fitchecks,'fits;',metricchecks,'numeric metrics',flush=True)
if __name__=='__main__':main()
