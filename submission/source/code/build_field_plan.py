"""선정 범위와 같은 기상 입력을 공유하는 인접 비교 후보 및 계측 계획을 생성한다."""
from pathlib import Path
import argparse, json, hashlib, html
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from pyproj import Transformer

ROOT=Path(__file__).resolve().parents[1]

def sha(p):
    with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def js(v):return json.dumps(v,ensure_ascii=False,allow_nan=False).replace('</','<\\/')

def make_map(context,selected,comparison,representative):
    shapes=[*selected.geometry,comparison.geometry,representative]
    lo=np.min([g.bounds[:2] for g in shapes],axis=0)-220
    hi=np.max([g.bounds[2:] for g in shapes],axis=0)+220
    cx,cy=(lo+hi)/2
    width=max(float(hi[0]-lo[0]),float(hi[1]-lo[1])*1.6,1200)
    height=width/1.6
    xmin,ymin=cx-width/2,cy-height/2
    def xy(x,y):return ((x-xmin)/width*800,500-(y-ymin)/height*500)
    def path(g):
        parts=list(g.geoms) if g.geom_type=='MultiLineString' else [g]
        return ' '.join('M'+' L'.join(f'{a:.2f},{b:.2f}' for a,b in (xy(x,y) for x,y,*_ in part.coords)) for part in parts)
    out=['<svg viewBox="0 0 800 500" role="img" aria-label="선정 범위의 대표 중점과 인접 비교 구간 지도">',
         '<rect width="800" height="500" fill="#f4f7f8"/>']
    for g in context.geometry:
        out.append(f'<path d="{path(g)}" fill="none" stroke="#b7c6ce" stroke-width="3"/>')
    for g in selected.geometry:
        out.append(f'<path d="{path(g)}" fill="none" stroke="#29546d" stroke-width="9" stroke-linecap="round"/>')
    out.append(f'<path d="{path(comparison.geometry)}" fill="none" stroke="#815722" stroke-width="7" stroke-dasharray="9 5"/>')
    for label,p,color in [('A',representative,'#29546d'),('B',comparison.geometry.interpolate(.5,normalized=True),'#815722')]:
        x,y=xy(p.x,p.y)
        out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="16" fill="{color}" stroke="white" stroke-width="3"/>')
        out.append(f'<text x="{x:.2f}" y="{y+5:.2f}" fill="white" text-anchor="middle" font-size="16" font-family="sans-serif" font-weight="bold">{label}</text>')
    scale=500/width*800
    out.extend(['<path d="M752 54 V22 M746 33 L752 22 L758 33" fill="none" stroke="#26343d" stroke-width="2"/>',
        '<text x="752" y="75" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#26343d">N</text>',
        f'<path d="M35 452 H{35+scale:.2f}" stroke="#26343d" stroke-width="3"/>',
        '<text x="35" y="480" font-family="sans-serif" font-size="15" fill="#26343d">500 m</text></svg>'])
    return ''.join(out)

