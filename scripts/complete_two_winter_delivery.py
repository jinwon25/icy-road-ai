"""검증된 두 겨울 후보의 지도·실행 예제·노트북을 같은 모델에 맞춘다."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import cv2
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
import nbformat
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.build_submission_candidate_demo import TEMPLATE
OUT=ROOT/'outputs/private/submission_candidate_20261024_v2'

def read(p):return json.loads(p.read_text('utf-8'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')

def maps():
    summary=pd.read_csv(OUT/'data/segment_candidate_summary.csv',dtype={'seg_id':str},float_precision='round_trip')
    mapping=read(OUT/'figures/shapefile_column_dictionary.json');checks=[]
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False})
    norm=Normalize(0,float(summary.cold_wet_fraction.max()))
    for scale in [500,1000]:
        fig,axes=plt.subplots(1,2,figsize=(10,7.2),layout='constrained')
        for ax,winter in zip(axes,[2024,2025]):
            stem=OUT/f'figures/candidate_conditions_{scale}m_{winter}'
            layers=gpd.list_layers(stem.with_suffix('.gpkg')).name.tolist()
            geom=gpd.read_file(stem.with_suffix('.gpkg'),layer=stem.name if stem.name in layers else 'candidate_conditions')[['seg_id','geometry']]
            geom.seg_id=geom.seg_id.astype(str)
            part=summary.loc[summary.scale_m.eq(scale)&summary.winter.eq(winter)]
            merged=geom.merge(part,on='seg_id',validate='one_to_one')
            assert len(merged)==len(part) and merged.geometry.notna().all()
            temporary=stem.with_suffix('.new.gpkg')
            merged.to_file(temporary,driver='GPKG',layer='candidate_conditions',mode='w')
            temporary.replace(stem.with_suffix('.gpkg'))
            narrow=merged[[*mapping,'geometry']].rename(columns=mapping)
            narrow.to_file(stem.with_suffix('.shp'),driver='ESRI Shapefile',encoding='UTF-8')
            for suffix,col in [('.gpkg','cold_wet_fraction'),('.shp','cw_frac')]:
                actual=gpd.read_file(stem.with_suffix(suffix)).sort_values('seg_id')
                expected=merged.sort_values('seg_id')
                assert actual.seg_id.tolist()==expected.seg_id.tolist()
                np.testing.assert_allclose(actual[col],expected.cold_wet_fraction,rtol=0,atol=1e-12)
                assert actual.crs==merged.crs
                checks.append(dict(scale_m=scale,winter=winter,format=suffix,rows=len(actual),sha256=sha(stem.with_suffix(suffix))))
            projected=merged.to_crs(5179)
            projected.plot(column='cold_wet_fraction',ax=ax,cmap='viridis',norm=norm,linewidth=2)
            for route,lines in projected.groupby('route_nm'):
                center=lines.geometry.union_all().centroid
                ax.annotate(str(route),(center.x,center.y),xytext=(9,5),textcoords='offset points',fontsize=9,
                    bbox=dict(facecolor='white',edgecolor='none',alpha=.8,pad=2))
            left,bottom,right,top=projected.total_bounds
            bx=left+4000;by=bottom-8000
            ax.plot([bx,bx+20000],[by,by],color='#334e60',linewidth=2)
            ax.text(bx+10000,by-2500,'20 km',ha='center',va='top',fontsize=8,color='#334e60')
            ax.annotate('N',xy=(.08,.94),xytext=(.08,.83),xycoords='axes fraction',ha='center',fontsize=11,
                arrowprops=dict(arrowstyle='-|>',color='#334e60'),color='#334e60')
            ax.set_title(f'{winter}/{str(winter+1)[-2:]} 겨울');ax.set_axis_off()
        fig.suptitle(f'{scale:,}m 구간의 저온·수분 조건 노출',fontsize=17)
        fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap='viridis'),ax=axes,shrink=.7,label='판정 1 / 유효 판정 슬롯')
        fig.supxlabel('동일 색상 범위 | 두 겨울 학습 모델 | 관측 결빙률·사고확률이 아님',fontsize=10)
        fig.savefig(OUT/f'figures/candidate_condition_map_{scale}m.jpg',dpi=180);plt.close(fig)
    write(OUT/'validation/two_winter_maps.json',dict(status='map_attributes_readback_passed',files=checks,source_sha256=sha(OUT/'data/segment_candidate_summary.csv')))

def demo():
    dest=OUT/'validation/two_winter_cli.csv'
    if dest.exists():raise FileExistsError('Preserve actual execution')
    command=['code/predict.py','--input','data/weather_example.csv','--output','validation/two_winter_cli.csv']
    run=subprocess.run([sys.executable,'-X','utf8',*command],cwd=OUT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
    log='python -X utf8 '+' '.join(command)+'\n'+run.stdout.decode('utf-8')
    assert run.returncode==0,log
    actual=pd.read_csv(dest,float_precision='round_trip');expected=pd.read_csv(OUT/'data/example_predictions.csv',float_precision='round_trip')
    pd.testing.assert_frame_equal(actual,expected,check_exact=True)
    records=actual.replace({np.nan:None}).to_dict('records')
    template=TEMPLATE.replace('첫 겨울 자료','두 겨울 자료').replace('../reports/결빙_분석_제출후보_보고서.pdf','../reports/current/current_report.pdf')
    (OUT/'demo/index.html').write_text(template.replace('__ROWS__',json.dumps(records,ensure_ascii=False,allow_nan=False)).replace('__LOG__',json.dumps(log,ensure_ascii=False)),'utf-8')
    (OUT/'demo/execution_log.txt').write_text(log,'utf-8')
    # 화면 녹화라고 표현하지 않는다. 실제 CSV 144행의 시간 순서 시각화이다.
    video=OUT/'demo/two_winter_inference.mp4';w,h=1280,720
    writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),12,(w,h));assert writer.isOpened()
    font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',25)
    bold=ImageFont.truetype('C:/Windows/Fonts/malgunbd.ttf',34)
    small=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',20)
    temps=actual.estimated_road_temp_c.to_numpy();low=min(-2,temps.min())-1;high=max(2,temps.max())+1
    x=lambda i:80+int(i*1110/143)
    y=lambda t:485-int((t-low)/(high-low)*270)
    for i,r in enumerate(records):
        im=Image.new('RGB',(w,h),'#f7f9fb');d=ImageDraw.Draw(im)
        d.text((65,38),'미관측 도로를 위한 기상 기반 노면 추정',font=bold,fill='#173246')
        d.text((65,95),'실제 CLI 출력의 시간 순서 시각화 · 두 겨울 학습 모델',font=font,fill='#476172')
        d.text((65,140),'학습 범위 내 예제: 12207 / 2024-12-15 · 새 지점 성능평가 아님',font=small,fill='#647783')
        d.line([(80,y(0)),(1190,y(0))],fill='#a5b5c2',width=2)
        d.text((15,y(0)-14),'0°C',font=small,fill='#647783')
        d.line([(x(j),y(t)) for j,t in enumerate(temps)],fill='#087f8c',width=4)
        for j,record in enumerate(records):
            if record['predicted_ice']==1:d.rectangle((x(j)-3,505,x(j)+3,519),fill='#c68432')
        d.line((x(i),195,x(i),525),fill='#173246',width=2)
        d.ellipse((x(i)-6,y(temps[i])-6,x(i)+6,y(temps[i])+6),fill='#087f8c')
        d.text((75,530),'00:00',font=small,fill='#647783');d.text((1110,530),'23:50',font=small,fill='#647783')
        d.text((65,580),f"{r['time']} KST     추정 {r['estimated_road_temp_c']:.2f}°C     판정 {int(r['predicted_ice'])}",font=font,fill='#173246')
        d.text((65,638),'주황: 저온·수분 조건 충족 | 관측 결빙·사고확률 아님 | 판정 0은 안전 보장 아님',font=small,fill='#766245')
        writer.write(cv2.cvtColor(np.asarray(im),cv2.COLOR_RGB2BGR))
        if i in [0,72,143]:im.save(OUT/f'demo/two_winter_frame_{i:03}.png')
    writer.release();cap=cv2.VideoCapture(str(video));decoded=0
    while True:
        ok,frame=cap.read()
        if not ok:break
        assert frame.shape[:2]==(720,1280);decoded+=1
    cap.release();assert decoded==144
    (OUT/'demo/README.md').write_text('# 두 겨울 모델 실행 예제\n\nindex.html은 외부 통신 없는 실제 예측 CSV의 탐색 화면입니다. two_winter_inference.mp4는 같은 실제 출력 144행을 12초로 시각화한 영상이며 브라우저 화면 녹화가 아닙니다. execution_log.txt가 CLI 실행 원문입니다. 기존 inference_demo.webm은 첫 겨울 모델의 역사 자료이므로 현재 데모로 사용하지 않습니다. 예제는 학습 범위 내 지점이며 성능평가가 아닙니다.\n','utf-8')
    write(OUT/'validation/two_winter_demo.json',dict(status='actual_cli_and_video_decode_passed',rows=len(actual),exact_csv_match=True,video_decoded_frames=decoded,video_seconds=12,video_sha256=sha(video),html_sha256=sha(OUT/'demo/index.html'),command=command))

def notebook():
    cells=[]
    def md(s):cells.append(nbformat.v4.new_markdown_cell(s))
    def code(s):cells.append(nbformat.v4.new_code_cell(s))
    md('# 두 겨울 모델 제출 검토\n\n포함 자료만으로 학습 범위, 실제 추론, 개발 지표를 검산합니다. 기본 실행은 재학습하지 않습니다. 보호 3곳의 정답은 사용하지 않습니다. 두 겨울은 반복 개발 자료이며 독립 최종평가가 아닙니다.')
    code("""from pathlib import Path
