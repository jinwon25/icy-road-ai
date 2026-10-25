"""현재 확장 후보의 실행 화면·영상·노트북·지도와 실제 출력의 일치를 검증한다."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import cv2
import joblib
import nbformat
import numpy as np
import pandas as pd
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.build_extended_candidate import OUT,read,write

TEMPLATE='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>노면온도 추정 | 실행 검토</title><style>
:root{font-family:"Malgun Gothic",sans-serif;color:#153447;background:#edf3f5}*{box-sizing:border-box}body{margin:0;padding:32px 20px}main{max-width:1050px;margin:auto}header{display:flex;justify-content:space-between;gap:20px;align-items:start}.eyebrow{letter-spacing:.12em;color:#507080;font-size:12px}h1{word-break:keep-all;font-size:30px;letter-spacing:-1px;margin:12px 0}p{line-height:1.7}a{color:#096b75}.pill{background:#d5e9e9;border-radius:20px;padding:9px 16px;white-space:nowrap;font-size:13px}.panel{background:white;border:1px solid #d2e0e6;border-radius:16px;padding:24px;margin-top:22px}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.label{font-size:13px;color:#5e7786}.metric{font-size:29px;font-weight:700;margin:10px 0;color:#087e85}.note{font-size:13px;color:#526a77;line-height:1.7}.reference{color:#855b30}#chart{width:100%;height:auto;display:block}input{width:100%;accent-color:#087e85;cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eff5f6;padding:15px;border-radius:8px;font-size:12px;line-height:1.7}summary{cursor:pointer;font-weight:700}footer{font-size:12px;line-height:1.8;color:#607481;margin-top:22px}.legend{display:flex;gap:20px;font-size:13px;flex-wrap:wrap}.dot{display:inline-block;width:24px;height:3px;background:#087e85;vertical-align:middle;margin-right:6px}.brown{background:#b18044}@media(max-width:650px){body{padding:20px 12px}header{display:block}.pill{display:inline-block;margin:10px 0}.cards{grid-template-columns:1fr}.panel{padding:18px}h1{font-size:25px}.metric{font-size:25px}}
</style><main><header><div><div class="eyebrow">ICY ROAD / LOCAL INFERENCE</div><h1>관측 장비가 없는 도로의 온도 추정</h1><p>공공 기상과 과거 열 상태로 계산한 실제 실행 결과입니다.</p></div><span class="pill">외부 통신 없는 예제</span></header>
<section class="panel"><div class="label">12207 지점 · 12시간 이력 뒤 하루 144개 시각</div><h2 id="time"></h2><div class="cards"><div><div class="label">현재 노면온도 추정</div><div class="metric" id="temperature"></div><div class="note">기상·열 이력과 ASOS 태양 위치 사용</div></div><div><div class="label">결빙 판정에 사용하는 기준 온도</div><div class="metric reference" id="reference"></div><div class="note">별도 검증을 거쳐 유지한 v2 모델</div></div><div><div class="label">저온·수분 조건 판정</div><div class="metric" id="ice"></div><div class="note" id="evidence"></div></div></div></section>
<section class="panel"><div class="legend"><span><i class="dot"></i>현재 온도</span><span><i class="dot brown"></i>결빙 기준 온도</span><span>점선: 0°C</span></div><svg id="chart" viewBox="0 0 960 280" role="img" aria-label="실제 하루 출력의 현재 온도와 결빙 기준 온도"></svg><label for="slot">시각 선택</label><input id="slot" type="range" min="0" max="143" value="0" aria-label="10분 단위 시각 선택"><p class="note" id="history"></p></section>
<section class="panel"><p>현재 온도 모델의 개선만으로 결빙 판정을 바꾸지 않았습니다. 두 온도는 목적과 검증 결과가 다른 별도 모델의 출력입니다. 판정 1은 추정 저온·수분 조건이며 실제 빙판·사고확률을 뜻하지 않습니다. 판정 0도 안전 보장은 아닙니다.</p><details><summary>실제 실행 명령과 로그</summary><pre id="log"></pre></details><p><a href="../reports/current/current_report.pdf">현재 검토 보고서</a> · <a href="../data/example_predictions.csv">원래 출력 CSV</a> · <a href="extended_inference.mp4">같은 출력의 시각화 영상</a></p></section>
<footer>학습 범위 내 지점의 실행 예제이며 독립 성능평가가 아닙니다. 결측은 NA로 유지합니다. 모델 간 온도 차이는 보정된 신뢰구간이 아닙니다. 실제 제출·외부 공개는 수행하지 않았습니다.</footer></main>
<script>const rows=__ROWS__;document.getElementById('log').textContent=__LOG__;const svg=document.getElementById('chart'),NS='http://www.w3.org/2000/svg';const values=rows.flatMap(r=>[r.estimated_road_temp_c,r.icing_reference_temperature_c]).filter(x=>x!==null);const lo=Math.min(-1,...values)-.8,hi=Math.max(1,...values)+.8;let W=960;const xx=i=>42+i/143*(W-67),yy=v=>230-(v-lo)/(hi-lo)*200;let marker;function line(tag,attrs){const e=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));svg.appendChild(e);return e}function draw(){W=Math.max(300,svg.getBoundingClientRect().width);svg.setAttribute('viewBox','0 0 '+W+' 280');svg.replaceChildren();for(let i=0;i<5;i++){let v=lo+(hi-lo)*i/4;line('line',{x1:42,y1:yy(v),x2:W-25,y2:yy(v),stroke:'#e2eaee'});line('text',{x:4,y:yy(v)+4,fill:'#637d88','font-size':12}).textContent=v.toFixed(1)}line('line',{x1:42,y1:yy(0),x2:W-25,y2:yy(0),stroke:'#849aa4','stroke-dasharray':'5 5'});for(const [key,color] of [['icing_reference_temperature_c','#b18044'],['estimated_road_temp_c','#087e85']]){let d='',previous=false;rows.forEach((r,i)=>{if(r[key]===null){previous=false;return}d+=(previous?'L':'M')+xx(i)+','+yy(r[key])+' ';previous=true});line('path',{d,fill:'none',stroke:color,'stroke-width':2.5})}for(const [i,t] of [[0,'00:00'],[36,'06:00'],[72,'12:00'],[108,'18:00'],[143,'23:50']])line('text',{x:xx(i),y:258,'text-anchor':'middle',fill:'#637d88','font-size':12}).textContent=t;marker=line('line',{x1:42,x2:42,y1:25,y2:230,stroke:'#294c5a','stroke-width':1});}const show=x=>x===null?'NA':x.toFixed(2)+' °C';function update(){let i=Number(document.getElementById('slot').value),r=rows[i];document.getElementById('time').textContent=r.time+' KST';document.getElementById('temperature').textContent=show(r.estimated_road_temp_c);document.getElementById('reference').textContent=show(r.icing_reference_temperature_c);document.getElementById('ice').textContent=r.predicted_ice===null?'NA':String(r.predicted_ice);document.getElementById('evidence').textContent={cold_wet_consensus:'두 기준 모델 모두 저온이며 수분 조건 충족',cold_wet_disagreement:'평균 기준 저온·수분 충족, 기준 모델 간 차이 있음',criterion_not_met:'저온·수분 기준 미충족',insufficient_input:'입력 부족으로 판정하지 않음'}[r.condition_evidence];document.getElementById('history').textContent='사용 가능한 과거 기상 특징 '+r.weather_history_available_features+' / '+r.weather_history_expected_features+'개 · 시간은 KST입니다.';marker.setAttribute('x1',xx(i));marker.setAttribute('x2',xx(i))}document.getElementById('slot').addEventListener('input',update);window.addEventListener('resize',()=>{draw();update()});draw();update();</script></html>'''


def maps():
    from scripts import complete_two_winter_delivery as old
    import geopandas as gpd
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    mapping=read(OUT/'figures/shapefile_column_dictionary.json');mapping['estimated_temp_mean_c']='t_mean_c'
    write(OUT/'figures/shapefile_column_dictionary.json',mapping)
    old.OUT=OUT;old.maps()
    summary=pd.read_csv(OUT/'data/segment_candidate_summary.csv',dtype={'seg_id':str},float_precision='round_trip');checks=[]
    norm=Normalize(float(summary.estimated_temp_mean_c.min()),float(summary.estimated_temp_mean_c.max()))
    for scale in [500,1000]:
        fig,axes=plt.subplots(1,2,figsize=(10,7.2),layout='constrained')
        for ax,winter in zip(axes,[2024,2025]):
            stem=OUT/f'figures/candidate_conditions_{scale}m_{winter}';expected=summary.loc[summary.scale_m.eq(scale)&summary.winter.eq(winter)].sort_values('seg_id')
            for suffix in ['.gpkg','.shp']:
                actual=gpd.read_file(stem.with_suffix(suffix)).sort_values('seg_id')
                assert actual.seg_id.tolist()==expected.seg_id.tolist()
                for column in expected.select_dtypes(include='number'):
                    if suffix=='.shp' and column not in mapping:continue
                    np.testing.assert_allclose(actual[mapping[column] if suffix=='.shp' else column],expected[column],rtol=0,atol=1e-9,equal_nan=True)
                checks.append(dict(scale_m=scale,winter=winter,format=suffix,sha256=sha(stem.with_suffix(suffix)),all_exported_numeric_columns_verified=True))
            geom=gpd.read_file(stem.with_suffix('.gpkg')).to_crs(5179)
            geom.plot(column='estimated_temp_mean_c',ax=ax,cmap='viridis',norm=norm,linewidth=2)
            ax.set_title(f'{winter}/{str(winter+1)[-2:]} 겨울');ax.set_axis_off()
        fig.suptitle(f'{scale:,}m 구간의 겨울 평균 추정 노면온도',fontsize=17)
        fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap='viridis'),ax=axes,shrink=.7,label='유효 시점 평균 추정 온도 (°C)')
        fig.supxlabel('동일 색상 범위 | 현재 v3 온도 모델 | 현장 노면 관측값이 아님',fontsize=10)
        fig.savefig(OUT/f'figures/extended_temperature_map_{scale}m.jpg',dpi=180);plt.close(fig)
    write(OUT/'validation/extended_maps.json',dict(status='all_spatial_numeric_attributes_readback_passed',checks=checks,
        temperature_shapefile_field='t_mean_c',numeric_absolute_tolerance=1e-9,summary_sha256=sha(OUT/'data/segment_candidate_summary.csv')))
    temperature_maps()


def temperature_maps():
    import geopandas as gpd
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False})
    summary=pd.read_csv(OUT/'data/segment_candidate_summary.csv',float_precision='round_trip')
    norm=Normalize(float(summary.estimated_temp_mean_c.min()),float(summary.estimated_temp_mean_c.max()))
    for scale in [500,1000]:
        fig,axes=plt.subplots(1,2,figsize=(10,7.2),layout='constrained')
        for ax,winter in zip(axes,[2024,2025]):
            geom=gpd.read_file(OUT/f'figures/candidate_conditions_{scale}m_{winter}.gpkg').to_crs(5179)
            geom.plot(column='estimated_temp_mean_c',ax=ax,cmap='viridis',norm=norm,linewidth=2)
            for route,lines in geom.groupby('route_nm'):
                center=lines.geometry.union_all().centroid
                ax.annotate(str(route),(center.x,center.y),xytext=(9,5),textcoords='offset points',fontsize=9,
                    bbox=dict(facecolor='white',edgecolor='none',alpha=.8,pad=2))
            left,bottom,right,top=geom.total_bounds;bx=left+4000;by=bottom-8000
            ax.plot([bx,bx+20000],[by,by],color='#334e60',linewidth=2)
            ax.text(bx+10000,by-2500,'20 km',ha='center',va='top',fontsize=8,color='#334e60')
            ax.annotate('N',xy=(.08,.94),xytext=(.08,.83),xycoords='axes fraction',ha='center',fontsize=11,
                arrowprops=dict(arrowstyle='-|>',color='#334e60'),color='#334e60')
            ax.set_title(f'{winter}/{str(winter+1)[-2:]} 겨울');ax.set_axis_off()
        fig.suptitle(f'{scale:,}m 구간의 겨울 평균 추정 노면온도',fontsize=17)
        fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap='viridis'),ax=axes,shrink=.7,label='유효 시점 평균 추정 온도 (°C)')
        fig.supxlabel('동일 색상 범위 | 현재 v3 온도 모델 | 현장 노면 관측값이 아님',fontsize=10)
        fig.savefig(OUT/f'figures/extended_temperature_map_{scale}m.jpg',dpi=180);plt.close(fig)


def demo():
    dest=OUT/'validation/extended_cli.csv'
    if dest.exists():raise FileExistsError('Preserve completed CLI example')
    (OUT/'demo').mkdir(exist_ok=True)
    command=['code/predict.py','--input','data/weather_example.csv','--output','validation/extended_cli.csv','--output-start','2024-12-15','--output-end','2024-12-16']
    run=subprocess.run([sys.executable,'-X','utf8',*command],cwd=OUT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    log='python -X utf8 '+' '.join(command)+'\n'+run.stdout.decode('utf-8');assert run.returncode==0,log
    frame=pd.read_csv(dest,float_precision='round_trip',dtype={'station':str,'predicted_ice':'Int64'},parse_dates=['time']);assert len(frame)==144
    from src.extended_runtime import infer
    plan=read(OUT/'extended_training_plan.json');models={r:[joblib.load(OUT/'model'/(s['name']+'.joblib')) for s in plan['models'] if s['role']==r] for r in ['temperature','icing_reference']}
    full=pd.read_parquet(OUT/'data/training_extended_temperature.parquet').loc[lambda f:f.station.eq('12207')].drop(columns='road_temp').reset_index(drop=True)
    expected=infer(full,models['temperature'],models['icing_reference'],plan['temperature_feature_kind'],plan['temperature_weights'])
    expected=expected.loc[expected.time.ge('2024-12-15')&expected.time.lt('2024-12-16')].reset_index(drop=True)
    pd.testing.assert_frame_equal(frame,expected,check_exact=True)
    shutil.copy2(dest,OUT/'data/example_predictions.csv');records=frame.copy();records.time=records.time.astype(str)
    rows=records.astype(object).where(records.notna(),None).to_dict('records')
    (OUT/'demo/index.html').write_text(TEMPLATE.replace('__ROWS__',json.dumps(rows,ensure_ascii=False,allow_nan=False)).replace('__LOG__',json.dumps(log,ensure_ascii=False)),'utf-8')
    (OUT/'demo/execution_log.txt').write_text(log,'utf-8')
    font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',24);title=ImageFont.truetype('C:/Windows/Fonts/malgunbd.ttf',37);small=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',18)
    video=OUT/'demo/extended_inference.mp4';writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),12,(1280,720));assert writer.isOpened()
    values=frame[['estimated_road_temp_c','icing_reference_temperature_c']].to_numpy(float);lo=min(-1,float(np.nanmin(values)))-1;hi=max(1,float(np.nanmax(values)))+1
    xy=lambda i,v:(70+1140*i/143,515-250*(v-lo)/(hi-lo))
    for i,r in enumerate(frame.itertuples()):
        im=Image.new('RGB',(1280,720),'#edf3f5');d=ImageDraw.Draw(im)
        d.text((65,40),'기상 이력으로 추정한 노면온도',font=title,fill='#173246');d.text((65,103),str(r.time)+' KST · 지점 12207',font=font,fill='#526d7b')
        d.text((65,164),f'현재 추정 {r.estimated_road_temp_c:.2f} °C',font=font,fill='#087e85');d.text((530,164),f'결빙 기준 {r.icing_reference_temperature_c:.2f} °C',font=font,fill='#986b36')
        for k,color in [(1,'#b18044'),(0,'#087e85')]:d.line([xy(j,v) for j,v in enumerate(values[:,k])],fill=color,width=3)
        d.line([(xy(0,0)[0],xy(0,0)[1]),(xy(143,0)[0],xy(143,0)[1])],fill='#9eafb7',width=1)
        xx=xy(i,0)[0];d.line([(xx,245),(xx,530)],fill='#294c5a',width=2)
        d.text((65,565),f'저온·수분 조건 판정 {r.predicted_ice} · 이력 특징 {r.weather_history_available_features}/{r.weather_history_expected_features}개',font=font,fill='#173246')
        d.text((65,625),'실제 출력 144행의 시각화 · 학습 범위 내 예제 · 독립평가 또는 브라우저 녹화 아님',font=small,fill='#526d7b')
        d.text((65,658),'조건 판정은 관측 결빙·사고확률과 다릅니다. 두 온도는 별도 모델의 출력입니다.',font=small,fill='#526d7b')
        writer.write(cv2.cvtColor(np.asarray(im),cv2.COLOR_RGB2BGR))
        if i in [0,72,143]:im.save(OUT/f'demo/frame_{i:03}.png')
    writer.release();cap=cv2.VideoCapture(str(video));count=0
    while True:
        ok,img=cap.read()
        if not ok:break
        assert img.shape[:2]==(720,1280);count+=1
    cap.release();assert count==144
    write(OUT/'validation/extended_demo.json',dict(status='actual_cli_full_history_comparison_and_video_decode_passed',input_rows=216,output_rows=144,
        full_station_history_matches_exactly=True,command=command,html_sha256=sha(OUT/'demo/index.html'),video_frames=count,video_seconds=12,video_sha256=sha(video)))


def notebook():
    cells=[]
    def md(s):cells.append(nbformat.v4.new_markdown_cell(s))
    def code(s):cells.append(nbformat.v4.new_code_cell(s))
    md('# 확장 노면온도 모델 제출 검토\n\n현재 v3의 고정 학습 계획, 실제 추론, 지역 제외 개발 지표와 제출 CSV를 검산합니다. 기본 실행은 재학습하지 않습니다. 보호 3곳의 정답은 포함하지 않습니다.')
    code("""from pathlib import Path
