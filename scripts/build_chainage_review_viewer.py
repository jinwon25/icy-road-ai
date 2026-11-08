"""공식 목록 버전·추정 위치·두 겨울 노출을 인터넷 없이 확인하는 화면을 만든다."""
from pathlib import Path
import json
import sys
import geopandas as gpd
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.align_official_culvert_chainage import write

P=ROOT/'outputs/private'
SOURCE=P/'vulnerability_map_comparison_20261031_v1'
OUT=P/'official_inventory_viewer_20261031_v1'


def svg_path(geometry, origin):
    result=[]
    def visit(g):
        if g.geom_type in ['Polygon']:
            visit(g.exterior)
            for hole in g.interiors:visit(hole)
        elif hasattr(g,'geoms'):
            for part in g.geoms:visit(part)
        else:
            coordinates=list(g.coords)
            result.append('M'+'L'.join(f'{(x-origin[0])/1000:.4f},{(origin[1]-y)/1000:.4f}' for x,y,*_ in coordinates))
    visit(geometry.simplify(2,preserve_topology=True))
    return ' '.join(result)


HTML='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>전북 도로 결빙 · 공식 목록 비교</title><style>
*{box-sizing:border-box}body{font:15px/1.55 "Malgun Gothic",sans-serif;margin:0;background:#f3f6f7;color:#18333e}header,main{max-width:1340px;margin:auto;padding:22px}h1{font-size:27px;margin:0 0 8px}h2{font-size:19px}p{margin:8px 0}label{display:block;font-size:13px;color:#395b68}select,button{font:inherit;padding:9px;border:1px solid #aabfc8;border-radius:6px;background:white;max-width:100%}button{cursor:pointer}.controls{display:flex;gap:14px;flex-wrap:wrap}.grid{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(310px,1fr);gap:20px}.panel{background:white;padding:20px;border-radius:12px;border:1px solid #d7e2e6;min-width:0}.note{color:#506d77;font-size:13px}.pill{background:#e9f0f3;padding:9px;border-radius:5px}.map{width:100%;height:650px;background:#fafcfc;touch-action:manipulation}.road{fill:none;stroke-width:.42;cursor:pointer}.road:hover{stroke-width:1.2}.chosen{stroke:#d44b36!important;stroke-width:1.4!important}.inventory{fill:none;stroke:#006f78;stroke-width:1;pointer-events:none}.boundary{fill:#edf1f2;stroke:#b2c1c7;stroke-width:.13;fill-rule:evenodd}.metrics{display:grid;grid-template-columns:1fr 1fr;gap:10px}.metric{background:#f5f8fa;padding:14px;border-radius:7px}.metric strong{font-size:22px;display:block}dl{display:grid;grid-template-columns:95px 1fr;gap:7px;margin:14px 0}dt{color:#66808a}dd{margin:0;overflow-wrap:anywhere}table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:7px;border-bottom:1px solid #d9e2e5}.legend{font-size:12px;display:flex;flex-wrap:wrap;gap:14px}.legend span:before{content:'';display:inline-block;width:18px;height:4px;background:var(--c);vertical-align:middle;margin-right:4px}a{color:#006b78}.small{font-size:12px}.footer{padding:8px 0}.hidden{display:none}@media(max-width:850px){.grid{grid-template-columns:1fr}.map{height:480px}header,main{padding:15px}.panel{padding:14px}h1{font-size:23px}.controls{gap:8px}}
</style><header><h1>전북 도로 결빙 · 공식 목록과 기상 조건 비교</h1><p>문제에 제시된 목록과 2026년 최신 목록을 나란히 확인하고, 두 겨울의 저온·수분 노출을 구간별로 검토합니다.</p><p class="note">암거 기준점으로 보간한 추정 위치입니다. 결빙 확률·공식 위험등급·측량된 구간 도형으로 해석하지 않습니다.</p></header>
<main><div class="controls"><label>공식 목록<select id="version"><option value="2026-09-07">2026-09-07 현재 목록</option><option value="problem_undated">문제 제시 목록 · 기준일 미상</option><option value="none">목록 숨기기</option></select></label><label>노선<select id="route"><option value="all">3개 노선 전체</option></select></label><label>방향<select id="flow"><option value="all">양방향</option></select></label><label>표시 범위<select id="scope"><option value="all">843개 구간 전체</option><option value="candidate">현장 확인 후보만</option></select></label></div>
<p class="note"><span id="count"></span> · <span id="groups"></span> · 보고 단위 500m와 기상정보의 공간 해상도는 다릅니다.</p>
<div class="grid"><section class="panel"><div class="controls"><button id="reset">전체 보기</button><button id="focus">선택 구간 확대</button></div><svg id="map" class="map" role="img" aria-label="전북 고속도로 구간 지도"></svg><div class="legend"><span style="--c:#a8bac4">대상 도로</span><span style="--c:#e69a28">현 목록 밖 확인 후보</span><span style="--c:#006f78">공식 목록의 추정 위치</span><span style="--c:#8b5e96">보간 불가</span><span style="--c:#d44b36">선택 구간</span></div><p class="note">지도 구간을 클릭하거나 오른쪽 목록으로 선택하세요. 방향을 좁히면 나란한 도로를 구분하기 쉽습니다.</p></section>
<section class="panel"><label>검토 구간<select id="segment" style="width:100%"></select></label><h2 id="roadTitle"></h2><p id="relation" class="pill"></p><dl><dt>추정 이정</dt><dd id="chainage"></dd><dt>구간 ID</dt><dd id="segmentId"></dd><dt>방향</dt><dd id="direction"></dd><dt>위치 대조</dt><dd id="cctv"></dd></dl>
<div class="metrics"><div class="metric">2024/25 저온·수분 노출<strong id="winter24"></strong><span id="hours24"></span></div><div class="metric">2025/26 저온·수분 노출<strong id="winter25"></strong><span id="hours25"></span></div></div>
<p class="note">노출률 = 유효 10분 추정 중 결합 조건을 충족한 비율. 실제 Ice 관측 빈도나 사고 확률이 아닙니다.</p><h2>선택 목록과의 관계</h2><p id="inventory"></p><h2>현장 확인 후보 선정</h2><p id="screening"></p><p class="note">두 겨울 모두 노선별 길이 가중 75백분위 이상이며, 추정 위치에 ±250m 범위를 더해도 최신 목록과 겹치지 않는 구간입니다. 같은 노출값은 모두 포함해 실제 후보 비중이 25%를 넘을 수 있습니다. 기상 입력을 공유하는 인접 구간은 연속 구간으로 묶어 확인합니다.</p><p class="small"><a href="corridors.csv" download>연속 확인 구간 CSV</a> · <a href="../vulnerability_map_comparison_20261031_v1/segment_screening.csv" download>전체 구간 CSV</a> · <a href="../vulnerability_map_comparison_20261031_v1/comparison.gpkg" download>GIS 자료</a></p></section></div>
<section class="panel" style="margin-top:20px"><h2>목록·위치 검증에서 확인한 내용</h2><p>문제 목록 17개 중 11개, 최신 전국 목록 중 8개가 전북 경계 안의 보간 가능한 도로와 겹칩니다. 최신 목록 8개 중 1개는 광주전남본부 관할입니다. 관할 본부와 행정 경계를 구별했습니다.</p><p>암거 위치 454곳의 중복 시설을 묶었습니다. 5km 공간 제외 검증의 95백분위 오차는 약 78m이지만, 별도 CCTV 후보 자료에서는 일부 1km 이상의 불일치가 있습니다. ±250m 표시는 민감도 범위이며 오차 보장이나 신뢰구간이 아닙니다.</p><p class="note">구간별 결빙 분류의 새로운 개선은 검증되지 않았습니다. 이 화면은 기존 온도 v3·결빙 v2 결과와 새 공식 목록의 비교 자료입니다. 2026년 목록으로 과거 겨울의 지정 현황이나 지정 해제 사유를 단정하지 않습니다.</p><p class="small">출처: <a href="https://www.data.go.kr/data/15102132/fileData.do">한국도로공사 결빙취약구간 20260907</a> · <a href="https://www.data.go.kr/data/15159523/fileData.do">한국도로공사 암거 20260514</a> · SGIS 2024 행정 경계 · 대회 제공 도로 자료. 화면은 외부 요청 없이 실행됩니다.</p></section></main>
<script>const data=__DATA__;const NS='http://www.w3.org/2000/svg',el=id=>document.getElementById(id);const rows=data.rows,lookup=Object.fromEntries(rows.map(r=>[r.seg_id,r]));const fullBox=data.box;let chosen=null;
function node(tag,attrs){let n=document.createElementNS(NS,tag);for(let[k,v]of Object.entries(attrs))n.setAttribute(k,v);return n}
function options(id,values){el(id).replaceChildren();for(let[v,t]of values){let o=document.createElement('option');o.value=v;o.textContent=t;el(id).appendChild(o)}}
for(let route of [...new Set(rows.map(r=>r.route_nm))]){let o=document.createElement('option');o.value=route;o.textContent=route;el('route').appendChild(o)}
function visible(){return rows.filter(r=>(el('route').value==='all'||r.route_nm===el('route').value)&&(el('flow').value==='all'||r.flow_lbl===el('flow').value)&&(el('scope').value==='all'||r.field_review_candidate))}
function draw(){const svg=el('map');svg.replaceChildren();svg.setAttribute('viewBox',fullBox.join(' '));svg.appendChild(node('path',{d:data.boundary,class:'boundary'}));let part=visible();for(let r of part){let p=node('path',{d:r.path,class:'road','data-id':r.seg_id,stroke:!r.chainage_available?'#8b5e96':r.field_review_candidate?'#e69a28':'#a8bac4'});p.addEventListener('click',()=>select(r.seg_id));svg.appendChild(p)}
const keep=new Set(part.map(r=>r.seg_id));for(let p of data.overlays.filter(p=>p.version===el('version').value&&keep.has(p.seg_id)))svg.appendChild(node('path',{d:p.path,class:'inventory'}));
options('segment',part.map(r=>[r.seg_id,r.route_nm+' · '+(r.estimated_km_lo===null?'이정 미확정':r.estimated_km_lo.toFixed(2)+'–'+r.estimated_km_hi.toFixed(2)+' km')+' · '+r.flow_lbl]));
el('count').textContent=part.length+'개 보고 구간';el('groups').textContent='겨울별 기상 입력 조합 '+new Set(part.map(r=>r.group24)).size+' / '+new Set(part.map(r=>r.group25)).size+'개';
if(part.length)select(keep.has(chosen)?chosen:part[0].seg_id)}
const relationText={alignment_unavailable:'기준점 범위 밖 · 이정 보간 불가',inside_inventory_for_margin:'현재 목록 안 · ±250m에서도 포함',boundary_uncertain:'현재 목록 경계 인접 · 위치 오차에 따라 관계 변화',outside_inventory_for_margin:'현재 목록 밖 · ±250m 범위에서도 비중첩'};
function select(id){chosen=id;const r=lookup[id];el('segment').value=id;for(let n of document.querySelectorAll('.road'))n.classList.toggle('chosen',n.dataset.id===id);let p=document.querySelector('.road.chosen');if(p)el('map').appendChild(p);
el('roadTitle').textContent=r.route_nm;el('relation').textContent=relationText[r.current_relation];el('segmentId').textContent=id;el('direction').textContent=r.flow_lbl;el('chainage').textContent=r.chainage_available?r.estimated_km_lo.toFixed(3)+'–'+r.estimated_km_hi.toFixed(3)+' km · 추정':'보간 범위 밖';
el('cctv').textContent=r.cctv_conflict?'인접 1km에 CCTV 이정 차이 >250m · 현장 대조 필요':'인접 CCTV 불일치 표지 없음 · 위치 검증을 보장하지 않음';
el('winter24').textContent=(r.exposure24*100).toFixed(2)+'%';el('winter25').textContent=(r.exposure25*100).toFixed(2)+'%';el('hours24').textContent=r.hours24.toFixed(1)+'시간 / 유효 '+r.valid24+'개';el('hours25').textContent=r.hours25.toFixed(1)+'시간 / 유효 '+r.valid25+'개';
let inv=data.overlaps.filter(v=>v.seg_id===id&&v.version===el('version').value);el('inventory').textContent=el('version').value==='none'?'목록 표시를 껐습니다.':inv.length?inv.map(v=>v.inventory_id+' · '+(v.nominal_overlap_km>0?'추정 위치 중첩':'±250m 범위에서만 인접')).join(' / '):r.chainage_available?'선택 목록과 ±250m에서 겹치는 구간 없음':'보간 불가로 관계를 판정하지 않음';
el('screening').textContent=r.field_review_candidate?'연속 확인 구간 '+r.corridor_id+'에 포함됩니다. 현장 점검·추가 센서 검토를 위한 연구 후보입니다.':'현재 설정의 확인 후보에 해당하지 않습니다. 안전함을 뜻하지 않습니다.'}
el('route').onchange=()=>{options('flow',[['all','양방향'],...[...new Set(rows.filter(r=>el('route').value==='all'||r.route_nm===el('route').value).map(r=>r.flow_lbl))].map(v=>[v,v])]);draw()};el('flow').onchange=draw;el('scope').onchange=draw;el('version').onchange=draw;el('segment').onchange=()=>select(el('segment').value);el('reset').onclick=()=>el('map').setAttribute('viewBox',fullBox.join(' '));el('focus').onclick=()=>{let r=lookup[chosen];if(!r)return;el('map').setAttribute('viewBox',[r.cx-4,r.cy-4,8,8].join(' '))};el('route').onchange();
</script></html>'''


def main():
    audit=json.loads((SOURCE/'independent_verification.json').read_text(encoding='utf-8'));assert audit['status']=='passed'
    OUT.mkdir(parents=True,exist_ok=False)
    source_files=[SOURCE/n for n in ['summary.json','independent_verification.json','comparison.gpkg','segment_screening.csv','two_winter_exposure.csv','overlap_sensitivity.csv']]
    source_files += [P/'segment_exposure_20261009_v1/segments_500m.gpkg',P/'segment_exposure_20261009_v1/boundary.gpkg',P/'official_chainage_alignment_20261031_v1/cctv_independent_diagnostic.csv',Path(__file__)]
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in source_files}
    g=gpd.read_file(source_files[6]);boundary=gpd.read_file(source_files[7]).to_crs(g.crs)
    f=pd.read_csv(SOURCE/'segment_screening.csv',dtype={'seg_id':str});w=pd.read_csv(SOURCE/'two_winter_exposure.csv',dtype={'seg_id':str,'prediction_group':str})
    g=g[['seg_id','chain_id','m0','m1','geometry']].merge(f.drop(columns='chain_id'),on='seg_id',validate='one_to_one')
    corridors=[];g['corridor_id']=None
    for chain,part in g.sort_values('m0').groupby('chain_id'):
        number=0;last_end=-np.inf;indices=[]
        for idx,row in part.loc[part.field_review_candidate].iterrows():
            if row.m0-last_end>1e-5:
                number+=1
            cid=f'{chain[:6]}-{number:02d}';g.loc[idx,'corridor_id']=cid;last_end=row.m1
    for cid,part in g.loc[g.field_review_candidate].groupby('corridor_id'):
        corridors.append(dict(corridor_id=cid,route_nm=part.route_nm.iloc[0],flow_lbl=part.flow_lbl.iloc[0],
            estimated_km_lo=float(part.estimated_km_lo.min()),estimated_km_hi=float(part.estimated_km_hi.max()),
            segment_count=len(part),directional_length_km=float(part.length_m.sum()/1000),
            minimum_two_winter_exposure=float(part.exposure_min.min()),maximum_two_winter_exposure=float(part.exposure_max.max()),
            official_chainage_verified=False))
    pd.DataFrame(corridors).to_csv(OUT/'corridors.csv',index=False,encoding='utf-8-sig')
    ties=[]
    for (route,winter),part in w.groupby(['route_nm','winter']):
        ties.append(dict(route_nm=route,winter=int(winter),threshold=float(part.route_q75.iloc[0]),
            at_or_above_segments=int(part.above_route_q75.sum()),all_segments=len(part),
            at_or_above_length_fraction=float(part.loc[part.above_route_q75,'len_m'].sum()/part.len_m.sum()),
            identical_at_threshold_segments=int(part.cold_wet_fraction.eq(part.route_q75).sum()),
            weather_input_groups=part.prediction_group.nunique()))
    pd.DataFrame(ties).to_csv(OUT/'threshold_ties.csv',index=False,encoding='utf-8-sig')
    bounds=g.total_bounds;origin=(float(bounds[0]),float(bounds[3]));box=[-5,-5,float((bounds[2]-bounds[0])/1000+10),float((bounds[3]-bounds[1])/1000+10)]
    cctv=pd.read_csv(source_files[8]);rows=[]
    for _,r in g.iterrows():
        record=r.drop('geometry').to_dict();a=w.loc[w.seg_id.eq(r.seg_id)].set_index('winter')
        for year,suffix in [(2024,'24'),(2025,'25')]:
            for key,column in [('exposure','cold_wet_fraction'),('hours','cold_wet_hours'),('valid','ice_valid_slots'),('group','prediction_group')]:record[key+suffix]=a.loc[year,column]
        conflict=cctv.loc[cctv.chain_id.eq(r.chain_id)&cctv.error_m.abs().gt(250)&cctv.x_m.between(r.m0-1000,r.m1+1000)]
        record['cctv_conflict']=len(conflict)>0;record['path']=svg_path(r.geometry,origin)
        center=r.geometry.interpolate(.5,normalized=True);record['cx']=(center.x-origin[0])/1000;record['cy']=(origin[1]-center.y)/1000
        rows.append(record)
    rows=json.loads(pd.DataFrame(rows).to_json(orient='records',force_ascii=False,double_precision=15))
    layers=gpd.read_file(SOURCE/'comparison.gpkg',layer='estimated_inventory_overlay')
    overlays=[dict(seg_id=r.seg_id,version=r.version,path=svg_path(r.geometry,origin)) for _,r in layers.iterrows()]
    overlaps=pd.read_csv(SOURCE/'overlap_sensitivity.csv');overlaps=overlaps.loc[overlaps.margin_m.eq(250)]
    ov=overlaps.groupby(['seg_id','version','inventory_id'],as_index=False).nominal_overlap_km.sum()
    data=dict(rows=rows,overlays=overlays,box=box,boundary=' '.join(svg_path(shape,origin) for shape in boundary.geometry),overlaps=json.loads(ov.to_json(orient='records',force_ascii=False)))
    payload=json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':')).replace('<','\\u003c')
    (OUT/'index.html').write_text(HTML.replace('__DATA__',payload),encoding='utf-8')
    (OUT/'viewer_data.json').write_text(payload,encoding='utf-8')
    summary=dict(status='offline_viewer_built',segments=len(rows),candidate_segments=int(g.field_review_candidate.sum()),
        directional_corridors=len(corridors),threshold_ties=ties,source_signatures=signatures,
        original_figure_caption_correction='vulnerability_map_comparison_20261031_v1/inventory_comparison.png의 상위 25% 표기는 동률을 포함한 75백분위 이상으로 읽어야 한다. 해당 초안 그림 대신 이 화면을 사용한다.',
        files={p.name:sha(p) for p in OUT.iterdir() if p.is_file()},network_required=False)
    write(OUT/'summary.json',summary);print('BUILT',len(rows),'segments',len(corridors),'directional corridors')


if __name__=='__main__':main()