import json, sys
import joblib, numpy as np, pandas as pd
ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p/'training_plan.json').exists())
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.two_winter import validate
from src.runtime_metrics import runtime_daily as daily
from src.temperature_transfer import regression_report
from src.submission_runtime import infer
from src.submission_io import read_weather
from src.offline_runtime import deny_network
read = lambda p: json.loads((ROOT/p).read_text('utf-8'))
plan = read('training_plan.json')
assert plan['second_winter_training'] and not plan['protected_outcomes_used']
plan['periods']""")
    md('## 1. 학습 범위와 모델 무결성\n\n비보호 23곳의 두 겨울. 최종 적합 793,149행. 현재 온도 모델은 MSE·MAE 고정 평균이며 별도 분류기를 채택하지 않았습니다.')
    code("""training = validate(pd.read_parquet(ROOT/'data/training_weather_temperature.parquet'))
assert set(training.station) == set(plan['allowed_stations'])
assert not set(training.station) & {'12410','33411','23402'}
assert len(training) == 793149
assert sha(ROOT/'data/training_weather_temperature.parquet') == plan['training_data_sha256']
receipts = read('model/fit_receipts.json')
for receipt in receipts:
    assert sha(ROOT/'model'/(receipt['name']+'.joblib')) == receipt['model_sha256']
