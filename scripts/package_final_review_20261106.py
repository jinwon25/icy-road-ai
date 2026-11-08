"""최신 규정·관측대조·풍속 구간 적용·새 검토 기준을 v12와 분리된 v14에 구성한다."""
import argparse,json,os,re,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
import nbformat as nb
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import read,write,copy,sha
from scripts.package_review_v8 import archive
from scripts.review_submission_bundle import verify_directory
from scripts.evaluate_objective_icing import verify_preserved
from scripts.check_markdown import inspect_documents
P=ROOT/'outputs/private';OLD=P/'submission_candidate_20261101_v12';OUT=P/'submission_candidate_20261106_v14';CHANNELS=P/'submission_channels_20261106_v14'
ASSETS=P/'final_release_assets_20261106_v14';REPORT=P/'final_report_20261106_v14';RISK=P/'risk_review_20261106_v14'
PROJECTION=P/'wind_network_segment_projection_20261102_v1';VIEWER=P/'weather_explorer_20261106_v13'
SYNC=['AI_USAGE.md','docs/competition/OFFICIAL_RULES_AND_RUBRIC_20261106.md','docs/competition/OFFICIAL_UPDATE_20261106.md',
'docs/delivery/FINAL_REVIEW_20261106.md','docs/delivery/SUBMISSION_READINESS_20261106.md','scripts/predict_competition_profile.py',
'scripts/predict_final_submission_20261106.py','scripts/build_official_submission_tables_20261106.py','scripts/audit_official_compliance_20261106.py',
'scripts/evaluate_official_icing_upgrade_20261106.py','scripts/build_risk_review_20261106.py','scripts/evaluate_wind_direction_terrain_20261106.py',
'scripts/build_weather_explorer_20261101.py','scripts/build_final_report_20261106.py','scripts/package_final_review_20261106.py',
'src/official_metrics_20261106.py','src/official_icing_upgrade.py','src/risk_review_20261106.py','src/wind_direction_terrain_20261106.py',
'config/official_icing_upgrade_20261106.json','config/wind_direction_terrain_20261106.json',
 'tests/test_official_metrics_20261106.py','tests/test_risk_review_20261106.py','tests/test_wind_direction_terrain_20261106.py']

def now():return datetime.now(timezone.utc).isoformat()
def put(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value,encoding='utf8')
def manifest(folder,channel):
 value=dict(package_label='v14',channel=channel,status='local_submission_candidate',at_utc=now(),competition_submitted=False,
 current_report='reports/analysis_report_v14.pdf',files={p.relative_to(folder).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in folder.rglob('*') if p.is_file() and p!=folder/'manifest.json' and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.relative_to(folder).parts[0]!='local_review'})
 if channel=='model':value.update(current_notebook='notebooks/final_submission_review_v14.ipynb',production_model_version='v3',icing_version='v2',production_model_changed=False,default_icing_profile='preserved_v2',current_weather_explorer='research/latest/weather_explorer_20261106_v13/index.html',current_weather_projection='research/latest/wind_network_segment_projection_20261102_v1',current_observation_comparison='exports/final/final_observed_predictions_10min.csv',current_demo='demo/final_review_v14.mp4')
 if (folder/'manifest.json').exists():(folder/'manifest.json').unlink()
 write(folder/'manifest.json',value)

