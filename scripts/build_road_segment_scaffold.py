"""Maximum 1-km geometry scaffold, with explicit disconnected-chain provenance."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file
from src.road_segments import prepare_chains, split_chain, endpoint_topology


def main():
    spatial = ROOT / 'outputs/private/spatial'
    source = spatial / 'jb_road_center_line.shp'
    roads = gpd.read_file(source)
    if roads.crs is None or roads.crs.to_epsg() != 5179:
        raise ValueError('Expected verified metric EPSG:5179 centerline')
    rows, summaries = [], []
    for route_index, (name, group) in enumerate(sorted(roads.groupby('NAME'), key=lambda x: x[0]), start=1):
        route_id = f'R{route_index:02}'
        chains = prepare_chains(group.geometry)
        source_length = float(group.length.sum())
        unique_length = float(group.geometry.union_all().length)
        # Duplicate/retraced roads need resolution before assigning geometric segment IDs.
        if abs(source_length - unique_length) > .01:
            raise ValueError(f'Overlapping centerline length: {route_id}')
        before = len(rows)
        for chain_index, chain in enumerate(chains, start=1):
            chain_id = f'{route_id}C{chain_index:04}'
            for part_index, (start, end, geometry) in enumerate(split_chain(chain), start=1):
                identity = hashlib.sha256(name.encode('utf-8') + geometry.wkb).hexdigest()[:16]
                rows.append({'seg_id': identity, 'route_id': route_id, 'route_nm': name,
                             'chain_id': chain_id, 'part_idx': part_index,
                             'chain_m0': start, 'chain_m1': end, 'length_m': geometry.length,
                             'risk_scr': np.nan, 'risk_stat': 'unscored', 'geometry': geometry})
        route_rows = rows[before:]
        segment_length = sum(row['length_m'] for row in route_rows)
        if abs(segment_length - source_length) > .001:
            raise AssertionError('Route length not conserved')
        summaries.append({'route_id': route_id, 'route_name': name, 'source_features': len(group),
                          'source_length_m': source_length, 'unique_length_m': unique_length,
                          'chain_count': len(chains), 'segment_count': len(route_rows),
                          'segment_length_m': segment_length,
                          'segments_under_100m': sum(r['length_m'] < 100 for r in route_rows),
                          **endpoint_topology(chains)})
    segments = gpd.GeoDataFrame(rows, crs=roads.crs)
    if segments.seg_id.duplicated().any() or not segments.length_m.between(0, 1000.000001, inclusive='right').all():
        raise AssertionError('Duplicate identity or invalid segment length')
    out = spatial / 'segment_scaffold'
    out.mkdir(parents=True, exist_ok=True)
    segments.to_file(out / 'segments.gpkg', layer='segments', driver='GPKG')
    segments.to_file(out / 'segments.shp', driver='ESRI Shapefile', encoding='UTF-8')
    roundtrip = gpd.read_file(out / 'segments.gpkg')
    shape_roundtrip = gpd.read_file(out / 'segments.shp')
    for reread in [roundtrip, shape_roundtrip]:
        if (len(reread) != len(segments) or reread.crs != segments.crs
                or not reread.seg_id.equals(segments.seg_id)
                or not reread.risk_scr.isna().all()
                or abs(reread.length.sum() - segments.length.sum()) > .001):
            raise AssertionError('Geometry export roundtrip mismatch')
    segments.drop(columns='geometry').to_csv(out / 'segment_inventory.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(summaries).to_csv(out / 'route_topology.csv', index=False, encoding='utf-8-sig')
    fig, ax = plt.subplots(figsize=(8, 9), layout='constrained')
    colors = ['#2d718e', '#5d8469', '#8b6e9e']
    for (route_id, group), color in zip(segments.groupby('route_id'), colors):
        group.plot(ax=ax, color=color, linewidth=1.3, label=route_id)
    ax.set_title('Road segment geometry scaffold\nMaximum 1 km per piece; no risk estimates')
    ax.set_xlabel('Easting (m), EPSG:5179')
    ax.set_ylabel('Northing (m), EPSG:5179')
    ax.legend(title='Source route ID', loc='lower right')
    ax.ticklabel_format(style='plain', axis='both', useOffset=False)
    fig.savefig(out / 'geometry_preview.jpg', dpi=180)
    plt.close(fig)
    summary = {'status': 'geometry_only_not_final_road_chainage_or_risk_map',
               'crs': str(segments.crs), 'max_segment_length_m': 1000,
               'segments': len(segments), 'routes': summaries,
               'source_length_m': float(roads.length.sum()), 'segment_length_m': float(segments.length.sum()),
               'source_hashes': {suffix: sha256_file(source.with_suffix(suffix)) for suffix in ['.shp', '.shx', '.dbf', '.prj']},
               'roundtrip_gpkg_and_shapefile_verified': True,
               'limitations': ['Endpoint-exact topology only. No snapping or inferred links.',
                               'Interior crossings not connected: bridges can cross in 2D.',
                               'Direction, chain orientation, ramps and mainline membership unverified.',
                               'Chain offsets reset at every disconnected/branch chain, not official highway kilometer posts.',
                               'Short chain tails retained; cannot claim uniform contiguous 1-km highway bins.',
                               'All risk scores null. This is not a completed competition risk map.']}
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
