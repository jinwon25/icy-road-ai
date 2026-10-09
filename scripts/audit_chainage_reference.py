"""연구 지도 이정 참조를 도형과 대조한다. 공식 이정·방향으로 확정하지 않는다."""
import json
import re
import sys
from pathlib import Path
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString
from shapely.strtree import STRtree

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file

ROUTES={'서해안고속국도':'150','호남고속국도':'250','통영-대전고속국도':'350'}
PROJECT_ROUTES={'서해안':'서해안고속국도','호남선':'호남고속국도','통영-대전중부선':'통영-대전고속국도'}


def main():
    private=ROOT/'outputs/private';sources=private/'external/uos_chainage_reference'
    paths=json.loads((sources/'selected_paths.json').read_text(encoding='utf-8'))
    segments=gpd.read_file(private/'spatial/segment_scaffold/segments.gpkg')
    records=[];reference_records=[]
    for route,code in ROUTES.items():
        rows=[]
        for edge in paths[code]:
            a,b=edge['from'],edge['to']
            km0=float(re.fullmatch(r'([0-9.]+)m 지점',a['name']).group(1))
            km1=float(re.fullmatch(r'([0-9.]+)m 지점',b['name']).group(1))
            if not np.isclose(km1-km0,.1):raise ValueError('Unexpected chainage increment')
            rows.append({'route':route,'reference_code':code,'km0_candidate':km0,'km1_candidate':km1,'geometry':LineString([a['coordinates'],b['coordinates']])})
        edges=gpd.GeoDataFrame(rows,crs=4326).to_crs(segments.crs).reset_index(drop=True)
        # 이름의 m 표기는 좌표 간격과 다르다. km 해석은 기하 검증에 근거한 후보다.
        if not 95<edges.length.median()<105:raise ValueError('Inconsistent reference distance units')
        tree=STRtree(edges.geometry.to_numpy());reference_records.extend(edges.to_dict(orient='records'))
        for row in segments.loc[segments.route_nm.eq(route)].itertuples():
            distances=np.unique(np.r_[np.arange(0,row.geometry.length,50.),row.geometry.length/2,row.geometry.length])
            points=np.array([row.geometry.interpolate(d) for d in distances],dtype=object)
            indices,nearest_distances=tree.query_nearest(points,all_matches=False,return_distance=True)
            order=np.argsort(indices[0]);edge_indices=indices[1][order];nearest_distances=nearest_distances[order]
            if not np.array_equal(indices[0][order],np.arange(len(points))):raise AssertionError('Missing reference point')
            chosen=edges.iloc[edge_indices]
            fractions=np.array([g.project(point,normalized=True) for g,point in zip(chosen.geometry,points)])
            km=chosen.km0_candidate.to_numpy()+fractions*(chosen.km1_candidate-chosen.km0_candidate).to_numpy()
            delta=km[-1]-km[0];sign=1 if delta>=0 else -1
            monotone=bool((np.diff(km)*sign>=-.001).all())
            span_m=abs(delta)*1000;length_error=abs(span_m-row.geometry.length)
            distance_ok=bool(nearest_distances.max()<=50.)
            length_ok=bool(length_error<=max(20.,.2*row.geometry.length))
            status='research_chainage_candidate' if distance_ok and length_ok and monotone else 'manual_geometry_review_required'
            records.append({'segment_id':row.seg_id,'route':route,'reference_code':code,
                            'km_start_candidate':float(km[0]),'km_end_candidate':float(km[-1]),
                            'km_min_candidate':float(km.min()),'km_max_candidate':float(km.max()),
                            'midpoint_km_candidate':float(km[np.argmin(abs(distances-row.geometry.length/2))]),
                            'max_reference_distance_m':float(nearest_distances.max()),'length_error_m':float(length_error),
                            'sample_points':len(points),'monotone_candidate':monotone,'distance_check':distance_ok,'length_check':length_ok,
                            'chainage_status':status,'official_chainage_verified':False,'direction_status':'unresolved'})
    result=pd.DataFrame(records)
    if len(result)!=467 or not result.segment_id.is_unique:raise AssertionError('Incomplete chainage comparison')
    out=private/'spatial/chainage_reference';out.mkdir(exist_ok=True)
    result.to_csv(out/'segment_chainage_candidates.csv',index=False,encoding='utf-8-sig')
    refs=gpd.GeoDataFrame(reference_records,crs=segments.crs)
    refs.to_file(out/'research_reference.gpkg',layer='reference_not_official',driver='GPKG')
    official=pd.read_csv(sources/'official_vulnerable_sections.csv')
    links=[];coverage=[]
    accepted=result.loc[result.chainage_status.eq('research_chainage_candidate')]
    for r in official.loc[official.within_three_route_scope].itertuples():
        route=PROJECT_ROUTES[r.project_route];pool=accepted.loc[accepted.route.eq(route)]
        intersections=[]
        for seg in pool.itertuples():
            begin=max(r.start_km,seg.km_min_candidate);end=min(r.end_km,seg.km_max_candidate)
            if end>begin:
                intersections.append((begin,end));links.append({'official_row':r.official_row,'official_route':r.official_route,
                    'official_grade':r.grade,'segment_id':seg.segment_id,'overlap_start_km_candidate':begin,'overlap_end_km_candidate':end,
                    'overlap_km_candidate':end-begin,'match_status':'research_reference_overlap_not_official_geometry','direction_status':'unresolved'})
        # 평행한 도형의 중복을 구간 연장에 더하지 않는다.
        merged=[]
        for begin,end in sorted(intersections):
            if merged and begin<=merged[-1][1]:merged[-1][1]=max(end,merged[-1][1])
            else:merged.append([begin,end])
        covered=sum(end-begin for begin,end in merged)
        coverage.append({'official_row':r.official_row,'official_route':r.official_route,'official_grade':r.grade,
                         'start_km':r.start_km,'end_km':r.end_km,'reported_length_km':r.reported_length_km,
                         'reference_overlap_km_candidate':covered,'fraction_candidate':covered/r.reported_length_km,
                         'candidate_segments':len(intersections),'official_geometry_verified':False})
    pd.DataFrame(links).to_csv(out/'official_sections_candidate_links.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(coverage).to_csv(out/'official_sections_candidate_coverage.csv',index=False,encoding='utf-8-sig')
    summary={'status':'research_chainage_candidates_not_official_alignment','segments':len(result),
             'passes_geometry_checks':int(result.chainage_status.eq('research_chainage_candidate').sum()),
             'requires_manual_review':int(result.chainage_status.eq('manual_geometry_review_required').sum()),
             'per_route':{route:{'segments':len(part),'passes':int(part.chainage_status.eq('research_chainage_candidate').sum()),
                          'max_distance_m':float(part.max_reference_distance_m.max()),'km_min_candidate':float(part.km_min_candidate.min()),'km_max_candidate':float(part.km_max_candidate.max())} for route,part in result.groupby('route')},
             'official_sections_in_scope':len(coverage),'sections_with_candidate_overlap':sum(r['candidate_segments']>0 for r in coverage),
             'unique_official_chainage_overlap_km_candidate':sum(r['reference_overlap_km_candidate'] for r in coverage),
             'thresholds':{'sample_spacing_m':50.,'max_distance_m':50.,'length_error_m':'max(20, 0.2*segment length)','monotonicity_tolerance_m':1.},
             'source_sha256':sha256_file(sources/'selected_paths.json'),
             'limitations':['Research viewer, not organizer-approved chainage-coordinate table.',
                            'Reference point names say m, but 0.1 units correspond to approximately100m; km interpretation remains a verified geometric inference.',
                            'Viewer RouteInfo mislabels/misses some RoutePath codes;250 is matched by geometry, not its incorrect251 name.',
                            'No identified travel direction, ramps, official history date or redistribution licence.',
                            'Geometry QA thresholds are analyst choices, not organizer-approved tolerances.',
                            'Candidate interval overlap is not validated facility or vulnerability membership.']}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
