"""암거 이정으로 도로 위치를 보간하고 공간 블록 제외·별도 CCTV 자료로 점검한다."""
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.chainage_alignment import aggregate_anchors, interpolate_checked
from src.data_source import sha256_file as sha

PRIVATE = ROOT / 'outputs/private'
OUT = PRIVATE / 'official_chainage_alignment_20261031_v1'
SOURCES = {
    'anchors': PRIVATE / 'official_culvert_anchors_20261031_v2/anchors.csv',
    'source_audit': PRIVATE / 'official_culvert_anchors_20261031_v2/summary.json',
    'roads': PRIVATE / 'releases/20261007/outputs/private/spatial/official_directed_segment_candidates_v1/segments_500m.gpkg',
    'clipped': PRIVATE / 'segment_exposure_20261009_v1/segments_500m.gpkg',
    'cctv': PRIVATE / 'releases/20261007/outputs/private/spatial/official_chainage_anchors/anchor_comparison.csv',
}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def project_points(frame, road, route_column):
    points = gpd.GeoDataFrame(frame.copy(), geometry=gpd.points_from_xy(frame.longitude, frame.latitude), crs=4326).to_crs(road.crs)
    result = []
    for (route, flow, chain), segments in road.groupby(['route_nm','flow_lbl','chain_id']):
        segments = segments.reset_index(drop=True)
        tree = STRtree(segments.geometry.to_numpy())
        for _, row in points.loc[points[route_column].eq(route)].iterrows():
            edge = segments.iloc[int(tree.nearest(row.geometry))]
            distance = float(row.geometry.distance(edge.geometry))
            # m0는 원래 선형의 누적 거리다. 경계로 자른 선형의 m0를 사용하지 않는다.
            result.append({**row.drop('geometry').to_dict(), 'route_nm':route, 'flow_lbl':flow,
                'chain_id':chain, 'nearest_seg_id':edge.seg_id, 'distance_m':distance,
                'x_m':float(edge.m0+edge.geometry.project(row.geometry)),
                'within_distance_gate':distance<=100})
    return pd.DataFrame(result)


def error_summary(frame):
    values = frame.error_m.dropna().abs()
    return dict(total=len(frame), predicted=len(values), no_extrapolation_unavailable=len(frame)-len(values),
                mae_m=None if not len(values) else float(values.mean()),
                p95_abs_m=None if not len(values) else float(values.quantile(.95)),
                max_abs_m=None if not len(values) else float(values.max()),
                within_100m=None if not len(values) else float(values.le(100).mean()),
                within_250m=None if not len(values) else float(values.le(250).mean()),
                within_500m=None if not len(values) else float(values.le(500).mean()))


