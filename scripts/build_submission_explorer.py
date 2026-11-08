"""검증된 지도 수치를 결과 중심의 오프라인 탐색 화면에 연결한다."""
from pathlib import Path
import sys,json,gzip,base64,re
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import sha
P=ROOT/'outputs/private';B=P/'competition_submission/icy_road_model'
def main():
 old=P/'weather_explorer_20261106_v13'
 payload=json.loads(gzip.decompress((old/'viewer_data.json.gz').read_bytes()))
 f=pd.read_csv(B/'results/sections/section_review.csv',float_precision='round_trip');index=f.loc[f.winter.eq(2024)].set_index('seg_id')
 for r in payload['rows']:
  q=index.loc[r['id']];r['km']=[None if pd.isna(q[x]) else float(q[x]) for x in ['estimated_km_lo','estimated_km_hi']]
 payload['model_note']='기상 추정값은 지역 전체를 제외한 평가로 비교했습니다. 가까운 구간이 같은 기상 입력을 공유할 수 있습니다.'
 packed=gzip.compress(json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(),mtime=0);(B/'viewer_data.json.gz').write_bytes(packed)
 t=(ROOT/'src/templates/weather_explorer.html').read_text(encoding='utf8')
 t=t.replace('__PAYLOAD__',base64.b64encode(packed).decode('ascii')).replace('../__SOURCE__/','results/weather/')
 header='''<header><nav class="topnav" aria-label="분석 탐색"><a class="active" href="index.html">기상 지도</a><a href="#temperature">노면온도 평가</a><a href="maps/sections.html">구간 검토</a><a href="report/analysis_report.pdf">분석 보고서</a><a href="demo/index.html">실행 영상</a></nav><h1>전북 고속도로 겨울 기상 지도</h1><p>500m 구간의 두 겨울 기온·습도·풍속을 비교합니다. 도로를 선택하면 일별 변화와 입력 자료의 상태를 확인할 수 있습니다.</p></header>'''
 t=re.sub(r'<header>.*?</header>',lambda _:header,t,count=1,flags=re.S)
 t=t.replace('</style>','</style><link rel="stylesheet" href="assets/site.css">',1)
 t=t.replace('<option value="0">평균 기온','<option value="0" selected>평균 기온').replace('<option value="1" selected>평균 상대습도','<option value="1">평균 상대습도')
 t=t.replace('<div id="segmentId" class="id"></div>','<p id="chainage" class="chainage"></p><div id="segmentId" class="id"></div>')
 tick=chr(96);dollar=chr(36)
 oldoption=tick+dollar+'{r.route} · '+dollar+'{r.flow} · '+dollar+'{r.id.slice(0,8)}'+tick
 newoption="r.route.replace('고속국도','')+' · '+r.flow+' · '+(r.km?.[0]===null?'이정 미산정':r.km[0].toFixed(1)+'-'+r.km[1].toFixed(1)+'km')"
 t=t.replace(oldoption,newoption)
 t=t.replace("el('segmentId').textContent=id;","el('segmentId').textContent=id;el('chainage').textContent=r.km?.[0]===null?'이정 미산정':'추정 이정 '+r.km[0].toFixed(2)+'-'+r.km[1].toFixed(2)+' km';")
 t=t.replace('현재 버전의 Chrome 또는 Edge에서 열어 주세요.','Chrome 또는 Edge에서 열어 주세요.')
 t=t.replace("el('modelNote').textContent=data.model_note;",'')
 t=t.replace('<table><thead><tr><th>입력 진단','<details><summary>입력 자료의 가용성과 범위</summary><table><thead><tr><th>입력 진단',1)
 t=t.replace('</tbody></table><p id="sourceNote"','</tbody></table></details><p id="sourceNote"',1)
 before=t.index('<section class="panel lower">');after=t.index('</section></div></main>',before)
 section='''<section class="analysis" id="temperature"><h2>관측과 비교한 노면온도</h2><p class="lead">부곡교·해전·삼봉을 학습에서 제외하고 두 겨울의 같은 10분 시각을 대조했습니다.</p><div class="analysis-grid"><div><img src="report/figures/road_temperature.png" alt="부곡교 해전 삼봉의 관측과 추정 노면온도 밀도 그래프"><p class="caption">관측·추정이 같으면 점선 위에 놓입니다. 전체 103,659 유효쌍의 밀도입니다.</p></div><div><p class="metric-line">MAE 지점 평균 0.978°C</p><table><thead><tr><th>지점</th><th>MAE</th><th>BIAS</th></tr></thead><tbody><tr><td>부곡교</td><td>1.113°C</td><td>-0.970°C</td></tr><tr><td>해전</td><td>1.044°C</td><td>-0.977°C</td></tr><tr><td>삼봉</td><td>0.776°C</td><td>+0.300°C</td></tr></tbody></table><p>부곡교와 해전은 낮은 쪽 편향이 남습니다. 0°C 부근에서는 평균 오차와 함께 지점별 편향도 살펴야 합니다.</p><a href="results/evaluation/observations_predictions.csv" download>관측·추정 대조 CSV</a></div></div></section><section class="analysis"><h2>결빙 판정과 관측 결빙일</h2><img src="report/figures/icing_calendar.png" alt="부곡교에서 관측과 판정의 결빙일을 두 겨울에 걸쳐 비교한 달력"><p>실제 결빙은 부곡교의 19일에서 관측됐고 판정은 44일에서 발생했습니다. 날짜별 평균 F1은 0.033, 정밀도는 0.0195입니다. 기온·수분의 대용조건만으로 결빙을 확정하기에는 오경보가 많습니다.</p><p class="data-note">실제 Ice가 없는 해전·삼봉은 분류 평균에서 제외했습니다. 지표별 날짜 수와 결측 처리는 보고서에 기재했습니다.</p></section><section class="analysis"><h2>어디에 관측을 보완할 것인가</h2><div class="analysis-grid"><div><img src="report/figures/inspection_locations.png" alt="이정에 따라 공개 취약구간과 추가 계측·시설 확인 범위를 비교한 그림"></div><div><p class="lead">두 겨울의 저온·수분 빈도, 교량·선형 정보, 공개 취약구간 목록을 대조했습니다.</p><p>조건이 겹치는 500m 22구간을 방향별 11개 연속 범위로 묶었습니다. 현장의 수분·배수·시설 범위를 확인할 후보이며 위험이 입증된 새 지정 구간은 아닙니다.</p><a class="button" href="maps/sections.html">구간과 선정 근거 확인</a><p class="data-note">843개 구간은 같은 기상 입력을 공유할 수 있습니다. 두 겨울은 장기 기후값을 대체하지 않습니다.</p></div></div></section>'''
 t=t[:before]+section+t[after+len('</section>'):]
 t=re.sub(r'<footer>.*?</footer>','<footer>자료: 2024/25·2025/26 겨울 RWIS·AWS·ASOS, 도로 중심선, 한국도로공사 공개 목록. 지도는 과거 자료에 대한 추정 결과입니다.</footer>',t,flags=re.S)
 (B/'index.html').write_text(t,encoding='utf8')
 receipt=dict(status='built_pending_browser_review',segments=843,winter_rows=1686,daily_rows=202320,
 source=(B/'results/weather').relative_to(ROOT).as_posix(),source_data_sha256={n:sha(B/'results/weather'/n) for n in ['weather_segments_500m.csv','weather_segment_daily.csv.gz','weather_segments.gpkg']},
 files={n:sha(B/n) for n in ['index.html','viewer_data.json.gz']},display_daily_decimal_places=6,external_dependencies=False)
 (B/'summary.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 print('EXPLORER BUILT',len(payload['rows']),'segments',flush=True)
if __name__=='__main__':main()
