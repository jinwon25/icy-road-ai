"""실제 탐색과 로컬 추론 과정을 설명하는 데모 영상을 녹화한다."""
from pathlib import Path
import sys,os,subprocess,json,html
import pandas as pd
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import write,sha
P=ROOT/'outputs/private';W=P/'final_jury_review_20261106';B=W/'icy_road_model';O=B/'demo'
def main():
 O.mkdir(exist_ok=True);env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
 output=B/'local_review/demo_full_jury.parquet';assert output.exists()
 cmd=[sys.executable,'-X','utf8','code/predict.py','--input','data/validation_weather.parquet','--output',str(output)]
 stdout=(O/'inference_log.txt').read_bytes();assert json.loads(stdout.decode('utf8'))['rows']==103680
 predicted=pd.read_parquet(output)
 expected=pd.read_parquet(B/'local_review/full_protected_predictions.parquet');pd.testing.assert_frame_equal(predicted,expected,check_exact=True)
 columns=['station','time','estimated_road_temp_c','predicted_ice']
 shown=predicted[columns].head(6).rename(columns={'station':'지점','time':'시각 (KST)','estimated_road_temp_c':'추정 노면온도 (°C)','predicted_ice':'결빙 판정'})
 inputf=pd.read_parquet(B/'data/validation_weather.parquet');shownin=inputf[['station','time','asos_air_temp','aws_air_temp','aws_humidity']].head(4)
 shown['추정 노면온도 (°C)']=shown['추정 노면온도 (°C)'].map(lambda x:'미산출' if pd.isna(x) else f'{x:.2f}')
 shown['결빙 판정']=shown['결빙 판정'].map(lambda x:'미산출' if pd.isna(x) else str(int(x)))
 shownin=shownin.rename(columns={'station':'지점','time':'시각 (KST)','asos_air_temp':'ASOS 기온 (°C)','aws_air_temp':'AWS 기온 (°C)','aws_humidity':'AWS 습도 (%)'})
 for col in ['ASOS 기온 (°C)','AWS 기온 (°C)','AWS 습도 (%)']:shownin[col]=shownin[col].map(lambda x:'입력 없음' if pd.isna(x) else f'{x:.1f}')
 stats=json.loads(stdout.decode('utf8').strip())
 intro='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>기상 입력의 모형 추론</title><link rel="stylesheet" href="../assets/site.css"><style>.analysis-grid>div{min-width:0}.table-scroll{max-width:100%}</style><header><nav class="topnav"><a class="team-brand" href="../index.html">로드투인사이트</a><a href="../index.html">기상 지도</a><a href="../maps/sections.html">구간 검토</a><a href="../report/analysis_report.pdf">분석 보고서</a><a href="index.html">실행 영상</a><a href="../results/field/index.html">현장 확인</a></nav><h1>기상 입력으로 노면온도와 결빙 조건 추정</h1><p>두 겨울의 전체 검증 기상을 로컬 Python 모형에 입력한 결과입니다. 입력 조건이 부족한 시각은 미산출로 남겼습니다.</p></header><main><section class="analysis" style="margin:0;padding-top:22px"><h2>실행 명령</h2><pre style="padding:18px;background:#f0f4f6;border-left:3px solid #29546d;white-space:pre-wrap;overflow-wrap:anywhere;font-size:16px;line-height:1.8">python code/predict.py --input data/validation_weather.parquet --output local_review/full_predictions.parquet</pre><p class="metric-line">출력 __ROWS__행 / 노면온도 추정 __TEMP__행 / 결빙 판정 __ICE__행</p><div class="analysis-grid"><div><h3>입력 일부</h3><div class="table-scroll">__INPUT__</div></div><div><h3>추정 결과 일부</h3><div class="table-scroll">__OUTPUT__</div></div></div><p class="data-note">학습에서 제외한 세 지점의 두 겨울 전체를 다시 추론한 결과입니다. 관측 정답은 입력하지 않았으며 표에는 예측값 일부를 표시합니다. 결빙 1은 기준온도·수분 대용조건을 만족한 판정이며 실제 Ice 관측을 뜻하지 않습니다.</p><a href="inference_log.txt">실제 실행 로그</a></section></main></html>'''
 intro=intro.replace('__ROWS__',f"{stats['rows']:,}").replace('__TEMP__',f"{stats['road_temperature_available']:,}").replace('__ICE__',f"{stats['ice_available']:,}").replace('__INPUT__',shownin.to_html(index=False,border=0,float_format=lambda x:f'{x:.1f}')).replace('__OUTPUT__',shown.to_html(index=False,border=0,float_format=lambda x:f'{x:.2f}'))
 (O/'inference.html').write_text(intro,encoding='utf8')
 recording=W/'jury_final_demo_recording';assert not recording.exists();chapters=[]
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
  caption('500m 843구간의 두 겨울 기상을 같은 척도로 비교합니다. 도로를 선택하면 일별 변화도 확인할 수 있습니다.',5,'기상 지도')
  page.select_option('#metric','2');page.select_option('#winter','1')
  caption('풍속의 지역 전체 제외 평가 MAE는 0.500m/s입니다. 각 지도 구간에서 실측 검증한 점수와는 구분합니다.',5,'풍속 추정')
  page.evaluate("document.getElementById('benchmarks').scrollIntoView({block:'start'})")
  caption('기본 12특성 회귀와 같은 관측쌍에서 비교한 노면온도 MAE가 14.6% 낮았습니다. 세 지점 모두 개선됐습니다.',7,'같은 관측쌍 비교')
  page.get_by_role('heading',name='결빙 판정과 관측 결빙일').evaluate("n=>n.scrollIntoView({block:'start'})")
  caption('결빙의 날짜별 정밀도는 0.0195로 낮습니다. 낮은 온도와 주변 적설만으로 도로 위의 Ice를 확정하기 어렵습니다.',6,'결빙 판정의 한계')
  page.goto((B/'maps/sections.html').as_uri());page.wait_for_function('window.SECTION_READY===true')
  caption('공개 목록과 중첩 가능한 81구간과 추가 계측 후보 3구간을 함께 봅니다. 지도 색은 위험등급이 아니라 검토할 정보의 종류입니다.',5,'목록과 추가 확인 종합')
  page.locator('#criteria').evaluate('(e)=>e.open=false')
  caption('실제 14입력 시계열의 중복을 제거한 기준 조합은 3구간·2개 범위입니다. 각 구간의 기상·도로환경·목록 관계와 선정 근거를 함께 보여줍니다.',6,'구간별 근거')
  page.locator('#inventoryAgreement').scroll_into_view_if_needed()
  caption('목록과 명목상 겹치는 64구간 중 두 겨울 모두 기상 상위 25%에 든 곳은 0개였습니다. 이 기상 조건으로 기존 지정을 해제하지 않습니다.',7,'목록과 기상 조건의 불일치')
  page.locator('#matrix').scroll_into_view_if_needed()
  caption('기상 빈도와 선형 기준, 목록 경계 여유를 바꾼 75개 조합입니다. 숫자를 누르면 그 기준을 지도에 반영합니다.',5,'기준 민감도')
  page.locator('#matrix button[data-scenario="2"]').click()
  caption('두 기준을 상위 40%로 넓히면 86구간입니다. 선정 개수는 비교 기준에 따라 달라집니다.',4,'기준 조정')
  page.evaluate("el('weatherQ').value='0.9';scenario()")
  caption('기상 상위 10%를 두 겨울 모두 요구하면 추가 후보는 0구간입니다. 공개 목록과의 대조는 그대로 유지됩니다.',4,'엄격한 기준')
  page.evaluate("el('weatherQ').value='0.75';el('curveQ').value='0.75';el('margin').value='250';scenario()")
  page.locator('#area').select_option('S01');page.locator('#view').select_option('shade')
  page.locator('#map').scroll_into_view_if_needed()
  caption('S01의 두 구간은 75개 조합 중 60개에서 유지됐습니다. 공개 DSM의 지형 차폐도 현장 확인 맥락으로 제공합니다.',6,'지형 맥락')
  with page.expect_download() as info:page.locator('#download').click()
  info.value.save_as(W/'demo_selected_information.csv')
  caption('선택한 구간의 조건·기준·지형 근거를 CSV로 내려받았습니다. 실제 결빙확률이나 위험 배점으로 해석하지 않습니다.',4,'근거 내보내기')
  page.goto((B/'results/field/index.html').as_uri());page.wait_for_function('window.FIELD_READY===true')
  caption('선정한 두 범위에 같은 기상 입력을 공유하는 인접 비교 후보를 연결했습니다. 실제 계측을 수행한 결과가 아니라 비교 측정 계획입니다.',5,'현장 확인 계획')
  page.locator('#S01 .area-map').scroll_into_view_if_needed()
  caption('A는 선정 범위의 대표점, B는 약 500m 떨어진 비선정 구간입니다. 위치와 선형 변화, 지형 추정을 나란히 확인합니다.',5,'같은 기상의 인접 비교')
  page.locator('#S01 summary').click();page.locator('#S01 details').scroll_into_view_if_needed()
  caption('노면온도와 실제 수분 상태, 잔류염분과 제빙 시각을 함께 기록합니다. 미측정 값은 채워 넣지 않았습니다.',5,'비교 기록 양식')
  with page.expect_download() as info:page.locator('#csv').click()
  info.value.save_as(W/'demo_unmeasured_field_record.csv')
  page.goto((O/'inference.html').as_uri())
  caption('전체 검증 기상 103,680행을 로컬 모형으로 다시 추론했습니다. 온도와 결빙 예측 모두 제출 표의 값과 정확히 일치합니다.',7,'실제 모형 추론')
  assert not errors and not external;video=page.video;context.close();video.save_as(str(O/'model_demo.webm'));browser.close()
 (O/'index.html').write_text('''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>지도에서 현장 확인 계획까지</title><link rel="stylesheet" href="../assets/site.css"><style>.analysis-grid>div{min-width:0}.table-scroll{max-width:100%}</style><header><nav class="topnav"><a class="team-brand" href="../index.html">로드투인사이트</a><a href="../index.html">기상 지도</a><a href="../maps/sections.html">구간 검토</a><a href="../report/analysis_report.pdf">분석 보고서</a><a class="active" href="index.html">실행 영상</a><a href="../results/field/index.html">현장 확인</a></nav><h1>지도에서 현장 확인 계획까지</h1><p>지도에서 조건을 바꾸고 관측·추정을 대조한 뒤 구간의 선정 근거와 CSV를 확인하는 과정입니다.</p></header><main><video controls preload="metadata" style="display:block;width:100%;max-height:760px;background:#edf1f3" src="model_demo.webm"></video><div class="actions"><a class="button" href="../index.html">기상 지도 직접 열기</a><a class="button" href="../maps/sections.html">구간 검토 직접 열기</a><a href="inference.html">실제 추론 예제</a><a href="inference_log.txt">실행 로그</a></div><section class="analysis"><h2>영상에서 다루는 내용</h2><p>두 겨울 기상, 같은 관측쌍의 회귀 비교, 결빙 판정의 한계, 공개 목록 대조와 75개 기준 조합의 민감도, 지형 맥락과 CSV 내보내기, 현장 확인 계획과 기록 양식, 실제 모형 추론을 순서대로 살펴봅니다.</p><p class="data-note">과거 관측을 이용한 분석 결과입니다. 영상은 로컬 탐색 화면을 녹화했으며 실제 도로 운영이나 제설 효과를 검증한 장면은 아닙니다.</p></section></main></html>''',encoding='utf8')
 write(W/'demo_build_final.json',dict(status='recorded_pending_video_review',video_sha256=sha(O/'model_demo.webm'),actual_browser_recording=True,cli_rows=103680,fixture_exact=True,chapters=chapters,external_requests=external,js_errors=errors))
 print('DEMO RECORDED',flush=True)
if __name__=='__main__':main()
