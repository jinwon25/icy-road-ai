"""실제 후보 CLI 로그와 학습 범위 내 하루의 로컬 예측 데모를 생성·검증."""
from datetime import datetime,timezone
from pathlib import Path
import json
import subprocess
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write
from src.data_source import sha256_file as sha
OUT=ROOT/'outputs/private/submission_candidate_20261013_v1'

TEMPLATE='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>기상 입력 기반 노면 추정 실행 예제</title><style>
*{box-sizing:border-box}body{font-family:system-ui,"Malgun Gothic",sans-serif;color:#253342;background:#f7f9fb;margin:0;padding:40px 7vw;line-height:1.7}main{max-width:1100px;margin:auto}h1{font-size:34px;line-height:1.35;color:#183b59}p{max-width:900px}svg{width:100%;height:auto;background:white;border-bottom:1px solid #dbe3eb}label{display:block;font-weight:600}input{width:100%;accent-color:#245980}.value{font-size:24px;font-weight:700;color:#183b59}table{width:100%;border-collapse:collapse;margin:20px 0}th,td{text-align:left;padding:12px;border-bottom:1px solid #dbe3eb}th{background:#e7eef4}small{color:#566a7b}a{color:#21577c}.note{color:#65461e}pre{white-space:pre-wrap;background:white;padding:20px;font-size:12px}footer{margin-top:30px}@media(max-width:650px){body{padding:24px}h1{font-size:25px}th,td{padding:8px;font-size:13px}}
</style><main><h1>기상 입력 기반 노면 추정 실행 예제</h1><p>허용 23개 지점의 첫 겨울 자료로 학습한 고정 2모델 평균입니다. 아래는 <strong>학습 범위 내 12207 지점의 2024년 12월 15일</strong>을 로컬 파일로 추론한 실행 예제입니다.</p><p class="note">새 지점 성능평가나 공식 대회 점수는 없습니다. 판정 0도 안전을 보장하지 않습니다. 성분 차이는 전체 예측오차나 확률을 뜻하지 않습니다.</p>
<svg id="chart" viewBox="0 0 1100 290" role="img" aria-label="하루의 추정 노면온도와 저온 수분 판정"><g id="drawing"></g></svg>
<label for="slot">10분 시각 선택</label><input id="slot" type="range" min="0" max="143" value="72" step="1"><p class="value" id="time"></p>
<table><thead><tr><th>추정 온도</th><th>결빙 판정</th><th>조건 근거</th><th>성분 차이</th></tr></thead><tbody><tr><td id="temperature"></td><td id="ice"></td><td id="condition"></td><td id="spread"></td></tr></tbody></table>
<p>평균 노면온도 0°C 이하와 이슬점·과거 강수·눈 중 하나의 수분 조건이 동시에 있어야 판정 1입니다. 유효 ASOS 또는 모든 수분 입력이 없으면 판정을 null로 남깁니다.</p>
<details><summary>실제 로컬 실행 기록</summary><pre id="log"></pre></details>
<footer><a href="../reports/결빙_분석_제출후보_보고서.pdf">분석 보고서와 실행매뉴얼</a><p><small>외부 라이브러리·지도 타일·분석 API 호출 없이 실행합니다. 비공개 참가 자료의 로컬 검토용입니다.</small></p></footer></main>
<script>const rows=__ROWS__;const log=__LOG__;document.getElementById('log').textContent=log;
const words={cold_wet_consensus:'저온·수분 조건에 모델 합의',cold_wet_disagreement:'저온·수분 조건에 성분 불일치',criterion_not_met:'결합 기준 미충족',insufficient_input:'입력 부족'};
const ns='http://www.w3.org/2000/svg';const g=document.getElementById('drawing');
function el(name,attrs,text){const x=document.createElementNS(ns,name);for(const[k,v]of Object.entries(attrs))x.setAttribute(k,v);if(text)x.textContent=text;g.appendChild(x);return x}
const temps=rows.map(r=>r.estimated_road_temp_c).filter(x=>x!==null);const low=Math.min(-2,...temps)-1,high=Math.max(2,...temps)+1;
const y=t=>240-(t-low)/(high-low)*200,x=i=>60+i*1000/143;
el('line',{x1:60,x2:1060,y1:y(0),y2:y(0),stroke:'#9aaebf','stroke-dasharray':'5 4'});el('text',{x:6,y:y(0)+4,fill:'#607687','font-size':14},'0°C');
let points='';for(let i=0;i<rows.length;i++){const r=rows[i];if(r.predicted_ice===1)el('rect',{x:x(i)-3,y:249,width:6,height:12,fill:'#d08730'});if(r.estimated_road_temp_c!==null)points+=`${x(i)},${y(r.estimated_road_temp_c)} `}
el('polyline',{points,fill:'none',stroke:'#245980','stroke-width':3});el('text',{x:60,y:282,fill:'#607687','font-size':14},'00:00');el('text',{x:520,y:282,fill:'#607687','font-size':14},'12:00');el('text',{x:1010,y:282,fill:'#607687','font-size':14},'23:50');
const marker=el('line',{x1:x(72),x2:x(72),y1:30,y2:265,stroke:'#253342','stroke-width':1});
function show(){const i=Number(document.getElementById('slot').value),r=rows[i];document.getElementById('time').textContent=r.time+' KST';document.getElementById('temperature').textContent=r.estimated_road_temp_c===null?'입력 부족':r.estimated_road_temp_c.toFixed(2)+' °C';document.getElementById('ice').textContent=r.predicted_ice===null?'null':String(r.predicted_ice);document.getElementById('condition').textContent=words[r.condition_evidence];document.getElementById('spread').textContent=r.temperature_component_spread_c.toFixed(3)+' °C';marker.setAttribute('x1',x(i));marker.setAttribute('x2',x(i));}
document.getElementById('slot').addEventListener('input',show);show();</script></html>'''


def main():
    if (OUT/'demo/index.html').exists():raise FileExistsError('Preserve demo')
    commands=[['code/predict.py','--input','data/weather_example.csv','--output','validation/cli_example_roundtrip.csv'],
        ['code/export_predictions.py','--kind','protected','--output','validation/cli_targets_roundtrip'],
        ['code/export_predictions.py','--kind','segment','--scale','500','--id','8eabed369e9c40e7','--output','validation/cli_segment_roundtrip']]
    logs=[]
    for command in commands:
        result=subprocess.run([sys.executable,'-X','utf8',*command],cwd=OUT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
        logs.append(dict(command='python -X utf8 '+' '.join(command),returncode=result.returncode,output=result.stdout.decode('utf-8',errors='replace')))
        assert result.returncode==0
    actual=pd.read_csv(OUT/'validation/cli_example_roundtrip.csv');expected=pd.read_csv(OUT/'data/example_predictions.csv')
    pd.testing.assert_frame_equal(actual,expected,check_exact=False,atol=1e-10,rtol=0)
    records=actual.replace({np.nan:None}).to_dict('records');log='\n\n'.join(r['command']+'\n'+r['output'] for r in logs)
    (OUT/'demo/index.html').write_text(TEMPLATE.replace('__ROWS__',json.dumps(records,ensure_ascii=False,allow_nan=False)).replace('__LOG__',json.dumps(log,ensure_ascii=False)),encoding='utf-8')
    (OUT/'demo/execution_log.txt').write_text(log,encoding='utf-8')
    write(OUT/'validation/cli_demo_receipt.json',dict(status='candidate_real_cli_demo_passed',commands=logs,
        example_rows=144,target_export_rows=sum(len(pd.read_csv(p)) for p in (OUT/'validation/cli_targets_roundtrip').glob('*.csv.gz')),
        segment_export_rows=sum(len(pd.read_csv(p)) for p in (OUT/'validation/cli_segment_roundtrip').glob('*.csv.gz')),
        model_fits=0,independent_performance_evaluation=False,html_sha256=sha(OUT/'demo/index.html')))
    print(read(OUT/'validation/cli_demo_receipt.json'))


if __name__=='__main__':main()