import json, sys
import joblib, numpy as np, pandas as pd
ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p/'extended_training_plan.json').exists())
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.extended_runtime import infer
from src.submission_io import read_weather
from src.offline_runtime import deny_network
from src.temperature_transfer import regression_report
from src.runtime_metrics import runtime_daily
read = lambda p: json.loads((ROOT/p).read_text('utf-8'))
plan = read('extended_training_plan.json')
assert not plan['protected_outcomes_used'] and not plan['new_independent_assessment']
plan['periods']""")
    md('## 1. 포함 자료와 최종 모델\n\n허용 23곳의 두 겨울 원시 794,545행에서 과거 특징을 먼저 계산합니다. 입력·온도 정답이 모두 있는 최종 학습 쌍은 793,149행입니다. 온도와 결빙 기준 모델의 학습 입력을 구분합니다.')
    code("""for role, entry in plan['training_sources'].items():
    assert sha(ROOT/entry['file']) == entry['sha256']
    identities = pd.read_parquet(ROOT/entry['file'], columns=['station','time'])
    assert set(identities.station) == set(plan['allowed_stations'])
    assert not set(identities.station) & {'12410','33411','23402'}
receipts = read('model/refit_receipt.json')
for entry in receipts['models']:
    assert sha(ROOT/'model'/(entry['name']+'.joblib')) == entry['sha256']