def build(output):
    assert not output.exists(),'Use a fresh output directory'
    inputs=[ROOT/'results/sections'/n for n in ['section_review.csv','inspection_areas.csv','field_review_plan.csv','risk_review.gpkg']]
    inputs+=[ROOT/'results/sections/terrain/segment_solar_context.csv']
    review=pd.read_csv(inputs[0],dtype={'seg_id':str},float_precision='round_trip')
    areas=pd.read_csv(inputs[1],float_precision='round_trip')
    plans=pd.read_csv(inputs[2],float_precision='round_trip').set_index('area_id')
    terrain=pd.read_csv(inputs[-1],dtype={'seg_id':str},float_precision='round_trip')
    geoms=gpd.read_file(inputs[3],layer='winter_2024',engine='pyogrio').to_crs(5179)
    assert len(review)==1686 and len(geoms)==843 and set(areas.area_id)=={'S01','S02'}
    assert not review.duplicated(['seg_id','winter']).any()
    weather=review.pivot(index='seg_id',columns='winter',values='weather_information_group')
    first=review.loc[review.winter.eq(2024)].set_index('seg_id')
    availability=review.groupby('seg_id').condition_availability.min()
    selected_ids=set(review.loc[review.inspection_candidate,'seg_id'])
    assert len(selected_ids)==3
    to_xy=Transformer.from_crs(4326,5179,always_xy=True)
    to_ll=Transformer.from_crs(5179,4326,always_xy=True)
    geoms=geoms.set_index('seg_id',drop=False)
    midpoint=geoms.geometry.interpolate(.5,normalized=True)
    cases=[];records=[];points=[]
    for area in areas.sort_values('area_id').itertuples():
        p=plans.loc[area.area_id]
        representative=Point(*to_xy.transform(p.representative_midpoint_lon,p.representative_midpoint_lat))
        members=first.index[first.inspection_area_id.eq(area.area_id)]
        assert len(members)==area.segments
        signature=weather.loc[members[0]]
        assert weather.loc[members].eq(signature).all().all()
        eligible=first.index[(first.route_nm==area.route)&(first.flow_lbl==area.direction)&first.chainage_available]
        eligible=[i for i in eligible if i not in selected_ids and availability.loc[i]>=.95 and
                  weather.loc[i].equals(signature) and midpoint.loc[i].distance(representative)<=2000]
        assert eligible,f'No matching comparison candidate for {area.area_id}'
        candidates=sorted(eligible,key=lambda i:(midpoint.loc[i].distance(representative),i))
        cid=candidates[0];c=first.loc[cid];cg=geoms.loc[cid];cp=midpoint.loc[cid]
        lon,lat=to_ll.transform(cp.x,cp.y)
        distance=cp.distance(representative)
        context=geoms.loc[geoms.geometry.distance(representative)<=2500]
        svg=make_map(context,geoms.loc[members],cg,representative)
        shade=terrain.loc[terrain.seg_id.isin(members)]
        comp_shade=terrain.loc[terrain.seg_id.eq(cid)]
        item=dict(id=area.area_id,route=area.route,direction=area.direction,
            start_km=float(area.estimated_km_start),end_km=float(area.estimated_km_end),
            segments=int(area.segments),length_km=float(area.directional_length_km),
            selection_fraction=float(p.minimum_selection_fraction),
            exposure=[float(area.exposure_pct_2024),float(area.exposure_pct_2025)],
            shade_range_pct=[float(100*shade.potential_shade_daylight_fraction.min()),float(100*shade.potential_shade_daylight_fraction.max())],
            shade_1km_range_pct=[float(100*shade.potential_shade_daylight_fraction_1km.min()),float(100*shade.potential_shade_daylight_fraction_1km.max())],
            curve_range=[float(first.loc[members,'curve_deg_100m'].min()),float(first.loc[members,'curve_deg_100m'].max())],
            selected=dict(lat=float(p.representative_midpoint_lat),lon=float(p.representative_midpoint_lon),
                ids=sorted(members.tolist()),information_groups=1),
            comparator=dict(id=cid,start_km=float(c.estimated_km_lo),end_km=float(c.estimated_km_hi),
                lat=float(lat),lon=float(lon),distance_m=float(distance),
                inventory_relation=str(c.current_relation),bridge_fraction=float(c.bridge_code_fraction),
                tunnel_fraction=float(c.tunnel_code_fraction),curve_deg_100m=float(c.curve_deg_100m),
                environment_context=bool(c.environment_context),
                shade_pct=float(100*comp_shade.potential_shade_daylight_fraction.mean())),
            svg=svg)
        cases.append(item)
        records.append(dict(area_id=area.area_id,comparison_seg_id=cid,
            comparison_km_start=item['comparator']['start_km'],comparison_km_end=item['comparator']['end_km'],
            comparison_midpoint_lat=lat,comparison_midpoint_lon=lon,representative_distance_m=distance,
            weather_information_groups_match_both_winters=True,minimum_availability=float(availability.loc[cid]),
            inventory_relation=str(c.current_relation),environment_context=bool(c.environment_context),
            comparison_selected_by_reference_criteria=False,official_location_verified=False))
        for pos,point,ident in [('A',representative,','.join(members)),('B',cp,cid)]:
            points.append(dict(area_id=area.area_id,position=pos,seg_ids=ident,geometry=point,
                               official_location_verified=False))
    output.mkdir(parents=True)
    pd.DataFrame(records).to_csv(output/'comparison_candidates.csv',index=False,encoding='utf-8-sig')
    gpd.GeoDataFrame(points,crs=5179).to_file(output/'measurement_plan.gpkg',layer='representative_points',driver='GPKG',engine='pyogrio')
    protocol=[('위치','관리기관 도면·방향·구조물을 대조해 대표 중점과 실제 계측 위치를 확인'),
              ('동시 비교','A·B의 같은 10분 KST 시각에 온도·수분 상태를 함께 기록'),
              ('관리 이력','잔류염분과 마지막 제설·제빙 시각, 통행·차로 조건을 기록'),
              ('환경 확인','배수·차폐·구조물을 현장에서 확인하고 DSM 추정과 비교'),
              ('판정 대조','노면온도 0°C 이하와 실제 Ice를 구분해 측정 누락도 함께 보존')]
    pd.DataFrame(protocol,columns=['item','planned_check']).to_csv(output/'measurement_protocol.csv',index=False,encoding='utf-8-sig')
    (output/'field_cases.json').write_text(js(cases)+'\n','utf8')
    template=(ROOT/'assets/field_plan_template.html').read_text('utf8')
    (output/'index.html').write_text(template.replace('__FIELD_DATA__',js(cases)),'utf8')
    summary=dict(status='field_comparison_plan_built',areas=2,reference_selected_segments=3,comparison_candidates=len(records),
        source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in inputs},
        source_template_sha256=sha(ROOT/'assets/field_plan_template.html'),
        outcome_columns_used=False,protected_outcomes_used=False,production_predictions_changed=False,
        actual_field_measurements=0,location_verified=False,
        interpretation='인접 비교 후보의 선정은 같은 기상 입력과 거리 기준의 계획이다. 현장 안전·설치 적합성·인과효과를 확인한 결과가 아니다.')
    (output/'summary.json').write_text(js(summary)+'\n','utf8')
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(js(build(args.output.resolve())),flush=True)