def notebook():
 n=nb.v4.new_notebook();n.metadata.kernelspec=dict(display_name='Python 3',language='python',name='python3')
 n.cells=[nb.v4.new_markdown_cell('# 최종 제출 검토 · v14\n\n현재 진입점은 이 노트북과 README입니다. v12 실행·학습 자산을 보존하고 최신 Q&A·고정 관측 대조·69특성 풍속의 구간 결과·도로환경 검토를 확인합니다. 관측은 이미 봉인 후 수행한 최종 대조용이며 여기서 모델을 조정하지 않습니다.'),
 nb.v4.new_code_cell("from pathlib import Path\nimport hashlib,json,sys,subprocess,tempfile,os\nimport pandas as pd\nroot=Path.cwd().resolve()\nif root.name=='notebooks':root=root.parent\nsys.path.insert(0,str(root))\nread=lambda p:json.loads(p.read_text(encoding='utf8'))\nsha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()\nm=read(root/'manifest.json')\nfor name,r in m['files'].items():\n p=root/name\n assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],name\nprint('Verified',len(m['files']),'files; default profile:',m['default_icing_profile'])"),
 nb.v4.new_code_cell("env=os.environ.copy();env.update(OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')\n(root/'local_review').mkdir(exist_ok=True)\nwith tempfile.TemporaryDirectory(prefix='v14_notebook_',dir=root/'local_review') as tmp:\n for profile,fixture in [('preserved_v2','final_example_predictions.csv'),('score_priority_asos_zero','score_priority_example_predictions.csv')]:\n  target=Path(tmp)/(profile+'.csv')\n  cmd=[sys.executable,'-X','utf8','code/predict_final.py','--input','data/weather_example.csv','--output',str(target),'--output-start','2024-12-15','--output-end','2024-12-16']\n  if profile!='preserved_v2':cmd+=['--icing-profile',profile]\n  r=subprocess.run(cmd,cwd=root,env=env,capture_output=True,text=True,encoding='utf8',check=True)\n  print(r.stdout.strip())\n  options=dict(dtype={'station':str},float_precision='round_trip')\n  pd.testing.assert_frame_equal(pd.read_csv(target,**options),pd.read_csv(root/'data'/fixture,**options),check_exact=True)\nprint('Both fixed profiles: 144 identical rows each')"),
 nb.v4.new_code_cell("from src.official_metrics_20261106 import evaluate\nf=pd.read_csv(root/'exports/final/final_observed_predictions_10min.csv',dtype={'station_id':str},float_precision='round_trip')\nassert len(f)==103680 and not f.duplicated(['station_id','prediction_time_kst']).any()\nq=pd.DataFrame({'station':f.station_id,'time':pd.to_datetime(f.prediction_time_kst),'ice':f.observed_ice})\nsummary=read(root/'metrics_summary.json')\nfor minimum,key in [(1,'primary'),(144,'strict_144')]:\n result=evaluate(q,f.predicted_ice,minimum_valid_slots=minimum,station_population=sorted(q.station.unique()))\n metrics=result[0] if isinstance(result,tuple) else result\n print('Metric return',type(result).__name__)\nprint('Fixed assessment:',summary['primary'])\ndisplay(pd.read_csv(root/'exports/final/final_temperature_metrics.csv'))"),
 nb.v4.new_code_cell("projection=root/m['current_weather_projection']\ns=read(projection/'summary.json');a=read(projection/'independent_verification.json')\nassert a['status']=='passed' and a['summary_sha256']==sha(projection/'summary.json')\nassert s['segment_count']==843 and s['daily_rows']==202320\nrisk=pd.read_csv(root/'exports/risk_review/risk_review_500m.csv')\nassert len(risk)==1686\nprint('843 segments; 240 dates; daily 202320 rows; risk review 1686 rows')\ndisplay(pd.read_csv(root/'exports/risk_review/risk_criteria_catalog.csv'))"),
 nb.v4.new_markdown_cell('## 전체 재학습\n\n포함 허용 자료와 고정 설정으로 재학습합니다. 아래 셀은 환경변수 `ICY_ROAD_RUN_STAGES`에 `refit`이 있을 때 실행합니다. 풍속·습도의 전체 재학습 노트북과 검증 기록도 해당 research 보완 폴더에 있습니다. 기본 실행은 완성된 모형의 추론·결과 검토입니다.'),
 nb.v4.new_code_cell("stages=json.loads(os.environ.get('ICY_ROAD_RUN_STAGES','[]'))\nif 'refit' in stages:\n target=root/'local_review'/'v14_temperature_refit'\n subprocess.run([sys.executable,'-X','utf8','code/train.py','--output',str(target)],cwd=root,env=env,check=True)\nelse:\n print('Full refit command: python code/train.py --output local_review/v14_temperature_refit')"),
 nb.v4.new_markdown_cell('결빙의 낮은 정밀도·평가 대상 1지점·개발과 최종의 순위 역전을 유지합니다. 공식 서버 점수나 운영 안전성을 보장하지 않습니다. 이전 날짜의 보고서·README는 당시 이력입니다.')]
 nb.write(n,OUT/'notebooks/final_submission_review_v14.ipynb')

