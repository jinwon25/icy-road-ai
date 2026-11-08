"""실제 탐색과 로컬 추론 과정을 설명하는 데모 영상을 녹화한다."""
from pathlib import Path
import sys,os,subprocess,json,html
import pandas as pd
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import write,sha
P=ROOT/'outputs/private';B=P/'competition_submission/icy_road_model';W=P/'editorial_review_20261106';O=B/'demo'
def main():
 O.mkdir(exist_ok=True);env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
 output=B/'local_review/demo_inference.csv';assert not output.exists()
 cmd=[sys.executable,'-X','utf8','code/predict.py','--input','data/weather_example.csv','--output',str(output),'--output-start','2024-12-15','--output-end','2024-12-16']
 run=subprocess.run(cmd,cwd=B,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180);assert run.returncode==0
 (O/'inference_log.txt').write_bytes(run.stdout)
 predicted=pd.read_csv(output,dtype={'station':str},float_precision='round_trip')
 expected=pd.read_csv(B/'data/example_predictions.csv',dtype={'station':str},float_precision='round_trip');pd.testing.assert_frame_equal(predicted,expected,check_exact=True)
 columns=['station','time','estimated_road_temp_c','predicted_ice']
 shown=predicted[columns].head(6).rename(columns={'station':'지점','time':'시각 (KST)','estimated_road_temp_c':'추정 노면온도 (°C)','predicted_ice':'결빙 판정'})
 inputf=pd.read_csv(B/'data/weather_example.csv');shownin=inputf.loc[inputf.time.str.startswith('2024-12-15'),['station','time','asos_air_temp','aws_air_temp','aws_humidity']].head(4)
 stats=json.loads(run.stdout.decode('utf8').strip())
 intro='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>기상 입력의 모형 추론</title><link rel="stylesheet" href="../assets/site.css"><header><nav class="topnav"><a href="../index.html">기상 지도</a><a href="../maps/sections.html">구간 검토</a><a href="../report/analysis_report.pdf">분석 보고서</a><a href="index.html">실행 영상</a></nav><h1>기상 입력으로 노면온도와 결빙 조건 추정</h1><p>포함된 예제 기상을 로컬 Python 모형에 입력해 생성한 결과입니다.</p></header><main><section class="analysis" style="margin:0;padding-top:22px"><h2>실행 명령</h2><pre style="padding:18px;background:#f0f4f6;border-left:3px solid #29546d;white-space:pre-wrap;overflow-wrap:anywhere;font-size:16px;line-height:1.8">python code/predict.py --input data/weather_example.csv
