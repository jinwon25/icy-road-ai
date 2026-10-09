"""감사된 두 겨울의 구간 기상 노출을 JPG·CSV·외부 통신 없는 HTML로 보여 준다."""
from pathlib import Path
import argparse,html,json,sys
import geopandas as gpd,numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize,TwoSlopeNorm
from matplotlib.ticker import FuncFormatter
from shapely import get_parts

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.audit_joint_surface import read,sha


def path_string(geometry):
    parts=[]
    for part in get_parts(geometry):
        if part.geom_type=='Polygon':rings=[part.exterior,*part.interiors]
        elif part.geom_type=='LineString':rings=[part]
        else:continue
        for line in rings:
            points=np.asarray(line.coords);parts.append('M'+' L'.join(f'{x:.6f},{-y:.6f}' for x,y in points)+(' Z' if part.geom_type=='Polygon' else ''))
    return ' '.join(parts)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'outputs/private/segment_review_20261009_v1');args=parser.parse_args();out=args.output.resolve();private=ROOT/'outputs/private'
    if not out.is_relative_to(private.resolve()):parser.error('Private output required')
    if out.exists():raise FileExistsError('Preserve review')
    folders=[private/'segment_exposure_20261009_v1',private/'segment_exposure_second_winter_20261009_v1']
    for p in folders:assert read(p/'independent_verification.json')['status']=='passed'
    first,second=[gpd.read_file(p/'segments_500m.gpkg') for p in folders];assert first.seg_id.tolist()==second.seg_id.tolist()
    boundary=gpd.read_file(folders[0]/'boundary.gpkg');out.mkdir(parents=True)
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':11})
    limit=float(np.ceil(max(first.cold_moist_fraction.max(),second.cold_moist_fraction.max())*10)/10);norm=Normalize(0,limit*100)
    difference=(second.cold_moist_fraction-first.cold_moist_fraction)*100;dl=max(float(np.abs(difference).max()),1)
    uncertainty=np.maximum(first.model_disagreement_fraction,second.model_disagreement_fraction)*100
    fig,axes=plt.subplots(2,2,figsize=(13,10),constrained_layout=True)
    values=[first.cold_moist_fraction*100,second.cold_moist_fraction*100,difference,uncertainty]
    titles=['추정 저온·수분 조건 비율: 2024–25 (%)','추정 저온·수분 조건 비율: 2025–26 (%)','두 겨울 조건 비율 차이 (두 번째에서 첫 번째를 뺌, %p)','제외 그룹별 모델과 판정이 달랐던 시각 (최대, %)']
    for i,(ax,value,title) in enumerate(zip(axes.flat,values,titles)):
        boundary.plot(ax=ax,color='#f3f5f7',edgecolor='#929aa3',linewidth=.6)
        local=TwoSlopeNorm(vmin=-dl,vcenter=0,vmax=dl) if i==2 else (Normalize(0,max(float(uncertainty.max()),1)) if i==3 else norm)
        cmap='coolwarm' if i==2 else ('magma' if i==3 else 'viridis')
        first.assign(value=np.asarray(value)).plot(ax=ax,column='value',cmap=cmap,norm=local,linewidth=2.5)
        fig.colorbar(plt.cm.ScalarMappable(norm=local,cmap=cmap),ax=ax,shrink=.7)
        ax.set_title(title);ax.set_aspect('equal');ax.xaxis.set_major_formatter(FuncFormatter(lambda x,_:f'{x/1000:.0f}'));ax.yaxis.set_major_formatter(FuncFormatter(lambda x,_:f'{x/1000:.0f}'));ax.set_xlabel('EPSG:5179 동서 좌표 (km)');ax.set_ylabel('남북 좌표 (km)')
    fig.suptitle('전북 843개 방향별 500m 구간의 기상 노출·모델 민감도\n첫 겨울 학습 모델 고정 / Ice·사고 확률 및 위험등급 검증 결과가 아님',fontsize=15)
    fig.savefig(out/'segment_exposure_review.jpg',dpi=220);plt.close(fig)
    rows=[]
    for winter,g in zip(['2024–25','2025–26'],[first,second]):
        for (route,flow),part in g.groupby(['route_nm','flow_lbl']):
            rows.append(dict(winter=winter,route=route,direction=flow,segments=len(part),directional_length_km=float(part.len_m.sum()/1000),
                             mean_cold_moist_fraction=float(np.average(part.cold_moist_fraction,weights=part.len_m)),
                             mean_cold_moist_hours=float(np.average(part.cold_moist_hours,weights=part.len_m)),
                             mean_disagreement_fraction=float(np.average(part.model_disagreement_fraction,weights=part.len_m)),
                             bridge_code_length_km=float((part.len_m*part.bridge_code_fraction).sum()/1000),
                             tunnel_code_length_km=float((part.len_m*part.tunnel_code_fraction).sum()/1000)))
    pd.DataFrame(rows).to_csv(out/'route_direction_review.csv',index=False,encoding='utf-8-sig')
    d={}
    for year,g in zip(['2024-25','2025-26'],[first,second]):
        d[year]=[dict(id=r.seg_id,route=r.route_nm,direction=r.flow_lbl,path=path_string(r.geometry),fraction=r.cold_moist_fraction,hours=r.cold_moist_hours,coverage=r.valid_fraction,
                       sensitivity_min=r.sensitivity_fraction_min,sensitivity_max=r.sensitivity_fraction_max,disagreement=r.model_disagreement_fraction,
                       bridge=r.bridge_code_fraction,tunnel=r.tunnel_code_fraction,length=r.len_m,relative_start=r.m0/1000,relative_end=r.m1/1000,edge=bool(r.boundary_edge),lon=r.point_lon,lat=r.point_lat) for r in g.itertuples(index=False)]
    xmin,ymin,xmax,ymax=boundary.total_bounds;view=f'{xmin} {-ymax} {xmax-xmin} {ymax-ymin}';outline=' '.join(path_string(g) for g in boundary.geometry)
    template='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>전북 구간 기상 노출 검토</title>