pd.DataFrame(receipts['models'])[['name','role','rows']]""")
    md('## 2. 과거 이력과 실제 추론\n\n216행 입력의 첫 72행은 이력 구성용입니다. 예측 후 하루 144행만 선택합니다. 학습 범위 내 예제이므로 독립 성능평가가 아닙니다.')
    code("""models = {r:[joblib.load(ROOT/'model'/(s['name']+'.joblib')) for s in plan['models'] if s['role']==r] for r in ['temperature','icing_reference']}
with deny_network() as attempts:
    actual = infer(read_weather(ROOT/'data/weather_example.csv'), models['temperature'], models['icing_reference'], plan['temperature_feature_kind'], plan['temperature_weights'])
actual = actual.loc[actual.time.ge('2024-12-15') & actual.time.lt('2024-12-16')].reset_index(drop=True)
expected = pd.read_csv(ROOT/'data/example_predictions.csv', float_precision='round_trip', dtype={'station':str,'predicted_ice':'Int64'}, parse_dates=['time'])
pd.testing.assert_frame_equal(actual, expected, check_exact=True)
assert not attempts and len(actual)==144
actual[['time','estimated_road_temp_c','icing_reference_temperature_c','predicted_ice']].head()""")
    md('## 3. 지역을 제외한 개발 지표\n\n평가 지역의 두 겨울 전체를 학습에서 제외한 예측입니다. 여러 후보를 같은 9곳에서 비교했으므로 새 독립 평가로 표현하지 않습니다. 현재 온도와 유지된 결빙 판정을 별도로 검산합니다.')
    code("""frame = pd.read_parquet(ROOT/'research/extended/audited_predictions.parquet')