def prepare(resume=False):
 if not resume:assert not OUT.exists()
 verify_directory(OLD);frozen=verify_preserved()
 for name in read(OLD/'manifest.json')['files']:
  if not (OUT/name).exists():copy(OLD/name,OUT/name)
 copy(OLD/'manifest.json',OUT/'provenance/v12_manifest.json');copy(OLD/'README.md',OUT/'README_v12.md')
 for p in ASSETS.rglob('*'):
  if p.is_file():
   rel=p.relative_to(ASSETS)
   target=OUT/'exports/final'/rel.relative_to('exports') if rel.parts[0]=='exports' else OUT/rel
   if p.name in ['final_example_predictions.csv','score_priority_example_predictions.csv']:target=OUT/'data'/p.name
   copy(p,target)
 copy(ROOT/'scripts/predict_release_default_20261106.py',OUT/'code/predict_final.py')
 for name in SYNC:
  if (ROOT/name).is_file():copy(ROOT/name,OUT/name)
 for source,dest in [(PROJECTION,OUT/'research/latest'/PROJECTION.name),(VIEWER,OUT/'research/latest'/VIEWER.name),(RISK,OUT/'exports/risk_review')]:
  for p in source.rglob('*') if source==RISK else source.iterdir():
   if p.is_file() and '__pycache__' not in p.parts:copy(p,dest/p.relative_to(source))
 # 현재 기본 v2와 추가 비교 열에 맞춰 이전 설명 사전만 명시적으로 교정한다.
 import pandas as pd
 dictionary=pd.read_csv(OUT/'exports/final/column_dictionary.csv')
 dictionary.loc[dictionary.column.eq('predicted_ice'),'unit_and_missing']='1/0/NA; 기본 preserved_v2 저온·수분 판정'
 dictionary=pd.concat([dictionary,pd.DataFrame([dict(column='predicted_ice_asos_zero',meaning_ko='ASOS 기온 0°C 기준선의 비교 판단',unit_and_missing='1/0/NA; 주 제출 예측과 구분'),dict(column='icing_policy',meaning_ko='주 제출 분류 프로필',unit_and_missing='preserved_v2')])],ignore_index=True)
 dictionary.to_csv(OUT/'exports/final/column_dictionary.csv',index=False,encoding='utf-8-sig')
 put(OUT/'exports/risk_review/README.md',(RISK/'README.md').read_text(encoding='utf8').replace('현재 제출용 F1 우선 분류 프로필과 조건 노출 지수의 목적은 다릅니다.','현재 주 제출 프로필은 기존 v2이며, 노출지수는 같은 조건을 기간별로 요약한 값입니다.'))
 for source in [P/'official_compliance_audit_20261106_v14',P/'final_selection_20261106_v14',P/'official_submission_tables_20261106_v14',P/'official_icing_upgrade_20261106_v1']:
  for name in ['receipt.json','selection_seal.json','summary.json','plan.json','selection.json']:
   if (source/name).is_file():copy(source/name,OUT/'provenance'/source.name/name)
 copy(RISK/'visual_review.json',OUT/'validation/v14_risk_visual.json')
 for p in (P/'weather_explorer_validation_20261106_v13').iterdir():
  if p.is_file():copy(p,OUT/'validation/v14_weather_explorer'/p.name)
 notebook()
 put(OUT/'README.md','''# 전북 고속도로 기상·노면온도·결빙 분석 · 최종 v14

[완성물 설명](docs/delivery/FINAL_REVIEW_20261106.md) → [현재 분석 보고서](reports/analysis_report_v14.pdf) → [실행 데모](demo/index_v14.html) 순서로 확인합니다. 기본 분류는 기존 v2, 온도는 v3, 풍속은 69특성 관측망 모형입니다. 과거 날짜의 README·보고서·화면은 당시 이력이며 이 진입점과 최상위 manifest가 현재 구성입니다.

- [최신 규정·평가 기준](docs/competition/OFFICIAL_RULES_AND_RUBRIC_20261106.md): 오늘 23:59 KST 마감, 최신 Q&A693·716 반영.
- [관측·예측 필수 103,680행 CSV](exports/final/final_observed_predictions_10min.csv), [열 설명](exports/final/column_dictionary.csv), [최종 노면온도 지표](exports/final/final_temperature_metrics.csv).
- [843구간·240일 기상 지도](research/latest/weather_explorer_20261106_v13/index.html): 풍속·겨울·노선·구간을 선택합니다. Chrome·Edge에서 인터넷 없이 열립니다.
- [새 도로환경 검토 JPG](exports/risk_review/risk_review_maps.jpg), [기준표](exports/risk_review/risk_criteria_catalog.csv), [GIS](exports/risk_review/risk_review.gpkg). 겨울별 Shapefile도 같은 폴더에 있습니다.
- [기존 취약구간 비교 지도](research/latest/official_inventory_viewer_20261031_v1/index.html): 문제 목록·최신 목록·위치 불확실성·기상 노출을 함께 확인합니다.
- [현재 실행·검토 노트북](notebooks/final_submission_review_v14.ipynb), [풍속 전체 학습·실행](research/wind_network_supplement/README.md), [습도 전체 학습·실행](research/weather_history_supplement/README.md).

## 실행

Windows·Python 3.11·CPU에서 검증합니다. 고정 버전은 requirements-notebook.txt와 별도 기상 모형의 requirements.txt를 사용합니다. 인증키·외부 예측 API는 필요하지 않습니다. 패키지 설치에는 다운로드가 필요합니다.

```powershell
python -m pip install -r requirements-notebook.txt
$env:OMP_NUM_THREADS='2'
$env:OPENBLAS_NUM_THREADS='2'
python code/predict_final.py --input data/weather_example.csv --output local_review/my_final.csv --output-start 2024-12-15 --output-end 2024-12-16
python scripts/check_notebook.py notebooks/final_submission_review_v14.ipynb
python scripts/review_submission_bundle.py --smoke --output local_review/my_verification.json
python code/train.py --output local_review/my_temperature_refit
```

기본 명령은 preserved_v2입니다. 비교용 기온 기준선은 같은 명령에 `--icing-profile score_priority_asos_zero`를 명시합니다. 각 프로필은 144행 예제와 정확 대조합니다. 실제 추론 입력에 관측 정답 열을 넣지 않습니다. 최종 관측 대조 CSV는 평가·전달용입니다. 코드·학습 데이터·모형·기본 및 전체 학습 Notebook·환경·검증 기록을 포함합니다. 과거 전체 연구의 원자료 재구성에는 원 비공개 작업공간이 추가로 필요합니다.

## 결과와 한계

제외 3지점의 노면온도 MAE 평균은 0.977562°C입니다. 결빙 F1은 0.032627·Precision 0.019495·Recall 0.593588로 낮은 정밀도가 남아 있습니다. 실제 Ice가 있는 부곡교 1지점만 분류 평균에 포함하고 해전·삼봉은 산출불가로 표시합니다. 모델·두 프로필을 먼저 봉인한 뒤 고정 관측 대조를 수행했으며 최종 정답으로 가중치·문턱을 다시 맞추지 않았습니다. 개발과 최종 자료의 기준선 순위가 역전됐습니다.

현재 풍속은 지역 제외 MAE 0.499955m/s, 지역·겨울 동시 제외 0.508379m/s이며 843구간에 실제 적용했습니다. 입력 범위 이탈 26.40%·30.39%는 오차나 확률이 아닙니다. 같은 기상 입력을 공유하는 구간을 독립 표본으로 세지 않습니다. 도로환경 검토는 현장 확인을 위한 새 기준이며 실제 Ice·사고확률·공식 위험등급이 아닙니다.

실제 대회 업로드는 수행하지 않았습니다. 문서자료 ZIP과 모델자료 ZIP을 각각 올리고 접수 이력을 확인합니다. 참가 승인 완료는 사용자가 확인했으며 AI의 검산을 참가자의 직접 검토로 기록하지 않습니다. 원자료·행단위 예측·모형은 공개 저장소 공유 대상에서 제외합니다.
''')
 write(OUT/'provenance/v14_preparation.json',dict(at_utc=now(),source_manifest_sha256=sha(OLD/'manifest.json'),preservation=frozen,
 original_v12_retained=True,default_profile='preserved_v2',dictionary_corrected_to_default_v2=True,
 protected_outcomes_read_only_after_seal_for_fixed_final_delivery=True,classification_threshold_or_model_refit_after_protected_join=False))
 print('PREPARED v14',flush=True)

def resume_prepare():prepare(resume=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--stage',choices=['prepare','resume_prepare'],required=True);globals()[p.parse_args().stage]()