def main():
    assert json.loads(SOURCES['source_audit'].read_text(encoding='utf-8'))['status']=='source_verified'
    OUT.mkdir(parents=True, exist_ok=False)
    inputs = [*SOURCES.values(), Path(__file__), ROOT/'src/chainage_alignment.py']
    signatures = {p.relative_to(ROOT).as_posix():sha(p) for p in inputs}
    write(OUT/'plan.json', dict(at_utc=datetime.now(timezone.utc).isoformat(), signatures=signatures,
        max_lateral_distance_m=100, max_interpolation_anchor_gap_m=3000, block_width_m=5000,
        validation_max_gap_m=10000, sensitivity_m=[100,250,500], primary_margin_m=250,
        coordinate_duplicates_grouped=True, extrapolation=False, protected_outcomes_used=False,
        cctv_for_diagnostics_only=True, official_chainage_verified=False))
    road = gpd.read_file(SOURCES['roads'])
    clipped = gpd.read_file(SOURCES['clipped'])
    anchors = pd.read_csv(SOURCES['anchors'])
    anchors = anchors.loc[anchors.source_coordinate_valid & anchors.in_three_route_scope & anchors.chainage_km.notna()]
    projected = project_points(anchors, road, 'route')
    projected.to_csv(OUT/'all_projected_anchors.csv', index=False, encoding='utf-8-sig')
    cctv = project_points(pd.read_csv(SOURCES['cctv']), road, 'route')
    calibration = {}; groups=[]; validations=[]
    for chain, part in projected.loc[projected.within_distance_gate].groupby('chain_id'):
        unique, sign = aggregate_anchors(part)
        unique['chain_id']=chain; unique['route_nm']=part.route_nm.iloc[0]; unique['flow_lbl']=part.flow_lbl.iloc[0]
        unique['block']=np.floor(unique.x_m/5000).astype(int)
        calibration[chain]=unique; groups.append(unique)
        for block in sorted(unique.block.unique()):
            train=unique.loc[unique.block.ne(block)]; held=unique.loc[unique.block.eq(block)].copy()
            held['predicted_km'], held['bracket_gap_m'], held['available']=interpolate_checked(held.x_m,train,10000)
            held['error_m']=(held.predicted_km-held.km)*1000
            held['validation']='contiguous_5km_block'; validations.append(held)
        for index in unique.index:
            train=unique.drop(index); held=unique.loc[[index]].copy()
            held['predicted_km'], held['bracket_gap_m'], held['available']=interpolate_checked(held.x_m,train,10000)
            held['error_m']=(held.predicted_km-held.km)*1000
            held['validation']='leave_coordinate_out'; validations.append(held)
        c = cctv.loc[cctv.chain_id.eq(chain) & cctv.within_distance_gate]
        pred,gap,ok=interpolate_checked(c.x_m,unique)
        cctv.loc[c.index,'predicted_km']=pred; cctv.loc[c.index,'bracket_gap_m']=gap
        cctv.loc[c.index,'available']=ok
    all_unique=pd.concat(groups,ignore_index=True); all_unique.to_csv(OUT/'calibration_anchors.csv',index=False,encoding='utf-8-sig')
    validation=pd.concat(validations,ignore_index=True);validation.to_csv(OUT/'spatial_validation.csv',index=False,encoding='utf-8-sig')
    cctv['error_m']=(cctv.predicted_km-cctv.official_chainage_km)*1000
    cctv['diagnostic_only']=True
    cctv.to_csv(OUT/'cctv_independent_diagnostic.csv',index=False,encoding='utf-8-sig')
    original=road.set_index('seg_id'); records=[]; piece_records=[]
    for _,seg in clipped.iterrows():
        origin=original.loc[seg.seg_id]
        assert origin.chain_id==seg.chain_id and origin.route_nm==seg.route_nm
        a=calibration[seg.chain_id]; geometry=seg.geometry
        pieces=list(geometry.geoms) if geometry.geom_type=='MultiLineString' else [geometry]
        valid_pieces=[]
        for piece_index,piece in enumerate(pieces):
            from shapely.geometry import Point
            x=np.array([origin.m0+origin.geometry.project(Point(piece.coords[0])),
                        origin.m0+origin.geometry.project(Point(piece.coords[-1]))])
            assert np.all(x>=origin.m0-1e-5) and np.all(x<=origin.m1+1e-5)
            km,gap,ok=interpolate_checked(x,a)
            # 내부에 기준점 공백이 있으면 양 끝만 통과하더라도 해당 조각을 확정하지 않는다.
            middle=a.x_m.between(min(x),max(x))
            probes=np.r_[x,a.loc[middle,'x_m'].to_numpy()]
            probes=np.unique(np.sort(probes)); midpoints=(probes[:-1]+probes[1:])/2
            _,inner_gap,inner_ok=interpolate_checked(midpoints,a)
            available=bool(ok.all() and inner_ok.all())
            rec=dict(seg_id=seg.seg_id,route_nm=seg.route_nm,flow_lbl=seg.flow_lbl,chain_id=seg.chain_id,
                piece_index=piece_index,x0_m=float(x[0]),x1_m=float(x[1]),length_m=float(piece.length),
                chainage_available=available,km_lo=float(min(km)) if available else None,
                km_hi=float(max(km)) if available else None,
                max_anchor_gap_m=float(max(np.r_[gap,inner_gap])),official_chainage_verified=False)
            piece_records.append(rec)
            if available: valid_pieces.append(rec)
        all_ok=len(valid_pieces)==len(pieces)
        records.append(dict(seg_id=seg.seg_id,route_nm=seg.route_nm,flow_lbl=seg.flow_lbl,
            chain_id=seg.chain_id,length_m=float(seg.geometry.length),piece_count=len(pieces),
            chainage_available=all_ok,estimated_km_lo=min(r['km_lo'] for r in valid_pieces) if all_ok else None,
            estimated_km_hi=max(r['km_hi'] for r in valid_pieces) if all_ok else None,
            valid_piece_length_m=sum(r['length_m'] for r in valid_pieces),official_chainage_verified=False))
    pieces=pd.DataFrame(piece_records); segments=pd.DataFrame(records)
    pieces.to_csv(OUT/'piece_chainage.csv',index=False,encoding='utf-8-sig')
    segments.to_csv(OUT/'segment_chainage.csv',index=False,encoding='utf-8-sig')
    summary=dict(status='candidate_alignment_complete',
        distinct_coordinate_anchors=int(all_unique[['longitude','latitude']].drop_duplicates().shape[0]),
        source_facilities_within_100m=int(projected.loc[projected.within_distance_gate,'source_row'].nunique()),
        direction_anchor_records=len(all_unique), validation={kind:error_summary(part) for kind,part in validation.groupby('validation')},
        validation_by_chain={chain:error_summary(part) for chain,part in validation.loc[validation.validation.eq('contiguous_5km_block')].groupby('chain_id')},
        cctv_diagnostic=error_summary(cctv.loc[cctv.within_distance_gate]),
        segments=len(segments),fully_interpolated_segments=int(segments.chainage_available.sum()),
        total_directional_length_m=float(segments.length_m.sum()),interpolated_piece_length_m=float(segments.valid_piece_length_m.sum()),
        official_chainage_verified=False,independent_survey_validation=False,protected_outcomes_used=False,
        limitations=['공식 암거 목록 안에서의 공간 제외 검증이며 독립 측량 검증이 아니다.',
            'CCTV는 고유 이름으로 결합한 후보 자료로 카메라명·이정 오류 가능성이 있어 진단만 수행한다.',
            '양방향 선형에 같은 시설점을 투영하므로 방향별 오차 결과를 독립 표본으로 합산하지 않는다.',
            '2026년 자료로 2024·2025년 시설 위치와 지정 현황을 소급 확정하지 않는다.',
            '250m 오차 띠는 분석자가 고정한 민감도 범위이며 통계적 신뢰구간이나 공식 허용오차가 아니다.',
            '외삽 및 3km 초과 기준점 공백을 허용하지 않는다. 도로 경계 밖 취약구간을 지도 안으로 옮기지 않는다.'],
        signatures=signatures)
    assert signatures=={p.relative_to(ROOT).as_posix():sha(p) for p in inputs}
    summary['files']={p.name:sha(p) for p in OUT.iterdir() if p.is_file()}
    write(OUT/'summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ['signatures','files']},ensure_ascii=False))


if __name__=='__main__':main()
