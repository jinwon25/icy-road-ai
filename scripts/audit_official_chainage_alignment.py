"""투영·공간 제외 오차·구간 교집합을 별도 계산으로 재검산한다."""
from bisect import bisect_right
from pathlib import Path
import sys
import json
import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def manual_interpolate(value, anchors, maximum_gap):
    ax=anchors.x_m.tolist();ay=anchors.km.tolist()
    if value<ax[0] or value>ax[-1]:return np.nan
    if value in ax:return ay[ax.index(value)]
    right=bisect_right(ax,value);left=right-1
    if ax[right]-ax[left]>maximum_gap:return np.nan
    return ay[left]+(ay[right]-ay[left])*(value-ax[left])/(ax[right]-ax[left])


def main():
    private=ROOT/'outputs/private';study=private/'official_chainage_alignment_20261031_v1'
    mapping=private/'vulnerability_map_comparison_20261031_v1';target=mapping/'independent_verification.json'
    assert not target.exists()
    s=read(study/'summary.json');m=read(mapping/'summary.json')
    for report,folder,key in [(s,study,'signatures'),(m,mapping,'source_signatures')]:
        for name,digest in report[key].items():assert sha(ROOT/name)==digest,name
        for name,digest in report['files'].items():assert sha(folder/name)==digest,name
    sources=read(study/'plan.json')['signatures']
    roadpath=next(ROOT/n for n in sources if n.endswith('official_directed_segment_candidates_v1/segments_500m.gpkg'))
    road=gpd.read_file(roadpath);projected=pd.read_csv(study/'all_projected_anchors.csv')
    transformer=Transformer.from_crs(4326,road.crs,always_xy=True)
    projection_checks=0
    for chain,part in projected.groupby('chain_id'):
        r=road.loc[road.chain_id.eq(chain)].reset_index(drop=True)
        for _,row in part.iterrows():
            point=Point(*transformer.transform(row.longitude,row.latitude))
            distances=r.geometry.distance(point).to_numpy();distance=distances.min()
            saved=r.loc[r.seg_id.eq(row.nearest_seg_id)].iloc[0]
            assert abs(saved.geometry.distance(point)-distance)<1e-7
            assert abs(distance-row.distance_m)<1e-7
            assert abs(saved.m0+saved.geometry.project(point)-row.x_m)<1e-7
            assert (distance<=100)==row.within_distance_gate
            projection_checks+=1
    anchors=pd.read_csv(study/'calibration_anchors.csv');validation=pd.read_csv(study/'spatial_validation.csv')
    cv_checks=0
    for _,row in validation.iterrows():
        pool=anchors.loc[anchors.chain_id.eq(row.chain_id)]
        if row.validation=='contiguous_5km_block':pool=pool.loc[pool.block.ne(row.block)]
        else:pool=pool.loc[pool.source_rows.ne(row.source_rows)]
        assert row.source_rows not in pool.source_rows.tolist()
        value=manual_interpolate(row.x_m,pool,10000)
        np.testing.assert_allclose(value,row.predicted_km,rtol=0,atol=1e-10,equal_nan=True)
        np.testing.assert_allclose((value-row.km)*1000,row.error_m,rtol=0,atol=1e-7,equal_nan=True)
        cv_checks+=1
    pieces=pd.read_csv(study/'piece_chainage.csv');inventories=pd.read_csv(mapping/'inventory_versions.csv')
    recorded=pd.read_csv(mapping/'overlap_sensitivity.csv')
    manual=[]
    for _,item in inventories.iterrows():
        pool=pieces.loc[pieces.chainage_available & pieces.route_nm.eq(item.route_nm)]
        for _,piece in pool.iterrows():
            for margin in [100,250,500]:
                start=piece.km_lo-margin/1000;end=piece.km_hi+margin/1000
                lo=max(start,item.start_km);hi=min(end,item.end_km)
                if hi<=lo:continue
                overlap=max(0.,min(piece.km_hi,item.end_km)-max(piece.km_lo,item.start_km))
                manual.append(dict(inventory_id=item.inventory_id,seg_id=piece.seg_id,piece_index=piece.piece_index,
                    margin_m=margin,nominal_overlap_km=overlap,possible_overlap_km=hi-lo,
                    boundary_relation='fully_inside_for_margin' if start>=item.start_km and end<=item.end_km else 'boundary_uncertain'))
    manual=pd.DataFrame(manual);keys=['inventory_id','seg_id','piece_index','margin_m']
    left=manual.sort_values(keys).reset_index(drop=True);right=recorded.sort_values(keys).reset_index(drop=True)
    assert left[keys+['boundary_relation']].equals(right[keys+['boundary_relation']])
    for col in ['nominal_overlap_km','possible_overlap_km']:
        np.testing.assert_allclose(left[col],right[col],rtol=0,atol=1e-12)
    geometry=gpd.read_file(private/'segment_exposure_20261009_v1/segments_500m.gpkg').set_index('seg_id')
    overlay=gpd.read_file(mapping/'comparison.gpkg',layer='estimated_inventory_overlay')
    for _,row in overlay.iterrows():
        geom=geometry.loc[row.seg_id].geometry
        assert row.geometry.difference(geom.buffer(1e-7)).length<1e-5
    screening=pd.read_csv(mapping/'segment_screening.csv');weather=pd.read_csv(mapping/'two_winter_exposure.csv')
    checks=0
    for _,row in screening.iterrows():
        w=weather.loc[weather.seg_id.eq(row.seg_id)]
        assert len(w)==2 and set(w.winter)=={2024,2025}
        assert row.stable_upper_quartile==bool((w.cold_wet_fraction>=w.route_q75).all())
        np.testing.assert_allclose([row.exposure_min,row.exposure_max],[w.cold_wet_fraction.min(),w.cold_wet_fraction.max()],rtol=0,atol=1e-12)
        assert row.field_review_candidate==(row.chainage_available and row.stable_upper_quartile and row.current_relation=='outside_inventory_for_margin')
        checks+=1
    result=dict(status='passed',projection_checks=projection_checks,spatial_validation_checks=cv_checks,
        overlap_records=len(manual),overlay_geometry_checks=len(overlay),two_winter_segment_checks=checks,
        alignment_summary_sha256=sha(study/'summary.json'),comparison_summary_sha256=sha(mapping/'summary.json'),
        audit_script_sha256=sha(Path(__file__)),protected_outcomes_read=False,
        independent_survey_validation=False)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
