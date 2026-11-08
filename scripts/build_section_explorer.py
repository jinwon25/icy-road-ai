"""고유 구간 키로 기상·시설·목록·선정 근거를 연결한 지도를 만든다."""
from pathlib import Path
import sys,json,math
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
P=ROOT/'outputs/private';B=P/'competition_submission/icy_road_model'
def main():
 shape=json.loads((B/'technical/inventory_geometry.json').read_text(encoding='utf8'));f=pd.read_csv(B/'results/sections/section_review.csv',float_precision='round_trip')
 shape_rows={r['seg_id']:r for r in shape['rows']};rows=[]
 for sid,q in f.groupby('seg_id',sort=True):
  q=q.sort_values('winter');a=q.iloc[0];g=shape_rows[sid]
  rows.append(dict(id=sid,route=a.route_nm,flow=a.flow_lbl,path=g['path'],cx=g['cx'],cy=g['cy'],
   km=[None if pd.isna(a[c]) else float(a[c]) for c in ['estimated_km_lo','estimated_km_hi']],
   bridge=float(a.bridge_code_fraction),curve=float(a.curve_deg_100m),area=None if pd.isna(a.inspection_area_id) else a.inspection_area_id,
   relation=a.current_relation,w=[dict(index=float(r.weather_index_100),availability=float(r.condition_availability),code=int(r.review_code)) for _,r in q.iterrows()]))
 areas=pd.read_csv(B/'results/sections/inspection_areas.csv').to_dict('records')
 def clean(v):
  if isinstance(v,float) and not math.isfinite(v):return None
  if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
  if isinstance(v,list):return [clean(x) for x in v]
  return v
 data=clean(dict(rows=rows,box=shape['box'],boundary=shape['boundary'],areas=areas))
 folder=B/'maps';folder.mkdir(exist_ok=True)
 template=(ROOT/'src/templates/submission_sections.html').read_text(encoding='utf8')
 rendered=template.replace('__DATA__',json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/'))
 (folder/'sections.html').write_text(rendered,encoding='utf8')
 print('SECTION EXPLORER BUILT',len(rows),'segments;',len(areas),'inspection areas',flush=True)
if __name__=='__main__':main()
