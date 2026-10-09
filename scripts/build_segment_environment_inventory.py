"""도로 조각 전체와 교량·터널 도형의 2차원 교차를 계산한다."""
import json
import sys
import zipfile
from pathlib import Path
import geopandas as gpd
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.build_static_station_features import _extract_layer,_facilities,_distance


def main():
    private=ROOT/'outputs/private';spatial=private/'spatial'
    segments=gpd.read_file(spatial/'segment_scaffold/segments.gpkg')
    layers={};metadata={}
    with zipfile.ZipFile(spatial/'other_spatial.zip') as z:
        for name,stem in [('bridge','N3A_A0070000'),('tunnel','N3A_A0110020')]:
            layer,info=_facilities(_extract_layer(z,stem),segments)
            invalid=~layer.geometry.is_valid
            info['invalid_geometries_repaired']=int(invalid.sum())
            if invalid.any():layer.loc[invalid,'geometry']=layer.loc[invalid].geometry.make_valid()
            layers[name]=layer;metadata[name]=info
    rows=[]
    for row in segments.itertuples():
        values={'segment_id':row.seg_id,'length_m':row.length_m}
        for name,layer in layers.items():
            indices=layer.sindex.query(row.geometry,predicate='intersects')
            length=float(row.geometry.intersection(layer.geometry.iloc[indices].union_all()).length) if len(indices) else 0.
            if length>row.length_m+1e-5:raise AssertionError('Facility overlap longer than segment')
            values[name+'_overlap_2d_m']=length;values[name+'_overlap_2d_fraction']=length/row.length_m
            values[name+'_minimum_distance_m']=_distance(row.geometry,layer)
            values[name+'_polygon_intersects_2d']=bool(len(indices))
        rows.append(values)
    table=pd.DataFrame(rows)
    native=pd.read_csv(spatial/'environment_features/segment_features.csv').rename(columns={'seg_id':'segment_id'})
    dsm=pd.read_csv(private/'solar_terrain_features/segment_terrain.csv').rename(columns={'seg_id':'segment_id'})
    table=table.merge(native,on='segment_id',validate='one_to_one').merge(dsm,on='segment_id',validate='one_to_one')
    out=spatial/'environment_features';table.to_csv(out/'segment_environment_inventory.csv',index=False,encoding='utf-8-sig')
    summary={'segments':len(table),'layers':metadata,'bridge_intersecting_segments':int(table.bridge_polygon_intersects_2d.sum()),
             'tunnel_intersecting_segments':int(table.tunnel_polygon_intersects_2d.sum()),
             'bridge_overlap_2d_total_m':float(table.bridge_overlap_2d_m.sum()),'tunnel_overlap_2d_total_m':float(table.tunnel_overlap_2d_m.sum()),
             'limitations':['2D line/polygon overlap does not prove the same carriageway, level or direction.','Overlapping facility polygons are unioned before length measurement to avoid duplicate counts.',
                            'Native DEM values retain unknown vertical scaling; metre heights come only from the separately identified Copernicus DSM.',
                            'Curvature proxies are geometric samples, not official engineering radii.','No arbitrary bridge/tunnel risk weights assigned.']}
    (out/'segment_environment_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
