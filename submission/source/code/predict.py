"""기상 입력으로 노면온도와 결빙 조건을 추정한다."""
from pathlib import Path
import argparse,json,hashlib,sys
import joblib,pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.extended_runtime import infer
from src.submission_io import read_weather
from src.competition_icing_profiles import apply_icing_profile
from src.offline_runtime import deny_network

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--input',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
 p.add_argument('--method',choices=['temperature_moisture','air_temperature'],default='temperature_moisture')
 p.add_argument('--output-start');p.add_argument('--output-end');a=p.parse_args()
 if a.output.exists():raise FileExistsError('Choose a new output file')
 plan=json.loads((ROOT/'extended_training_plan.json').read_text(encoding='utf8'))
 receipt=json.loads((ROOT/'model/refit_receipt.json').read_text(encoding='utf8'));checks={v['name']:v['sha256'] for v in receipt['models']}
 models={'temperature':[],'icing_reference':[]}
 with deny_network() as attempts:
  for spec in plan['models']:
   path=ROOT/'model'/(spec['name']+'.joblib')
   assert hashlib.sha256(path.read_bytes()).hexdigest()==checks[spec['name']]
   models[spec['role']].append(joblib.load(path))
  f=read_weather(a.input)
  out=infer(f,models['temperature'],models['icing_reference'],plan['temperature_feature_kind'],plan['temperature_weights'])
  if a.method=='air_temperature':out=apply_icing_profile(f,out,'score_priority_asos_zero')
  columns=['station','time','estimated_road_temp_c','predicted_ice','temperature_status','moisture_status','aws_status','condition_evidence','weather_history_status']
  out=out[columns];out['method']=a.method
  for value in [a.output_start,a.output_end]:
   if value is not None and pd.Timestamp(value).tz is not None:raise ValueError('Use KST dates without a timezone suffix')
  if a.output_start:out=out.loc[out.time.ge(pd.Timestamp(a.output_start))]
  if a.output_end:out=out.loc[out.time.lt(pd.Timestamp(a.output_end))]
  if out.empty:raise ValueError('Output interval contains no predictions')
  a.output.parent.mkdir(parents=True,exist_ok=True)
  if a.output.suffix=='.parquet':out.to_parquet(a.output,index=False)
  else:out.to_csv(a.output,index=False,encoding='utf-8-sig')
 assert not attempts
 print(json.dumps(dict(rows=len(out),road_temperature_available=int(out.estimated_road_temp_c.notna().sum()),ice_available=int(out.predicted_ice.notna().sum()),method=a.method),ensure_ascii=False))
if __name__=='__main__':main()