<style>body{font-family:system-ui,'Malgun Gothic',sans-serif;margin:24px;color:#172c3e;background:#f6f8fa}h1{font-size:25px}select,input{padding:8px;margin:5px;border:1px solid #aab6c2;border-radius:5px}.notice{padding:16px;background:#fff5d8;line-height:1.6}.layout{display:grid;grid-template-columns:1.2fr 1fr;gap:20px;margin-top:20px}svg{width:100%;height:620px;background:white;border:1px solid #ddd}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:9px;border-bottom:1px solid #d8e0e8;text-align:left}tbody tr:hover{background:#e5efff;cursor:pointer}#detail{background:white;padding:16px;line-height:1.8;min-height:160px}a{color:#1b5797}small{line-height:1.6}button{padding:8px} @media(max-width:900px){.layout{grid-template-columns:1fr}}</style>
<h1>전북 고속도로: 두 겨울의 기상 노출과 환경 근거</h1><div class="notice">843개 방향별 500m 구간 / 2024년 SGIS 경계 안의 연구용 선형.<br>표의 비율은 <b>AI 추정 온도 ≤0°C이면서 수분 근거가 있었던 시각 / 추정 가능한 시각</b>입니다. 검증된 Ice 확률·사고확률·공식 위험등급이 아닙니다. 모델 간 차이는 민감도이며 신뢰구간이 아닙니다.</div>
<p><label>겨울 <select id="year"><option>2024-25</option><option>2025-26</option></select></label><label>노선 <select id="route"><option value="">전체</option></select></label><label>방향 <select id="direction"><option value="">전체</option></select></label><input id="search" placeholder="구간 ID 검색" aria-label="구간 ID 검색"><button id="download">현재 목록 CSV 저장</button></p>
<div class="layout"><div><svg id="map" viewBox="__VIEW__" role="img" aria-label="전북 도로 구간 기상 노출 지도"><path d="__BOUNDARY__" fill="#f2f5f7" fill-rule="evenodd" stroke="#8997a4" stroke-width="100"/><g id="roads"></g></svg><small>색이 진해질수록 조건 비율이 높습니다. 양 방향은 가까이 겹치므로 방향 필터로 비교하세요.<br>구간 중앙의 기상 입력으로 추정했습니다. 공식 이정·실제 시설 범위·현행 제한속도는 확인이 필요합니다. 원본 도로의 틈은 연결하지 않았습니다.<br>출처: 기상청 ASOS/AWS·RWIS 학습 자료, <a href="https://sgis.mods.go.kr/view/pss/openDataIntrcn">SGIS 2024 경계</a>, <a href="https://www.its.go.kr/opendata/nodelink">국가교통정보센터 과거 링크</a>. 외부 통신·지도 타일·인증키가 없는 로컬 검토 파일입니다.</small></div><div><div id="detail">지도나 표에서 구간을 선택하면 추정 조건과 환경 근거가 표시됩니다.</div><p id="count"></p><div style="max-height:390px;overflow:auto"><table><thead><tr><th>구간 ID</th><th>조건 비율</th><th>모델 차이</th></tr></thead><tbody id="rows"></tbody></table></div></div></div>
<script>const DATA=__DATA__;const byId=x=>document.getElementById(x);const route=byId('route'),direction=byId('direction'),year=byId('year'),search=byId('search');let current=[];
const percent=x=>(x*100).toFixed(2)+'%';const escape=x=>String(x).replace(/[&<>"']/g,a=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[a]));
[...new Set(DATA['2024-25'].map(x=>x.route))].sort().forEach(x=>route.add(new Option(x,x)));function directions(){direction.innerHTML='<option value="">전체</option>';[...new Set(DATA[year.value].filter(x=>!route.value||x.route===route.value).map(x=>x.direction))].sort().forEach(x=>direction.add(new Option(x,x)));}
function show(x){byId('detail').innerHTML=`<b>${escape(x.route)} · ${escape(x.direction)}</b><br>ID ${escape(x.id)} · 유지 길이 ${x.length.toFixed(1)}m<br>저온·수분 조건 ${percent(x.fraction)} (${x.hours.toFixed(1)}시간)<br>추정 가능 시각 ${percent(x.coverage)}<br>그룹 제외 모델 조건 비율 범위 ${percent(x.sensitivity_min)}–${percent(x.sensitivity_max)}<br>모델과 판정이 달랐던 시각 ${percent(x.disagreement)}<br>과거 링크 교량 코드 ${percent(x.bridge)} / 터널 코드 ${percent(x.tunnel)}<br>후보 경로 상대 거리 ${x.relative_start.toFixed(3)}–${x.relative_end.toFixed(3)}km (공식 이정 아님)<br>경계에서 잘린 구간 ${x.edge?'예':'아니오'} · 표본 위치 ${x.lat.toFixed(5)}, ${x.lon.toFixed(5)}`;}
function render(){current=DATA[year.value].filter(x=>(!route.value||x.route===route.value)&&(!direction.value||x.direction===direction.value)&&x.id.includes(search.value.trim())).sort((a,b)=>b.fraction-a.fraction);byId('roads').replaceChildren();byId('rows').replaceChildren();current.forEach(x=>{let p=document.createElementNS('http://www.w3.org/2000/svg','path');p.setAttribute('d',x.path);p.setAttribute('fill','none');p.setAttribute('stroke-width','430');p.setAttribute('stroke',`hsl(${215-x.fraction*170},70%,${75-x.fraction*45}%)`);p.addEventListener('click',()=>show(x));const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=x.id+' '+percent(x.fraction);p.append(title);byId('roads').append(p);let tr=document.createElement('tr');tr.innerHTML=`<td>${escape(x.id)}</td><td>${percent(x.fraction)}</td><td>${percent(x.disagreement)}</td>`;tr.addEventListener('click',()=>show(x));byId('rows').append(tr)});byId('count').textContent=current.length+'개 구간 · 조건 비율 내림차순 (위험등급 순위가 아님)';}
route.addEventListener('change',()=>{directions();render()});year.addEventListener('change',render);direction.addEventListener('change',render);search.addEventListener('input',render);
byId('download').addEventListener('click',()=>{const fields=['id','route','direction','fraction','hours','coverage','disagreement','bridge','tunnel','length'];const cell=x=>'"'+String(x).replace(/"/g,'""')+'"';const content='\\ufeff'+fields.join(',')+'\\n'+current.map(x=>fields.map(k=>cell(x[k])).join(',')).join('\\n');const url=URL.createObjectURL(new Blob([content],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='segment_exposure_'+year.value+'.csv';a.click();URL.revokeObjectURL(url)});directions();render();</script></html>'''
    content=template.replace('__VIEW__',view).replace('__BOUNDARY__',outline).replace('__DATA__',json.dumps(d,ensure_ascii=False,allow_nan=False).replace('</','<\\/'))
    (out/'segment_review.html').write_text(content,'utf-8')
    (out/'summary.json').write_text(json.dumps(dict(status='completed_local_aggregate_review',segments_per_winter=len(first),network_requests_in_viewer=False,
                                                 inputs={str(p):sha(p/'summary.json') for p in folders},files={p.name:sha(p) for p in out.iterdir() if p.is_file()}),ensure_ascii=False,indent=2),'utf-8')
    print('Rendered segment JPG/CSV/offline HTML:',out,flush=True)


if __name__=='__main__':main()
