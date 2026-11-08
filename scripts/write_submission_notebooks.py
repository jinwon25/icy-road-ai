"""분석·학습 재현 Notebook과 기준표를 작성한다."""
from pathlib import Path
import sys,json
import pandas as pd,nbformat as nb
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import copy
from scripts.prepare_presentation_submission import module_closure
P=ROOT/'outputs/private';B=P/'competition_submission/icy_road_model';OLD=P/'submission_candidate_20261106_v14'
def put(p,t):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(t,encoding='utf8')
def main():
 copy(ROOT/'src/official_metrics_20261106.py',B/'src/evaluation.py')
 for m in module_closure(OLD,['src.validation']):
  target=B/Path(*m.split('.')).with_suffix('.py')
  if not target.exists():copy(OLD/Path(*m.split('.')).with_suffix('.py'),target)
 n=nb.v4.new_notebook();n.metadata.kernelspec=dict(display_name='Python 3',language='python',name='python3')
 n.cells=[nb.v4.new_markdown_cell('# 전북 고속도로 겨울철 분석\n\n관측과 추정의 차이를 확인하고 예제 기상 입력으로 추론한다. 기상 지도는 ../index.html에서 연다.'),
 nb.v4.new_code_cell("from pathlib import Path\nimport sys,json,subprocess,tempfile,os\nimport pandas as pd\nfrom IPython.display import display,Image\nroot=Path.cwd().resolve()\nif root.name=='notebooks':root=root.parent\nsys.path.insert(0,str(root))\nf=pd.read_csv(root/'results/evaluation/observations_predictions.csv',dtype={'station_id':str},float_precision='round_trip')\nassert len(f)==103680 and not f.duplicated(['station_id','prediction_time_kst']).any()\ndisplay(pd.read_csv(root/'results/evaluation/road_temperature_metrics.csv'))"),
 nb.v4.new_markdown_cell('## 노면온도와 도로 기상\n\n3개 제외 지점의 관측 대조와 지역 전체 제외 기상 평가를 구분한다.'),
 nb.v4.new_code_cell("display(Image(filename=str(root/'report/figures/road_temperature.png')))\nw=pd.read_csv(root/'results/evaluation/weather_metrics.csv')\ndisplay(w.loc[w.validation.eq('spatial'),['target','method','n','mae','rmse','bias']])"),
 nb.v4.new_markdown_cell('## 결빙 판정\n\n날짜별 지표를 지점 안에서 평균한 뒤 실제 Ice가 있는 지점만 평균한다.'),
 nb.v4.new_code_cell("from src.evaluation import evaluate\nq=pd.DataFrame({'station':f.station_id,'time':pd.to_datetime(f.prediction_time_kst),'ice':f.observed_ice})\nmetrics,stations,days=evaluate(q,f.predicted_ice,minimum_valid_slots=1,station_population=sorted(q.station.unique()))\nassert abs(metrics['f1']-0.03262670874029061)<1e-12\ndisplay(pd.DataFrame([{k:metrics[k] for k in ['precision','recall','f1','actual_ice_stations','precision_days','recall_days','f1_days']}]))\ndisplay(stations[['station','status','observed_ice_slots','precision','recall','f1']])\ndisplay(Image(filename=str(root/'report/figures/icing_calendar.png')))"),
 nb.v4.new_markdown_cell('## 기상 입력으로 추론\n\n예제는 실행 재현용이며 검증 성적을 계산하는 자료가 아니다.'),
 nb.v4.new_code_cell("env=os.environ.copy();env.update(OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')\nwith tempfile.TemporaryDirectory(prefix='road_model_') as tmp:\n target=Path(tmp)/'prediction.csv'\n cmd=[sys.executable,'-X','utf8','code/predict.py','--input','data/weather_example.csv','--output',str(target),'--output-start','2024-12-15','--output-end','2024-12-16']\n run=subprocess.run(cmd,cwd=root,env=env,capture_output=True,text=True,encoding='utf8',check=True)\n predicted=pd.read_csv(target,float_precision='round_trip',dtype={'station':str})\n expected=pd.read_csv(root/'data/example_predictions.csv',float_precision='round_trip',dtype={'station':str})\n pd.testing.assert_frame_equal(predicted,expected,check_exact=True)\n display(predicted.head())"),
 nb.v4.new_markdown_cell('## 추가 계측·시설 확인\n\n두 겨울의 기상조건과 도로환경·공개 목록을 대조한 방향별 연속 범위다. 실제 위험 확정 지점은 아니다.'),
 nb.v4.new_code_cell("areas=pd.read_csv(root/'results/sections/inspection_areas.csv')\nassert len(areas)==11 and areas.segments.sum()==22\ndisplay(areas[['area_id','route','direction','estimated_km_start','estimated_km_end','directional_length_km','exposure_pct_2024','exposure_pct_2025']])\ndisplay(Image(filename=str(root/'report/figures/inspection_locations.png')))")]
 (B/'notebooks').mkdir(exist_ok=True);nb.write(n,B/'notebooks/analysis.ipynb')
 n=nb.v4.new_notebook();n.metadata.kernelspec=dict(display_name='Python 3',language='python',name='python3')
 n.cells=[nb.v4.new_markdown_cell('# 모형 학습\n\n포함된 기상 입력과 학습 허용 지점의 노면온도로 모형을 학습한다. 전체 학습은 RUN_TRAINING 환경변수를 1로 지정한 뒤 실행한다. 기온·습도·풍속의 학습 명령은 weather/README.md를 따른다.'),
 nb.v4.new_code_cell("from pathlib import Path\nimport json,os,sys,subprocess\nimport pandas as pd\nroot=Path.cwd().resolve()\nif root.name=='notebooks':root=root.parent\nplan=json.loads((root/'extended_training_plan.json').read_text(encoding='utf8'))\nrows=[]\nfor role,record in plan['training_sources'].items():\n f=pd.read_parquet(root/record['file'])\n assert not set(f.station)&{'12410','23402','33411'}\n rows.append({'학습 목적':role,'행 수':len(f),'지점 수':f.station.nunique()})\ndisplay(pd.DataFrame(rows))"),
 nb.v4.new_code_cell("if os.environ.get('RUN_TRAINING')=='1':\n target=root/'local_review'/'trained_model'\n env=os.environ.copy();env.update(OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')\n subprocess.run([sys.executable,'-X','utf8','code/train.py','--output',str(target)],cwd=root,env=env,check=True)\n display(json.loads((target/'refit_receipt.json').read_text(encoding='utf8')))\nelse:\n print('전체 학습 명령: python code/train.py --output local_review/trained_model')")]
 nb.write(n,B/'notebooks/training.ipynb')
 weather_text='# 도로 기상 모형\n\n기온은 기본 기상 잔차 회귀, 습도는 과거 기상 이력 회귀, 풍속은 주변 AWS 관측망 회귀를 사용한다. 결합 추론은 상위 폴더의 code/predict_weather.py로 실행한다.\n\n| 폴더 | 목적 | 전체 재학습 명령 |\n| --- | --- | --- |\n| air_temperature | 기온 회귀 | python scripts/retrain_weather_supplement.py --bundle . --output local_review/trained |\n| humidity | 과거 이력 습도 | python scripts/retrain_weather_history.py --bundle . --output local_review/trained |\n| wind | 관측망 69특성 풍속 | python scripts/retrain_wind_network.py --bundle . --output local_review/trained |\n\n명령은 각 폴더를 작업 디렉터리로 사용한다. 학습 자료와 고정 설정을 포함한다. 기상 입력은 추정 시각보다 앞선 관측만 사용한다. 모듈의 공통 중간 출력에는 결합 전에 사용하는 다른 기상 열이 포함될 수 있다.\n'
 put(B/'weather/README.md',weather_text)
 for folder,title,script in [('air_temperature','기온 모형','retrain_weather_supplement.py'),('humidity','습도 이력 모형','retrain_weather_history.py'),('wind','풍속 관측망 모형','retrain_wind_network.py')]:
  put(B/'weather'/folder/'README.md',f'# {title}\n\n학습 자료는 data/, 모형은 model/, 전처리와 추론은 src/ 및 scripts/에 있다. requirements.txt로 환경을 설치한다.\n\n전체 재학습 명령: python scripts/{script} --bundle . --output local_review/trained\n\n세 기상값의 결합 추론은 상위 모델자료에서 code/predict_weather.py를 실행한다.\n')
 criteria=[
 ('저온·수분 조건 비율','100 × cold_wet_slots / ice_valid_slots','0-100%','기준온도와 기상 수분 대용조건','실제 Ice 빈도·사고확률 아님'),
 ('높은 기상조건 빈도','겨울별 고유 기상 그룹의 75백분위 이상','2024/25 12.020372%, 2025/26 4.718347%','같은 입력을 공유하는 구간의 중복 가중 방지','자료 내부 비교 기준'),
 ('교량','bridge_code_fraction > 0','중심선에 교량 코드 존재','ODOT 결빙 안내','실제 시설 범위는 현장 확인'),
 ('선형','25m 재표본화 방향 변화의 100m당 합','고유 구간의 75백분위 초과','중심선 파생 통계','설계 곡률·회전반경과 다름'),
 ('자료 충분성','ice_valid_slots / planned_slots','95% 이상','입력 가용성 점검','자료 부족을 낮은 위험으로 처리하지 않음'),
 ('목록 관계','공개 취약구간과 이정 범위 교집합','±250m까지 겹치지 않음','공개 목록 2026.09.07','위치 민감도 조건'),
 ('계측 검토 범위','두 겨울 높은 빈도 + 교량/선형 + 충분성 + 목록 관계','모든 조건 충족, 이정 추정 가능','과제 질의응답의 자체 기준 허용','위험 지정·자동 제설 기준 아님')]
 pd.DataFrame(criteria,columns=['item','formula','threshold','basis','interpretation']).to_csv(B/'results/sections/criteria.csv',index=False,encoding='utf-8-sig')
 f=pd.read_csv(B/'results/sections/section_review.csv');f.loc[f.winter.eq(2024)&f.inspection_candidate].to_csv(B/'results/sections/inspection_segments.csv',index=False,encoding='utf-8-sig')
 print('NOTEBOOKS AND REPRODUCTION GUIDE BUILT',flush=True)
if __name__=='__main__':main()