--output local_review/road_predictions.csv
--output-start 2024-12-15 --output-end 2024-12-16</pre><p class="metric-line">출력 __ROWS__행 / 노면온도 추정 __TEMP__행 / 결빙 판정 __ICE__행</p><div class="analysis-grid"><div><h3>입력 예시</h3>__INPUT__</div><div><h3>추정 결과</h3>__OUTPUT__</div></div><p class="data-note">예제는 추론 재현용입니다. 보고서의 미관측 지점 검증 성적과는 구분합니다. 결빙 1은 기준온도·수분 대용조건을 만족한 판정이며 실제 Ice 관측을 뜻하지 않습니다.</p><a href="inference_log.txt">실제 실행 로그</a></section></main></html>'''
 intro=intro.replace('__ROWS__',str(stats['rows'])).replace('__TEMP__',str(stats['road_temperature_available'])).replace('__ICE__',str(stats['ice_available'])).replace('__INPUT__',shownin.to_html(index=False,border=0,float_format=lambda x:f'{x:.1f}')).replace('__OUTPUT__',shown.to_html(index=False,border=0,float_format=lambda x:f'{x:.2f}'))
 (O/'inference.html').write_text(intro,encoding='utf8')
 recording=W/'demo_recording';assert not recording.exists();chapters=[]
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True);context=browser.new_context(viewport=dict(width=1440,height=1080),record_video_dir=str(recording),record_video_size=dict(width=1440,height=1080),accept_downloads=True)
  page=context.new_page();errors=[];external=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  def route(r):
   if r.request.url.startswith(('http://','https://')):external.append(r.request.url);r.abort()
   else:r.continue_()
  page.route('**/*',route)
  def caption(text,seconds,label):
   page.evaluate("""text=>{let n=document.getElementById('demoCaption');if(!n){n=document.createElement('div');n.id='demoCaption';n.style.cssText='position:fixed;bottom:16px;left:28px;right:28px;z-index:9999;background:rgba(255,255,255,.97);border-top:3px solid #29546d;padding:16px 23px;color:#26343d;font:21px/1.65 Malgun Gothic,sans-serif;box-shadow:0 1px 5px #ccd5da';document.body.appendChild(n)}n.textContent=text}""",text)
   chapters.append(label);print('RECORD',label,flush=True);page.wait_for_timeout(int(seconds*1000))
  page.goto((B/'index.html').as_uri());page.wait_for_function('window.WEATHER_READY===true')
  caption('센서가 없는 도로의 기상조건을 500m 구간으로 살펴봅니다. 두 겨울은 같은 척도로 비교합니다.',5,'기상 분포')
  page.select_option('#metric','2');page.wait_for_timeout(800);caption('변수를 풍속으로 바꾸면 같은 도로의 겨울별 기상 분포와 일별 변화가 나타납니다.',4,'풍속')
  page.select_option('#winter','1');page.wait_for_timeout(700);caption('풍속의 지역 전체 제외 평가 MAE는 0.500m/s입니다. 지도 구간마다 실측 검증한 값은 아닙니다.',4,'두 겨울 비교')
  page.evaluate("document.getElementById('temperature').scrollIntoView({block:'start'})");page.wait_for_timeout(700)
  caption('부곡교·해전·삼봉은 학습에서 제외했습니다. 노면온도 MAE 평균은 0.978°C이고 지점별 편향은 남습니다.',6,'노면온도 대조')
  page.get_by_role('heading',name='결빙 판정과 관측 결빙일').evaluate("n=>n.scrollIntoView({block:'start'})");page.wait_for_timeout(700)
  caption('결빙 판정에는 오경보가 많습니다. 정밀도 0.0195의 한계를 바탕으로 활용 목적을 추가 관측 검토에 두었습니다.',6,'결빙 관측일')
  page.goto((B/'maps/sections.html').as_uri());page.wait_for_function('window.SECTION_READY===true')
  caption('기상조건이 두 겨울 모두 높고 도로환경 확인이 필요한 구간을 공개 취약구간 목록과 대조합니다.',6,'구간 선정')
  page.select_option('#view','exposure');page.select_option('#year','0');page.wait_for_timeout(700);caption('서해안 F06 범위 안의 선택 구간입니다. 두 겨울 조건 비율은 약 13.0%와 6.8%입니다.',4,'조건 비율')
  page.select_option('#year','1');page.wait_for_timeout(700)
  page.select_option('#view','inspection');page.select_option('#area','F08');page.click('#focus')
  caption('F08은 호남선 120.6-123.6km의 방향별 확인 범위입니다. 화면은 그 안의 한 500m 구간의 선정 근거를 보여줍니다.',6,'선정 근거')
  with page.expect_download() as info:page.click('#download')
  info.value.save_as(W/'demo_selected_section.csv')
  caption('선택 구간의 두 겨울 값은 CSV로 내려받을 수 있습니다. 전체 11개 범위와 GIS도 함께 제공합니다.',4,'결과 내보내기')
  page.goto((O/'inference.html').as_uri())
  caption('같은 기상 입력으로 노면온도와 결빙 조건을 추론합니다. 화면의 표는 실제 로컬 실행에서 생성한 예제입니다.',7,'모형 추론')
  assert not errors and not external;video=page.video;context.close();video.save_as(str(O/'model_demo.webm'));browser.close()
 (O/'index.html').write_text('''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>기상 분포에서 계측 후보까지</title><link rel="stylesheet" href="../assets/site.css"><header><nav class="topnav"><a href="../index.html">기상 지도</a><a href="../maps/sections.html">구간 검토</a><a href="../report/analysis_report.pdf">분석 보고서</a><a class="active" href="index.html">실행 영상</a></nav><h1>기상 분포에서 계측 후보까지</h1><p>지도에서 조건을 바꾸고 관측·추정을 대조한 뒤 구간의 선정 근거와 CSV를 확인하는 과정입니다.</p></header><main><video controls preload="metadata" style="display:block;width:100%;max-height:760px;background:#edf1f3" src="model_demo.webm"></video><div class="actions"><a class="button" href="../index.html">기상 지도 직접 열기</a><a class="button" href="../maps/sections.html">구간 검토 직접 열기</a><a href="inference.html">실제 추론 예제</a><a href="inference_log.txt">실행 로그</a></div><section class="analysis"><h2>영상에서 다루는 내용</h2><p>두 겨울 기상 분포, 학습 제외 지점의 노면온도, 결빙 관측일과 오경보, 추가 계측·시설 확인 범위, CSV 내보내기와 모형 추론을 순서대로 살펴봅니다.</p><p class="data-note">과거 관측을 이용한 분석 결과입니다. 영상은 로컬 탐색 화면을 녹화했으며 실제 도로 운영이나 제설 효과를 검증한 장면은 아닙니다.</p></section></main></html>''',encoding='utf8')
 write(W/'demo_build.json',dict(status='recorded_pending_video_review',video_sha256=sha(O/'model_demo.webm'),actual_browser_recording=True,cli_rows=144,fixture_exact=True,chapters=chapters,external_requests=external,js_errors=errors))
 print('DEMO RECORDED',flush=True)
if __name__=='__main__':main()
