"""검증된 분석 결과를 심사·사용 목적에 맞는 제출 구조로 구성한다."""
from pathlib import Path
import ast,json,sys,shutil,hashlib
import pandas as pd,numpy as np,nbformat as nb
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import copy,read,sha,write
OLD=ROOT/'outputs/private/submission_candidate_20261106_v14'
P=ROOT/'outputs/private';DELIVERY=P/'competition_submission';B=DELIVERY/'icy_road_model';D=DELIVERY/'icy_road_documents';W=P/'editorial_review_20261106'

def text(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf8')
def module_closure(source,modules):
 result=set();todo=list(modules)
 while todo:
  name=todo.pop()
  if name in result:continue
  p=source/Path(*name.split('.')).with_suffix('.py')
  if not p.exists():continue
  result.add(name);tree=ast.parse(p.read_text(encoding='utf-8-sig'))
  for node in ast.walk(tree):
   if isinstance(node,ast.ImportFrom):
    if node.level:
     stem=name.split('.')[:-node.level]
     module='.'.join(stem+([node.module] if node.module else []))
    else:module=node.module or ''
    if module.startswith('src.'):todo.append(module)
   elif isinstance(node,ast.Import):
    todo.extend(v.name for v in node.names if v.name.startswith('src.'))
 return sorted(result)

PUBLIC_COLUMNS=['station','time','estimated_road_temp_c','predicted_ice','temperature_status','moisture_status','aws_status','condition_evidence','weather_history_status']
PREDICT = r'''"""기상 입력으로 노면온도와 결빙 조건을 추정한다."""
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
'''

def prepare():
 if DELIVERY.exists():assert B.is_dir() and D.is_dir() and W.is_dir()
 B.mkdir(parents=True,exist_ok=True);D.mkdir(exist_ok=True);W.mkdir(exist_ok=True)
 files=['code/train.py','extended_training_plan.json','model/refit_receipt.json','data/weather_example.csv','data/training_extended_temperature.parquet','data/training_weather_temperature.parquet','requirements-notebook.txt']
 for n in files:copy(OLD/n,B/n)
 for p in (OLD/'model').glob('*.joblib'):copy(p,B/'model'/p.name)
 mods=module_closure(OLD,['src.extended_runtime','src.submission_io','src.offline_runtime','src.competition_icing_profiles','src.solar_thermal_runtime','src.submission_runtime'])
 text(B/'src/__init__.py','')
 for m in mods:copy(OLD/Path(*m.split('.')).with_suffix('.py'),B/Path(*m.split('.')).with_suffix('.py'))
 text(B/'code/predict.py',PREDICT)
 text(B/'requirements.txt',(OLD/'requirements-notebook.txt').read_text(encoding='utf8'))
 for method,source,name in [('temperature_moisture','final_example_predictions.csv','example_predictions.csv'),('air_temperature','score_priority_example_predictions.csv','baseline_predictions.csv')]:
  f=pd.read_csv(OLD/'data'/source,float_precision='round_trip',dtype={'station':str})[PUBLIC_COLUMNS];f['method']=method
  f.to_csv(B/'data'/name,index=False,encoding='utf-8-sig')
 # 검증된 원천의 수치를 보존하고 목적별로 정리한다.
 weather={}
 for src,dest in [('weather_observation_supplement','air_temperature'),('weather_history_supplement','humidity'),('wind_network_supplement','wind')]:
  source=OLD/'research'/src;target=B/'weather'/dest;weather[dest]=target
  for p in source.rglob('*'):
   rel=p.relative_to(source)
   if not p.is_file() or '__pycache__' in p.parts or p.suffix=='.pyc':continue
   if rel.parts[0] in ['src','scripts','data','model'] or rel.as_posix() in ['requirements.txt','settings.json']:
    copy(p,target/rel)
  if (source/'notebooks').exists():
   for p in (source/'notebooks').glob('*.ipynb'):copy(p,W/'source_notebooks'/dest/p.name)
 # 검증된 원천의 수치를 보존하고 목적별로 정리한다.
 source=OLD/'exports/final/final_observed_predictions_10min.csv';f=pd.read_csv(source,dtype={'station_id':str,'observed_surface_state':str},float_precision='round_trip')
 columns=['highway_name','station_name','station_id','prediction_time_kst','observed_surface_state','observed_ice','predicted_ice','observed_road_temperature_c','estimated_road_temperature_c','temperature_status','moisture_status']
 result=f[columns].copy();folder=B/'results/evaluation';folder.mkdir(parents=True,exist_ok=True)
 result.to_csv(folder/'observations_predictions.csv',index=False,encoding='utf-8-sig');result.to_parquet(folder/'observations_predictions.parquet',index=False,compression='zstd')
 for src,dest in [('final_temperature_metrics.csv','road_temperature_metrics.csv'),('final_daily_metrics.csv','icing_daily_metrics.csv'),('final_station_metrics.csv','icing_station_metrics.csv')]:
  q=pd.read_csv(OLD/'exports/final'/src,dtype={'station':str},float_precision='round_trip')
  if 'profile' in q:q=q.drop(columns='profile')
  q.to_csv(folder/dest,index=False,encoding='utf-8-sig')
 dictionary=pd.read_csv(OLD/'exports/final/column_dictionary.csv')
 dictionary=dictionary.loc[dictionary.column.isin(columns)].copy()
 dictionary.loc[dictionary.column.eq('predicted_ice'),'unit_and_missing']='1=결빙, 0=조건 미충족, NA=입력 부족'
 dictionary.to_csv(folder/'column_dictionary.csv',index=False,encoding='utf-8-sig')
 copy(OLD/'metrics_summary.json',B/'technical/evaluation_metrics.json')
 # 검증된 원천의 수치를 보존하고 목적별로 정리한다.
 for n in ['official_compliance_audit_20261106_v14/receipt.json','final_selection_20261106_v14/selection_seal.json']:
  copy(P/n,B/'technical'/('input_compliance.json' if 'compliance' in n else 'prediction_freeze.json'))
 wp=P/'wind_network_segment_projection_20261102_v1'
 for n in ['weather_segments_500m.csv','weather_segment_daily.csv.gz','weather_segment_daily.parquet','weather_segments.gpkg']:
  copy(wp/n,B/'results/weather'/n)
 for n in ['summary.json','independent_verification.json']:copy(wp/n,B/'technical/weather_projection'/n)
 # 검증된 원천의 수치를 보존하고 목적별로 정리한다.
 s=read(P/'weather_network_20261101_v1/summary.json');rows=[]
 for target in ['air_temperature','relative_humidity','wind_speed']:
  key='network_residual' if target=='wind_speed' else 'current'
  for mode in ['spatial','joint']:
   d=s['reports'][target][mode]['metrics']
   for method in ['aws_fallback',key]:
    rows.append(dict(target=target,validation=mode,method='aws_reference' if method=='aws_fallback' else 'estimated',**d[method]['pooled']))
 pd.DataFrame(rows).to_csv(B/'results/evaluation/weather_metrics.csv',index=False,encoding='utf-8-sig')
 risk=pd.read_csv(P/'risk_review_20261106_v14/risk_review_500m.csv',float_precision='round_trip')
 chain=pd.read_csv(P/'official_chainage_alignment_20261031_v1/segment_chainage.csv',float_precision='round_trip')
 keep=['seg_id','route_nm','flow_lbl','winter','len_m','prediction_group','planned_slots','ice_valid_slots','cold_wet_slots','cold_wet_hours','cold_wet_fraction','weather_index_100','condition_availability','bridge_code_fraction','tunnel_code_fraction','curve_deg_100m','weather_upper_threshold','review_code','review_label','wind_speed_mean','wind_network_outside_fraction','new_asos_source_domain']
 risk=risk[keep].merge(chain[['seg_id','estimated_km_lo','estimated_km_hi','chainage_available']],on='seg_id',validate='many_to_one')
 labels={0:'입력자료 부족',1:'분석 조건 미충족',2:'저온·수분 조건 관측 대상',3:'저온·수분 빈도 높음',4:'저온·수분 빈도 높음 / 도로환경 확인'}
 risk['review_label']=risk.review_code.map(labels)
 (B/'results/sections').mkdir(parents=True,exist_ok=True)
 risk.to_csv(B/'results/sections/section_review.csv',index=False,encoding='utf-8-sig')
 for p in (P/'risk_review_20261106_v14').rglob('*'):
  if p.is_file() and p.suffix in ['.gpkg','.shp','.shx','.dbf','.prj','.cpg']:
   copy(p,B/'results/sections'/p.relative_to(P/'risk_review_20261106_v14'))
 copy(P/'risk_review_20261106_v14/risk_criteria_catalog.csv',B/'results/sections/criteria.csv')
 inv=P/'vulnerability_map_comparison_20261031_v1'
 for n in ['inventory_mapping.csv','segment_screening.csv','overlap_sensitivity.csv','two_winter_exposure.csv','comparison.gpkg']:
  copy(inv/n,B/'results/inventory'/n)
 copy(P/'official_inventory_viewer_20261031_v1/viewer_data.json',B/'technical/inventory_geometry.json')
 # 검증된 원천의 수치를 보존하고 목적별로 정리한다.
 table=[]
 for (route,winter),q in risk.groupby(['route_nm','winter']):
  length=q.len_m.sum();weight=q.len_m/length
  table.append(dict(route=route,winter=int(winter),segments=len(q),directional_km=length/1000,exposure_pct=float(np.dot(weight,q.weather_index_100)),condition_hours=float(np.dot(weight,q.cold_wet_hours)),weather_groups=q.prediction_group.nunique(),weather_and_context_segments=int(q.review_code.eq(4).sum())))
 pd.DataFrame(table).to_csv(B/'results/sections/route_summary.csv',index=False,encoding='utf-8-sig')
 # 검증된 원천의 수치를 보존하고 목적별로 정리한다.
 for name in ['runtime','joblib','numpy','pandas','scikit-learn','scipy','threadpoolctl']:
  source=OLD/'licenses'/name
  if source.exists():
   for p in source.rglob('*'):
    if p.is_file():copy(p,B/'licenses'/name/p.relative_to(source))
 text(B/'AI_USAGE.md','''# AI 활용 내역\n\n분석 설계 검토, 코드 작성과 수정, 실험 실행 및 결과 대조, 보고서와 데모 편집에 Codex를 활용했습니다. 지표와 지도 수치는 로컬 Python 프로그램으로 계산했습니다. 외부 생성형 AI 예측 API를 추론에 사용하지 않았습니다.\n\n모델 학습·평가 범위, 입력 자료, 결측 처리와 지표 집계 방식은 보고서와 실행 코드에 명시했습니다. 제공 자료는 대회 목적의 비공개 심사 자료이며 공개·재배포 허용을 전제로 하지 않습니다.\n''')
 write(W/'preparation.json',dict(source_manifest_sha256=sha(OLD/'manifest.json'),core_modules=mods,
  model_hashes={p.name:sha(p) for p in (B/'model').glob('*.joblib')},source_observation_table_sha256=sha(OLD/'exports/final/final_observed_predictions_10min.csv'),
  outcome_or_model_values_changed=False,public_result_rows=len(result),historical_materials_included=False))
 print('PREPARED',len(mods),'core modules;',len(result),'evaluation rows;',flush=True)
if __name__=='__main__':prepare()
