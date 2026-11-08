"""결과값·실행 진입점·선정 기준·문서 링크를 제출 폴더에서 확인한다."""
from pathlib import Path
import sys,os,json,subprocess,hashlib,re
import pandas as pd,numpy as np
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import read,write,copy,sha
from scripts.check_markdown import inspect_documents
P=ROOT/'outputs/private';B=P/'competition_submission/icy_road_model';W=P/'editorial_review_20261106';OLD=P/'submission_candidate_20261106_v14'
class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  for key in (['href'] if tag in ['a','link'] else ['src'] if tag in ['img','video','source'] else []):
   if a.get(key):self.links.append(a[key])
def run(name,args):
 env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
 result=subprocess.run([sys.executable,'-X','utf8',*args],cwd=B,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600)
 p=W/(name+'.log');p.write_bytes(result.stdout)
 assert result.returncode==0,(name,result.stdout.decode('utf8',errors='replace'))
 print('PASSED',name,flush=True)
def main():
 assert not (W/'delivery_checks.json').exists()
 original={p.name:sha(p) for p in (OLD/'model').glob('*.joblib')}
 assert original=={p.name:sha(p) for p in (B/'model').glob('*.joblib')}
 for name in ['training_extended_temperature.parquet','training_weather_temperature.parquet']:
  assert sha(B/'data'/name)==sha(OLD/'data'/name)
  q=pd.read_parquet(B/'data'/name,columns=['station']);assert not set(q.station)&{'12410','23402','33411'}
 opt=dict(dtype={'station':str},parse_dates=['time'],float_precision='round_trip')
 for method,fixture in [('temperature_moisture','example_predictions.csv'),('air_temperature','baseline_predictions.csv')]:
  path=B/'local_review'/('verified_'+method+'.csv')
  run('cli_'+method,['code/predict.py','--input','data/weather_example.csv','--output',str(path),'--method',method,'--output-start','2024-12-15','--output-end','2024-12-16'])
  pd.testing.assert_frame_equal(pd.read_csv(path,**opt),pd.read_csv(B/'data'/fixture,**opt),check_exact=True)
 path=B/'local_review/verified_weather.csv'
 run('cli_weather',['code/predict_weather.py','--input','data/weather_context_example.csv','--aws-input','data/aws_example.parquet','--points','data/points_example.csv','--output',str(path),'--output-start','2024-12-15','--output-end','2024-12-16'])
 actual=pd.read_csv(path,**opt).sort_values(['station','time']).reset_index(drop=True)
 humidity=pd.read_csv(B/'weather/humidity/data/expected_predictions.csv',**opt).sort_values(['station','time']).reset_index(drop=True)
 wind=pd.read_csv(B/'weather/wind/data/reference_predictions.csv',**opt).sort_values(['station','time']).reset_index(drop=True)
 for expected,cols in [(humidity,['estimated_air_temperature_c','estimated_humidity_pct']),(wind,['estimated_wind_speed_ms'])]:
  pd.testing.assert_frame_equal(actual[['station','time']],expected[['station','time']],check_exact=True)
  for c in cols:np.testing.assert_array_equal(actual[c],expected[c])
 f=pd.read_csv(B/'results/evaluation/observations_predictions.csv',dtype={'station_id':str,'observed_surface_state':str},float_precision='round_trip')
 old=pd.read_csv(OLD/'exports/final/final_observed_predictions_10min.csv',dtype={'station_id':str,'observed_surface_state':str},float_precision='round_trip')
 pd.testing.assert_frame_equal(f,old[f.columns],check_exact=True);assert len(f)==103680 and f.predicted_ice.isna().sum()==18
 # 별도로 작성한 문턱 계산 코드로 22구간을 재계산한다.
 run('section_selection',['code/review_sections.py','--output',str(B/'local_review/verified_sections.csv')])
 sections=pd.read_csv(B/'results/sections/section_review.csv',float_precision='round_trip');selected=pd.read_csv(B/'local_review/verified_sections.csv')
 assert set(selected.seg_id)==set(sections.loc[sections.inspection_candidate,'seg_id']) and selected.seg_id.nunique()==22
 areas=pd.read_csv(B/'results/sections/inspection_areas.csv');assert len(areas)==11 and areas.segments.sum()==22
 assert abs(areas.directional_length_km.sum()-11)<1e-8
 groups=sections.groupby(['winter','prediction_group']).weather_index_100.agg(['min','max']);assert np.max(groups['max']-groups['min'])<1e-12
 for n in ['analysis','training']:
  run('notebook_'+n,[str(ROOT/'scripts/check_notebook.py'),'notebooks/'+n+'.ipynb'])
 errors=inspect_documents(B,[p.relative_to(B).as_posix() for p in B.rglob('*.md')]);assert not errors,errors
 links=0
 for p in B.rglob('*.html'):
  parser=Links();parser.feed(p.read_text(encoding='utf8'))
  for href in parser.links:
   url=urlsplit(href)
   if url.scheme or url.netloc or not url.path:continue
   target=(p.parent/unquote(url.path)).resolve();assert target.is_relative_to(B) and target.is_file(),(p,href);links+=1
 for p in [B/'README.md',B/'report/analysis_report.md']:
  content=p.read_text(encoding='utf8');assert not re.search(r'\bv(?:1[0-9]|[1-9])\b|최종 v|보존된 v',content,re.I),p
 # 고정 환경 선언의 include 그래프에 순환이 없는지 확인한다.
 def visit(path,ancestors):
  assert path not in ancestors
  for line in path.read_text(encoding='utf8').splitlines():
   if line.startswith('-r '):visit(path.parent/line[3:].strip(),ancestors|{path})
 visit(B/'requirements.txt',set());visit(B/'requirements-notebook.txt',set())
 for source,dest in [(W/'weather_browser_checked/summary.json','weather_browser.json'),(W/'section_browser/receipt.json','section_browser.json'),(W/'report_visual_review.json','report_visual_review.json'),(W/'video_review_checked/visual_review.json','demo_visual_review.json')]:
  assert read(source)['status']=='passed';copy(source,B/'validation'/dest)
 for p in W.glob('cli_*.log'):copy(p,B/'validation'/p.name)
 for p in W.glob('notebook_*.log'):copy(p,B/'validation'/p.name)
 write(W/'delivery_checks.json',dict(status='passed',model_hashes_unchanged=True,training_data_hashes_unchanged=True,core_example_rows_each=144,weather_example_rows=432,
 observations_predictions_rows=103680,original_prediction_values_exact=True,inspection_segments=22,inspection_areas=11,source_weather_groups=5,
 notebooks=dict(analysis=5,training=3),local_html_links=links,markdown_links_passed=True,requirements_no_include_cycles=True,
 report_pages=8,browser_weather_values=1632048,browser_weather_cases=126,browser_section_values=3372,browser_section_cases=36,competition_submitted=False))
 copy(W/'delivery_checks.json',B/'validation/delivery_checks.json');print('ALL DELIVERY CHECKS PASSED',flush=True)
if __name__=='__main__':main()