audit = read('research/extended/audit.json')
assert sha(ROOT/'research/extended/audited_predictions.parquet') == audit['runtime_prediction_sha256']
temperature = regression_report(frame, frame.temperature_both)
ice, stations, days = runtime_daily(frame, frame.physical_both)
np.testing.assert_allclose(temperature['pooled']['mae'], audit['temperature']['regression']['pooled']['mae'], atol=1e-12, rtol=0)
np.testing.assert_allclose(ice['f1_fixed_population'], audit['physical']['both']['all']['f1_fixed_population'], atol=1e-12, rtol=0)
print('온도 MAE:',temperature['pooled']['mae'])
print('일별 지점 F1:',ice['f1_fixed_population'])
pd.DataFrame(temperature['stations']).T""")
    md('## 4. 제출 CSV와 보호 예측\n\n138개 공유 기상 그룹을 위치 인덱스로 연결합니다. 구간 수는 독립 검증 표본 수가 아닙니다. 보호 예측에는 관측 정답이 없고 입력 부족 18행은 NA입니다.')
    code("""exports = read('exports/manifest.json')
assert exports['development_scope']=='extended_two_winter'
for table in exports['tables']:
    assert sha(ROOT/'exports'/table['file']) == table['sha256']
protected = pd.read_csv(ROOT/'exports/protected_predictions_10min.csv', dtype={'station':str})
assert len(protected)==103680 and protected.predicted_ice.isna().sum()==18
assert not {'road_temp','ice','observed_ice','actual_ice'} & set(protected)
pd.DataFrame(exports['tables'])[['file','rows','bytes']]""")
    md('## 재학습\n\n`python -X utf8 code/train.py --output validation/my_refit`은 포함 자료에서 고정 모델을 새 폴더에 적합합니다. 실제 독립 재학습의 모델별 해시 일치는 `validation/extended_delivery.json`에 기록합니다. 전체 탐색 재실행은 원 비공개 작업 공간의 자료가 필요합니다. 현재 보고서는 `reports/current/current_report.pdf`, 실행 화면은 `demo/index.html`입니다.')
    target=OUT/'notebooks/extended_submission_review.ipynb';target.parent.mkdir(exist_ok=True)
    book=nbformat.v4.new_notebook(cells=cells,metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python','version':'3.11'}});nbformat.write(book,target)
    shutil.copy2(target,ROOT/'notebooks/extended_submission_review.ipynb')


def browser():
    from playwright.sync_api import sync_playwright
    target=OUT/'validation/extended_browser.json'
    if target.exists():raise FileExistsError('Preserve browser verification')
    errors=[];external=[];f=pd.read_csv(OUT/'data/example_predictions.csv')
    with sync_playwright() as p:
        app=p.chromium.launch(headless=True);page=app.new_page(viewport={'width':1280,'height':1000})
        page.on('pageerror',lambda e:errors.append(str(e)))
        def route(r):
            if r.request.url.startswith(('http://','https://')):external.append(r.request.url);r.abort()
            else:r.continue_()
        page.route('**/*',route);page.goto((OUT/'demo/index.html').as_uri());page.wait_for_selector('#temperature')
        for i in [0,36,72,143]:
            page.locator('#slot').evaluate('(e,v)=>{e.value=v;e.dispatchEvent(new Event("input"));}',i)
            assert page.locator('#time').inner_text()==f.time.iloc[i]+' KST'
            for key,col in [('temperature','estimated_road_temp_c'),('reference','icing_reference_temperature_c')]:assert page.locator('#'+key).inner_text()==f'{f[col].iloc[i]:.2f} °C'
            assert page.locator('#ice').inner_text()==str(f.predicted_ice.iloc[i])
        page.screenshot(path=str(OUT/'validation/extended_desktop.png'),full_page=True);page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth');page.screenshot(path=str(OUT/'validation/extended_mobile.png'),full_page=True);app.close()
    assert not errors and not external
    write(target,dict(status='extended_browser_verified',slider_slots=[0,36,72,143],console_errors=errors,external_requests=external,
        mobile_no_horizontal_overflow=True,html_sha256=sha(OUT/'demo/index.html'),visual_review_pending=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['maps','temperature_maps','demo','notebook','browser'],required=True);globals()[p.parse_args().stage]()