pd.DataFrame(receipts)[['name','training_rows','fit_seconds']]""")
    md('## 2. 외부 통신 없는 실제 추론\n\n학습 범위 내 예제 하루 144행을 실행합니다. 이 일치 검사는 성능평가가 아닙니다.')
    code("""models = [joblib.load(ROOT/'model'/(r['name']+'.joblib')) for r in receipts]
with deny_network() as attempts:
    prediction = infer(read_weather(ROOT/'data/weather_example.csv'), models)
assert not attempts
expected = pd.read_csv(ROOT/'data/example_predictions.csv', float_precision='round_trip', parse_dates=['time'], dtype={'station':str,'predicted_ice':'Int64'})
pd.testing.assert_frame_equal(prediction, expected, check_exact=True)
prediction.head()""")
    md('## 3. 공간 제외 개발 지표 검산\n\n아래는 최종 모델의 학습 내 오차가 아닙니다. 지역을 두 겨울 모두 제외한 별도 개발 예측입니다. 기존 시간 보류 자료를 개발로 편입했으므로 새 후보의 독립평가라고 해석하지 않습니다.')
    code("""frame = validate(pd.read_parquet(ROOT/'research/two_winter/audited_predictions.parquet'))
audit = read('research/two_winter/audit.json')
regression = regression_report(frame, frame.temperature_both)
summary = read('research/two_winter/summary.json')
np.testing.assert_allclose(regression['pooled']['mae'], summary['regression']['all']['both']['pooled']['mae'], atol=1e-12, rtol=0)
classification, stations, days = daily(frame, frame.physical_both)
np.testing.assert_allclose(classification['f1_fixed_population'], audit['physical']['both']['all']['f1_fixed_population'], atol=1e-12, rtol=0)
print('온도 MAE:', regression['pooled']['mae'])
print('일별 지점 F1:', classification['f1_fixed_population'])
pd.read_csv(ROOT/'research/two_winter/temperature_regions.csv')""")
    md('## 4. 제출 CSV와 원래 예측의 일치\n\n보호 예측 103,680행 중 입력 부족 18행은 NA를 유지합니다. 구간별 10분 자료는 그룹 CSV와 위치 인덱스를 연결합니다. 독립 검증 표본 수는 구간 수가 아닙니다.')
    code("""receipt = read('exports/manifest.json')
