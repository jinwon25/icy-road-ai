"""구간 선정 기준·민감도·공개 DSM 지형 맥락을 같은 도로 키로 연결한 탐색 화면."""
from pathlib import Path
import sys,json,math
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.seal_protected_weather_20261106 import W
B=W/'icy_road_model'

def main():
    shape=json.loads((B/'technical/inventory_geometry.json').read_text('utf8'));shapes={r['seg_id']:r for r in shape['rows']}
    f=pd.read_csv(B/'results/sections/section_review.csv',dtype={'seg_id':str},float_precision='round_trip')
    stable=pd.read_csv(B/'results/sections/sensitivity/segment_stability.csv',dtype={'seg_id':str}).set_index('seg_id')
    members=pd.read_csv(B/'results/sections/sensitivity/scenario_membership.csv',dtype={'seg_id':str}).set_index('seg_id')
    terrain=pd.read_csv(W/'terrain_context/segment_terrain.csv',dtype={'seg_id':str},float_precision='round_trip').set_index('seg_id')
    solar=pd.read_csv(W/'terrain_context/segment_solar_context.csv',dtype={'seg_id':str},float_precision='round_trip').set_index(['seg_id','winter'])
    overlap=pd.read_csv(B/'results/inventory/overlap_sensitivity.csv',dtype={'seg_id':str})
    possible={m:set(overlap.loc[overlap.version.eq('2026-09-07')&overlap.margin_m.eq(m),'seg_id']) for m in [100,250,500]}
    inside={m:set(overlap.loc[overlap.version.eq('2026-09-07')&overlap.margin_m.eq(m)&overlap.boundary_relation.eq('fully_inside_for_margin'),'seg_id']) for m in [100,250,500]}
    rows=[]
    for sid,q in f.groupby('seg_id',sort=True):
        q=q.sort_values('winter');p=q.iloc[0];g=shapes[sid];t=terrain.loc[sid]
        rows.append(dict(id=sid,route=p.route_nm,flow=p.flow_lbl,path=g['path'],cx=g['cx'],cy=g['cy'],length=p.len_m,
            km=[p.estimated_km_lo,p.estimated_km_hi],bridge=p.bridge_code_fraction,tunnel=p.tunnel_code_fraction,curve=p.curve_deg_100m,
            area=p.inspection_area_id,stability=stable.loc[sid,'selection_fraction'],
            membership=''.join('1' if x else '0' for x in members.loc[sid]),
            inventory={str(m):'alignment_unavailable' if not p.chainage_available else 'inside_inventory_for_margin' if sid in inside[m] else 'boundary_uncertain' if sid in possible[m] else 'outside_inventory_for_margin' for m in possible},
            w=[dict(index=r.weather_index_100,availability=r.condition_availability) for r in q.itertuples()],
            terrain=dict(elevation=t.dsm_elevation_m,skyview=t.sky_view_proxy),
            solar=[dict(shade=solar.loc[(sid,y),'potential_shade_daylight_fraction'],shade1=solar.loc[(sid,y),'potential_shade_daylight_fraction_1km']) for y in [2024,2025]]))
    areas=pd.read_csv(B/'results/sections/inspection_areas.csv').merge(pd.read_csv(B/'results/sections/sensitivity/area_stability.csv'),left_on='area_id',right_on='inspection_area_id',validate='one_to_one')
    for i,a in areas.iterrows():
        ids=f.loc[f.inspection_area_id.eq(a.area_id),'seg_id'].unique()
        values=solar.loc[pd.IndexSlice[ids,:],'potential_shade_daylight_fraction']
        areas.loc[i,'shade_min']=float(values.min());areas.loc[i,'shade_max']=float(values.max())
    scenarios=pd.read_csv(B/'results/sections/sensitivity/scenario_summary.csv').to_dict('records')
    def clean(v):
        if isinstance(v,float) and not math.isfinite(v):return None
        if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
        if isinstance(v,list):return [clean(x) for x in v]
        return v
    data=clean(dict(rows=rows,areas=areas.to_dict('records'),scenarios=scenarios,box=shape['box'],boundary=shape['boundary'],maxExposure=float(f.weather_index_100.max())))
    template=(ROOT/'src/templates/inspection_evidence.html').read_text('utf8')
    notice=json.loads((W/'terrain_context/summary.json').read_text('utf8'))['source_notice']
    template=template.replace('__DSM_NOTICE__',notice).replace('__DATA__',json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/'))
    assert '__DATA__' not in template and len(rows)==843 and len(scenarios)==75
    (B/'maps/sections.html').write_text(template,'utf8')
    print('구간 근거 탐색 화면:',len(rows),'구간,',len(scenarios),'기준 조합')

if __name__=='__main__':main()
