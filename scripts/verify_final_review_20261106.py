"""현재 v14 파일을 실행·검산하고 두 채널 ZIP을 만들어 해시로 재검증한다."""
from pathlib import Path
import argparse,json,os,subprocess,sys,re
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_final_review_20261106 import OUT,OLD,P,CHANNELS,REPORT,PROJECTION,VIEWER,RISK,manifest,now,put
from scripts.package_submission_channels import read,write,copy,sha
from scripts.package_review_v8 import archive
from scripts.review_submission_bundle import verify_directory
from scripts.evaluate_objective_icing import verify_preserved
from scripts.check_markdown import inspect_documents

def run(label,command,cwd=OUT,extra=None):
 env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
 if extra:env.update(extra)
 r=subprocess.run(command,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
 target=OUT/'local_review'/(label+'.log');target.parent.mkdir(exist_ok=True);target.write_bytes(r.stdout)
 if r.returncode:raise RuntimeError('Failed '+label+'; inspect '+str(target))
 print('PASSED',label,flush=True);return target

def preserved():
 old=read(OLD/'manifest.json')['files'];changes=[]
 for n,r in old.items():
  if sha(OUT/n)!=r['sha256']:changes.append(n)
 allowed={'README.md','AI_USAGE.md','docs/STATUS.md','docs/START_HERE.md','docs/README.md','README_repository.md','scripts/build_weather_explorer_20261101.py','docs/delivery/CSV_CONTRACT.md'}
 assert set(changes)<=allowed,changes
 return dict(original_files=len(old),unchanged_files=len(old)-len(changes),updated_historical_entrypoints=changes)

def sync():
 verify_directory(OLD);verify_preserved()
 assert read(REPORT/'visual_review.json')['status']=='passed'
 assert sha(REPORT/'analysis_report_v14.pdf')==read(REPORT/'visual_review.json')['pdf_sha256']
 assert read(OUT/'demo/final_v14/visual_review.json')['status']=='passed'
 assert sha(OUT/'demo/final_review_v14.mp4')==read(OUT/'demo/final_v14/visual_review.json')['video_sha256']
 for name in ['README.md','AI_USAGE.md','docs/STATUS.md','docs/START_HERE.md','docs/README.md','docs/delivery/FINAL_REVIEW_20261106.md','docs/delivery/SUBMISSION_READINESS_20261106.md','docs/competition/OFFICIAL_UPDATE_20261106.md','docs/competition/OFFICIAL_RULES_AND_RUBRIC_20261106.md',
  'docs/research/WIND_DIRECTION_TERRAIN_20261106.md','scripts/audit_wind_direction_terrain_20261106.py','scripts/audit_final_demo_20261106.py','scripts/build_final_demo_20261106.py','scripts/build_final_report_20261106.py','scripts/package_final_review_20261106.py','scripts/verify_final_review_20261106.py']:
  copy(ROOT/name,OUT/('README_repository.md' if name=='README.md' else name))
 for name in ['analysis_report_v14.pdf','analysis_report_v14.md','temperature_observed_predicted.png']:
  copy(REPORT/name,OUT/'reports'/name)
 for name in ['build_receipt.json','visual_review.json']:copy(REPORT/name,OUT/'validation'/('v14_report_'+name))
 study=P/'wind_direction_terrain_20261106_v1'
 for name in ['summary.json','plan.json','feature_receipt.json','independent_verification.json']:
  copy(study/name,OUT/'research/latest'/study.name/name)
 # 현재 기본값 v2와 필수 제출 경로를 대조한다.
 requirements=[('규정','최신 Q&A·공통 배점','docs/competition/OFFICIAL_RULES_AND_RUBRIC_20261106.md'),('보고','현재 분석 보고서','reports/analysis_report_v14.pdf'),('실행','최종 추론','code/predict_final.py'),('학습','전체 노면온도 학습','code/train.py'),('학습자료','허용 지점 학습 자료','data/training_extended_temperature.parquet'),('Notebook','현재 검토·추론·학습 명령','notebooks/final_submission_review_v14.ipynb'),('Notebook','기존 학습·평가 재현','notebooks/submission_review_v11.ipynb'),('환경','고정 버전','requirements-notebook.txt'),('데모','실제 추론 결과 설명','demo/final_review_v14.mp4'),('관측대조','필수 7항목 포함','exports/final/final_observed_predictions_10min.csv'),('분류평가','지점·날짜별 지표와 분모','exports/final/final_station_metrics.csv'),('회귀평가','제외 3지점 BIAS·MAE·RMSE','exports/final/final_temperature_metrics.csv'),('공간','500m 기상 GIS','research/latest/wind_network_segment_projection_20261102_v1/weather_segments.gpkg'),('기준표','새 기준·식·근거·한계','exports/risk_review/risk_criteria_catalog.csv'),('지도','겨울별 도로환경 JPG','exports/risk_review/risk_review_maps.jpg'),('공간','겨울별 Shapefile','exports/risk_review/shapefile_2024/risk_2024_500m.shp'),('탐색','현재 69특성 풍속','research/latest/weather_explorer_20261106_v13/index.html'),('비교','기존 취약구간 목록 비교','research/latest/official_inventory_viewer_20261031_v1/index.html'),('AI','지원 범위·실패·선택','AI_USAGE.md')]
 for _,_,n in requirements:assert (OUT/n).is_file(),n
 pd.DataFrame(requirements,columns=['category','requirement','relative_path']).to_csv(OUT/'submission_requirements_coverage.csv',index=False,encoding='utf-8-sig')
 write(OUT/'validation/v14_preservation.json',preserved())
 manifest(OUT,'model');verify_directory(OUT);print('SYNCED final v14',flush=True)

def verify():
 verify_directory(OUT);preserved();frozen=verify_preserved()
 target=OUT/'validation/v14_delivery.json';assert not target.exists()
 run('v14_core',[sys.executable,'-X','utf8','scripts/review_submission_bundle.py','--smoke','--output','local_review/v14_core.json'])
 core=read(OUT/'local_review/v14_core.json');assert core['prediction_rows_identical']==144
 log=(OUT/'local_review/v14_core_notebook.log').read_text(encoding='utf8');assert '5 code cells' in log
 wind=OUT/'research/wind_network_supplement'
 run('v14_wind',[sys.executable,str(wind/'scripts/predict_wind_network.py'),'--bundle',str(wind),'--input',str(wind/'data/weather_example.csv'),'--aws-input',str(wind/'data/aws_example.parquet'),'--points',str(wind/'data/points_example.csv'),'--output',str(OUT/'local_review/v14_wind.csv')])
 load=lambda p:pd.read_csv(p,dtype={'station':str},parse_dates=['time'],float_precision='round_trip')
 pd.testing.assert_frame_equal(load(OUT/'local_review/v14_wind.csv'),load(wind/'data/reference_predictions.csv'),check_exact=True)
 run('v14_demo_browser',[sys.executable,str(ROOT/'scripts/audit_final_demo_20261106.py')],cwd=ROOT,extra={'PYTHONPATH':str(P/'browser_runtime_20261024'),'PLAYWRIGHT_NODEJS_PATH':'C:/Program Files/nodejs/node.exe'})
 f=pd.read_csv(OUT/'exports/final/final_observed_predictions_10min.csv',dtype={'station_id':str,'observed_surface_state':str},float_precision='round_trip')
 parquet=pd.read_parquet(OUT/'exports/final/final_observed_predictions_10min.parquet')
 # CSV·Parquet의 전달 자료형을 맞춘 뒤 모든 값을 비교한다.
 for c in f:
  if c in parquet:
   a=f[c];b=parquet[c]
   if pd.api.types.is_numeric_dtype(b):np.testing.assert_allclose(pd.to_numeric(a).to_numpy(dtype=float,na_value=np.nan),b.to_numpy(dtype=float,na_value=np.nan),rtol=0,atol=0,equal_nan=True)
   else:assert a.fillna('<NA>').astype(str).equals(b.fillna('<NA>').astype(str)),c
 assert len(f)==103680 and f.icing_policy.eq('preserved_v2').all()
 assert set(['highway_name','station_name','prediction_time_kst','observed_surface_state','predicted_ice','observed_road_temperature_c','estimated_road_temperature_c'])<=set(f)
 import geopandas as gpd
 risk=pd.read_csv(OUT/'exports/risk_review/risk_review_500m.csv');assert len(risk)==1686
 for year in [2024,2025]:
  shp=OUT/f'exports/risk_review/shapefile_{year}/risk_{year}_500m.shp';assert len(gpd.read_file(shp))==843
 qa=P/'weather_explorer_bundle_qa_20261106_v14';assert not qa.exists()
 run('v14_relocated_browser',[sys.executable,str(ROOT/'scripts/audit_weather_explorer_20261101.py'),'--viewer',str(OUT/'research/latest'/VIEWER.name),'--output',str(qa)],cwd=ROOT,extra={'PYTHONPATH':str(P/'browser_runtime_20261024'),'PLAYWRIGHT_NODEJS_PATH':'C:/Program Files/nodejs/node.exe'})
 b=read(qa/'summary.json');assert b['status']=='passed'
 for p in qa.iterdir():
  if p.is_file():copy(p,OUT/'validation/v14_relocated_browser'/p.name)
 for p in (OUT/'local_review').glob('v14*.log'):copy(p,OUT/'validation/v14_execution'/p.name)
 copy(OUT/'local_review/v14_core.json',OUT/'validation/v14_execution/core.json')
 errors=inspect_documents(OUT,[p.relative_to(OUT).as_posix() for p in OUT.rglob('*.md')]);assert not errors,errors
 assert verify_preserved()==frozen
 write(target,dict(status='v14_delivery_verified',at_utc=now(),core_rows_exact=144,default_and_comparison_profile_rows_each=144,wind_cli_rows_exact=432,
 notebook_code_cells=5,observed_prediction_rows=103680,csv_parquet_all_values_exact=True,shapefile_readback_rows=1686,
 current_report_pages=12,current_demo_seconds=80,relocated_browser=b,preservation=preserved(),
 classification_model_changed=False,temperature_model_changed=False,protected_targets_read_after_seal_for_final_delivery=True,official_server_score=False,competition_submitted=False))
 manifest(OUT,'model');verify_directory(OUT);print('VERIFIED final v14',flush=True)

def package():
 verify_directory(OUT);preserved();verify_preserved();assert read(OUT/'validation/v14_delivery.json')['status']=='v14_delivery_verified'
 assert read(OUT/'validation/v14_relocated_browser/visual_review.json')['status']=='passed'
 assert read(OUT/'validation/v14_demo_browser/visual_review.json')['status']=='passed'
 assert not CHANNELS.exists();CHANNELS.mkdir();D=CHANNELS/'icy_road_documents';D.mkdir()
 for source,dest in [('reports/analysis_report_v14.pdf','reports/analysis_report_v14.pdf'),('reports/analysis_report_v14.md','reports/analysis_report_v14.md'),('docs/delivery/FINAL_REVIEW_20261106.md','docs/delivery/FINAL_REVIEW_20261106.md'),('docs/delivery/SUBMISSION_READINESS_20261106.md','docs/delivery/SUBMISSION_READINESS_20261106.md'),('docs/competition/OFFICIAL_RULES_AND_RUBRIC_20261106.md','docs/competition/OFFICIAL_RULES_AND_RUBRIC_20261106.md'),('AI_USAGE.md','AI_USAGE.md'),('exports/risk_review/risk_criteria_catalog.csv','data/risk_criteria_catalog.csv'),('exports/risk_review/risk_review_maps.jpg','figures/risk_review_maps.jpg'),('exports/final/final_temperature_metrics.csv','data/final_temperature_metrics.csv'),('exports/final/final_station_metrics.csv','data/final_station_metrics.csv'),('metrics_summary.json','data/metrics_summary.json')]:copy(OUT/source,D/dest)
 copy(OUT/'docs/research/WIND_DIRECTION_TERRAIN_20261106.md',D/'docs/research/WIND_DIRECTION_TERRAIN_20261106.md')
 short_ai=(OUT/'AI_USAGE.md').read_text(encoding='utf8').split('## 11월 6일 초기 이력')[0]
 put(D/'AI_USAGE.md',short_ai+'\n전체 날짜별 기록은 별도 모델자료 ZIP의 AI_USAGE.md에 보존합니다.\n')
 copy(ROOT/'docs/images/wind_network_projection_20261102.png',D/'figures/wind_network_projection.png');copy(ROOT/'docs/images/inventory_comparison_20261031_v3.png',D/'figures/inventory_comparison.png')
 put(D/'README.md','''# 문서자료 · 최종 v14

[완성물 설명](docs/delivery/FINAL_REVIEW_20261106.md) → [현재 12쪽 보고서](reports/analysis_report_v14.pdf) → [최신 규정·평가 기준](docs/competition/OFFICIAL_RULES_AND_RUBRIC_20261106.md) 순서로 확인합니다. [새 도로환경 검토 지도](figures/risk_review_maps.jpg)와 [기준표](data/risk_criteria_catalog.csv), [현재 풍속 적용](figures/wind_network_projection.png), [기존 취약구간 비교](figures/inventory_comparison.png)를 함께 제공합니다.

제외 3지점 노면온도 MAE 평균 0.977562°C, 최신 결빙 F1 0.032627입니다. 실제 Ice가 있는 1지점만 분류 평균 대상이며 낮은 정밀도가 남습니다. 기본은 기존 v2이고 새 결빙·풍속 후보는 채택 조건을 통과하지 못했습니다. 지도는 실제 Ice 확률·공식 위험등급이 아닙니다.

실행 코드·학습 자료·모형·Notebook·환경·80초 데모·필수 관측 대조 CSV·공간 GIS·오프라인 HTML은 별도 모델자료 ZIP에 있습니다. [AI 지원 기록](AI_USAGE.md)과 [제출 준비 현황](docs/delivery/SUBMISSION_READINESS_20261106.md)을 함께 확인합니다.

마감은 오늘 2026년 11월 6일 23:59 KST입니다. 실제 업로드는 수행하지 않았습니다. 문서자료와 모델자료를 각각 제출하고 사이트 이력을 확인합니다. 승인 완료는 사용자 확인이며 AI 검산을 참가자의 직접 검토로 기록하지 않습니다.
''')
 manifest(D,'documents')
 secret_values=[]
 for line in (ROOT/'secret.env').read_text(encoding='utf-8-sig').splitlines():
  if '=' in line and not line.lstrip().startswith('#'):
   v=line.split('=',1)[1].strip().strip('"'+chr(39))
   if len(v)>=12:secret_values.append(v.encode())
 for folder in [OUT,D]:
  records=read(folder/'manifest.json')['files'];errors=inspect_documents(folder,[n for n in records if n.endswith('.md')]);assert not errors,errors
  for n in records:
   p=folder/n;assert p.suffix.lower() not in {'.env','.pem','.key','.hwp'} and '/.git/' not in '/'+n,n
   if p.suffix in {'.py','.json','.md','.txt','.ipynb','.html','.js','.log','.yml','.csv'}:
    data=p.read_bytes();assert not any(v in data for v in secret_values),n
    assert not re.search(rb'(?:github_pat_[A-Za-z0-9_]{40,}|RGAPI-[A-Za-z0-9-]{30,}|sk-[A-Za-z0-9_-]{30,})',data),n
 archives={c:archive(f,CHANNELS/f'icy_road_{c}.zip','icy_road_'+c) for c,f in [('documents',D),('model',OUT)]}
 verify_directory(OLD);verify_preserved()
 write(CHANNELS/'submission_receipt.json',dict(status='two_channel_archives_verified',at_utc=now(),archives=archives,model_source=OUT.relative_to(ROOT).as_posix(),
 preservation=preserved(),execution=read(OUT/'validation/v14_delivery.json'),competition_submitted=False,
 submission_deadline_kst='2026-11-06T23:59:00+09:00',account_approved='user confirmed',
 remaining=['사용자 완성물 검토','사이트 실제 업로드와 접수 이력 확인']))
 print(json.dumps(archives,ensure_ascii=False),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--stage',required=True,choices=['sync','verify','package']);globals()[p.parse_args().stage]()