assert receipt['development_scope'] == 'two_winter'
for table in receipt['tables']:
    assert sha(ROOT/'exports'/table['file']) == table['sha256']
protected = pd.read_csv(ROOT/'exports/protected_predictions_10min.csv', dtype={'station':str})
assert len(protected)==103680 and protected.predicted_ice.isna().sum()==18
pd.DataFrame(receipt['tables'])[['file','rows','bytes']]""")
    md('## 재학습과 전체 연구의 경계\n\n`python -X utf8 code/train.py --output validation/my_refit`으로 포함 학습 자료에서 최종 두 모델을 새 폴더에 재학습할 수 있습니다. 기존 폴더는 덮어쓰지 않습니다. 전체 탐색 실험은 원 비공개 작업 공간의 데이터 경로를 사용하므로 이 패키지만으로 모든 과거 실험을 새로 실행한다고 주장하지 않습니다. 최신 보고서는 `reports/current/current_report.pdf`, 지도는 `figures/`, 데모는 `demo/index.html`입니다.')
    book=nbformat.v4.new_notebook(cells=cells,metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python','version':'3.11'}})
    target=OUT/'notebooks/two_winter_submission_review.ipynb';nbformat.write(book,target)
    shutil.copy2(target,ROOT/'notebooks/two_winter_submission_review.ipynb')

def browser():
    from playwright.sync_api import sync_playwright
    target=OUT/'validation/two_winter_browser.json'
    if target.exists():raise FileExistsError('Preserve browser verification')
    errors=[];external=[];frame=pd.read_csv(OUT/'data/example_predictions.csv')
    with sync_playwright() as p:
        app=p.chromium.launch(headless=True)
        page=app.new_page(viewport={'width':1280,'height':1000})
        page.on('pageerror',lambda error:errors.append(str(error)))
        def route(request):
            if request.request.url.startswith(('http://','https://')):
                external.append(request.request.url);request.abort()
            else:request.continue_()
        page.route('**/*',route)
        page.goto((OUT/'demo/index.html').as_uri());page.wait_for_selector('#temperature')
        for index in [0,36,72,143]:
            page.locator('#slot').evaluate('(e,v)=>{e.value=v;e.dispatchEvent(new Event("input"));}',index)
            assert page.locator('#time').inner_text()==frame.time.iloc[index]+' KST'
            assert page.locator('#temperature').inner_text()==f'{frame.estimated_road_temp_c.iloc[index]:.2f} °C'
            assert page.locator('#ice').inner_text()==str(frame.predicted_ice.iloc[index])
        page.screenshot(path=str(OUT/'validation/two_winter_desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        page.screenshot(path=str(OUT/'validation/two_winter_mobile.png'),full_page=True)
        app.close()
    assert not errors and not external
    write(target,dict(status='two_winter_browser_verified',slider_slots=[0,36,72,143],console_errors=errors,
        external_requests=external,mobile_no_horizontal_overflow=True,html_sha256=sha(OUT/'demo/index.html'),visual_review_pending=True))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['maps','demo','notebook','browser'],required=True)
    globals()[parser.parse_args().stage]()
