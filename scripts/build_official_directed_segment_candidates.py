"""공식 방향별 링크의 연속 경로와 500m/1km 구간 후보를 비공개로 만든다.

행정권역 식별자는 경계 폴리곤의 대체물이 아니다. 실제 전북 경계와
역사적 선형·이용 조건 검증을 마칠 때까지 기존 추론 구간을 대체하지 않는다.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file
from src.directed_road_chains import audit_paths, split_path
from src.frozen_assessment import verify_freeze

ROUTES = {
    '서해안고속도로': ('15', '서해안고속국도', ['2950075300', '3410049000']),
    '호남고속도로': ('25', '호남고속국도', ['3080140300', '3420066800']),
    '통영대전고속도로': ('35', '통영-대전고속국도', ['3140115900', '3150089300']),
}
SOURCE_GAP_EXCEPTIONS = {('3070564500', '3070052700'): 6.391254}


def main():
    private = ROOT / 'outputs/private'
    review = private / 'spatial/official_nodelink_review_v1'
    reviewed = json.loads((review / 'summary.json').read_text(encoding='utf-8'))
    inventory = review / 'official_named_route_inventory.csv'
    if sha256_file(inventory) != reviewed['output_sha256'][inventory.name]:
        raise ValueError('Official reviewed inventory changed')
    archive = private / 'external/official_nodelink_20240325/NODELINKDATA.zip'
    if sha256_file(archive) != reviewed['archive_sha256']:
        raise ValueError('Official archive changed')
    out = private / 'spatial/official_directed_segment_candidates_v1'
    if out.exists():
        raise FileExistsError('Preserve existing candidate evidence')
    base = f'/vsizip/{archive.resolve().as_posix()}'
    source = pyogrio.read_dataframe(base + '/MOCT_LINK.shp',
        where="ROAD_RANK='101' AND ROAD_NO IN ('15','25','35')", encoding='CP949').to_crs(5179)
    expected_names = source.ROAD_NAME.isin(ROUTES)
    region = source.LINK_ID.str[:3].astype(int).between(305, 319)
    selected = source.loc[expected_names & region & source.ROAD_USE.eq('0') & source.CONNECT.eq('0')].copy()
    verified = pd.read_csv(inventory, dtype=str).set_index('LINK_ID')
    assert selected.LINK_ID.is_unique and len(selected) == 163
    assert verified.loc[selected.LINK_ID, 'orientation_check'].eq('geometry_order_matches_flow_nodes').all()
    nodes = pyogrio.read_dataframe(base + '/MOCT_NODE.shp', encoding='CP949').set_index('NODE_ID')
    turns = pyogrio.read_dataframe(base + '/TURNINFO.dbf', encoding='CP949', read_geometry=False)
    flagged = set(zip(turns.ST_LINK, turns.ED_LINK))
    transition_rows, chain_rows, link_rows, lineage = [], [], [], []
    segments = {500: [], 1000: []}
    sensitivities = []
    for name, (number, route_name, anchors) in ROUTES.items():
        pool = selected.loc[selected.ROAD_NAME.eq(name) & selected.ROAD_NO.eq(number)]
        records = pool.to_dict('records')
        by_id = {r['LINK_ID']: r for r in records}
        paths, candidates = audit_paths(records, review_pairs=flagged, gap_exceptions=SOURCE_GAP_EXCEPTIONS)
        transition_rows.extend({'route': route_name, **r} for r in candidates)
        endpoint_paths = []
        for path in paths:
            f, t = by_id[path[0]]['F_NODE'], by_id[path[-1]]['T_NODE']
            accepted = f != t and {f, t} == set(anchors)
            if accepted:
                endpoint_paths.append(path)
            for index, key in enumerate(path):
                link_rows.append({'route': route_name, 'path_first_link': path[0], 'path_order': index,
                                  'LINK_ID': key, 'F_NODE': by_id[key]['F_NODE'], 'T_NODE': by_id[key]['T_NODE'],
                                  'selected_anchor_path': accepted})
        if len(endpoint_paths) != 2:
            raise ValueError('Expected two opposite anchor paths; do not guess across breaks')
        for angle, tangent in [(30., 10.), (45., 30.), (60., 50.)]:
            check_paths, check_candidates = audit_paths(records, max_angle=angle, look_m=tangent,
                                        review_pairs=flagged, gap_exceptions=SOURCE_GAP_EXCEPTIONS)
            found = [p for p in check_paths if by_id[p[0]]['F_NODE'] != by_id[p[-1]]['T_NODE']
                     and {by_id[p[0]]['F_NODE'], by_id[p[-1]]['T_NODE']} == set(anchors)]
            same = {tuple(p) for p in found} == {tuple(p) for p in endpoint_paths}
            sensitivities.append({'route': route_name, 'max_angle_deg': angle, 'tangent_distance_m': tangent,
                                  'same_selected_link_sequences': same, 'anchor_paths_found': len(found),
                                  'rejected_forward_connections_json': json.dumps([
                                      r for r in check_candidates if r['angle_deg'] < 90
                                      and not r['status'].startswith('accepted')], ensure_ascii=False)})
        for path in endpoint_paths:
            rows = [by_id[key] for key in path]
            f, t = rows[0]['F_NODE'], rows[-1]['T_NODE']
            chain_id = hashlib.sha256((route_name + '/' + '/'.join(path)).encode()).hexdigest()[:16]
            flow = str(nodes.loc[f, 'NODE_NAME']) + '→' + str(nodes.loc[t, 'NODE_NAME'])
            gaps = [float(np.linalg.norm(np.array(a['geometry'].coords[-1]) - np.array(b['geometry'].coords[0])))
                    for a, b in zip(rows, rows[1:])]
            chain_rows.append({'chain_id': chain_id, 'route': route_name, 'flow_label': flow,
                               'start_node': f, 'end_node': t, 'start_node_type': nodes.loc[f, 'NODE_TYPE'],
                               'end_node_type': nodes.loc[t, 'NODE_TYPE'], 'links': len(path),
                               'geometric_length_m': sum(r['geometry'].length for r in rows),
                               'maximum_source_join_gap_m': max(gaps, default=0),
                               'official_chainage_verified': False, 'province_boundary_clip_verified': False})
            for size in segments:
                for index, piece in enumerate(split_path(rows, size)):
                    seg_id = hashlib.sha256(f'{chain_id}/{size}/{index}'.encode()).hexdigest()[:16]
                    segments[size].append({'seg_id': seg_id, 'route_nm': route_name, 'flow_lbl': flow,
                        'chain_id': chain_id, 'm0': piece['m0'], 'm1': piece['m1'],
                        'len_m': piece['geometry'].length, 'piece_n': piece['piece_count'],
                        'tail': piece['tail'], 'km_stat': 'local_only', 'risk_scr': np.nan,
                        'risk_stat': 'candidate', 'geometry': piece['geometry']})
                    lineage.extend({'seg_id': seg_id, 'chain_id': chain_id, 'size_m': size,
                                    'piece_order': i, **r} for i, r in enumerate(piece['lineage']))
    frozen = verify_freeze(ROOT)
    out.mkdir(parents=True)
    pd.DataFrame(transition_rows).to_csv(out / 'transition_audit.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(chain_rows).to_csv(out / 'directed_paths.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(link_rows).to_csv(out / 'source_link_membership.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(lineage).to_csv(out / 'segment_source_lineage.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(sensitivities).to_csv(out / 'angle_tangent_sensitivity.csv', index=False, encoding='utf-8-sig')
    totals = {}
    for size, records in segments.items():
        frame = gpd.GeoDataFrame(records, crs=5179)
        assert frame.seg_id.is_unique and frame.len_m.between(0, size + 1e-6, inclusive='right').all()
        assert frame.risk_scr.isna().all()
        expected = sum(r['geometric_length_m'] for r in chain_rows)
        assert abs(frame.length.sum() - expected) < 1e-6
        frame.to_file(out / f'segments_{size}m.gpkg', driver='GPKG')
        frame.to_file(out / f'segments_{size}m.shp', driver='ESRI Shapefile', encoding='UTF-8')
        for suffix in ['gpkg', 'shp']:
            reread = gpd.read_file(out / f'segments_{size}m.{suffix}')
            assert reread.seg_id.equals(frame.seg_id) and reread.crs.to_epsg() == 5179
            assert reread.risk_scr.isna().all()
            assert abs(reread.length.sum() - expected) < 1e-6
        totals[str(size)] = {'segments': len(frame), 'tails': int(frame['tail'].sum()),
                            'multipart_segments': int(frame.piece_n.gt(1).sum()),
                            'directed_length_sum_m': float(frame.length.sum())}
    result = {'status': 'directed_500m_1km_candidates_boundary_and_rights_pending',
        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'region_id_range': [305, 319],
        'source_non_ramp_regional_links': len(selected), 'selected_path_links': sum(r['links'] for r in chain_rows),
        'directional_paths': chain_rows, 'sizes_m': totals,
        'angular_sensitivity_checks_passed': sum(r['same_selected_link_sequences'] for r in sensitivities),
        'angular_sensitivity_checks_total': len(sensitivities),
        'angular_sensitivity_review': sensitivities,
        'all_angular_choices_stable': all(r['same_selected_link_sequences'] for r in sensitivities),
        'final_geometry_approved': False,
        'geometry_roundtrips_gpkg_shp_verified': True, 'source_gaps_filled': False,
        'continuity_gap_qa_m': 1., 'explicit_source_gap_exceptions_max_m': {'3070564500/3070052700': 6.391254},
        'source_gap_exception_review': {'shared_official_node': '3070024800',
            'gap_m': 6.391253088792269, 'angle_deg': 14.352467504613228,
            'both_links_node_orientation_passed': True, 'turn_record_between_links': False,
            'physical_contiguity_claimed': False, 'gap_added_to_length': False},
        'official_chainage_verified': False, 'province_boundary_clip_verified': False,
        'final_submission_use_rights_confirmed': False, 'risk_scored': False,
        'protected_outcomes_used': False, 'frozen_files_unchanged': len(frozen['files']),
        'source_sha256': {'archive': reviewed['archive_sha256'], 'reviewed_inventory': sha256_file(inventory),
                          'builder': sha256_file(Path(__file__)),
                          'path_module': sha256_file(ROOT / 'src/directed_road_chains.py')},
        'outputs_sha256': {p.name: sha256_file(p) for p in out.iterdir() if p.is_file()},
        'limitations': ['Regional identifiers are not a verified province polygon: Honam anchors include Nonsan JC and a tunnel endpoint.',
            'Six chosen anchor paths are geometric continuity candidates, not certification of legal travel movements.',
            'Official ITS direction-separated lines can be offset from physical carriageways.',
            'Source WKT transformation contains unverified ballpark datum offset, recorded in the preceding review.',
            'Gaps remain as separate original line pieces; no connector distance is added. One audited 6.39m source gap is an explicit exception to the 1m continuity QA.',
            '500m/1km distances reset at candidate path origin; these are not official highway kilometer posts.',
            'End tails are shorter; proper administrative clipping will require rebuilding candidates under a new version.',
            'Existing 467 inference segments, frozen models and submission draft v1 remain unchanged.']}
    (out / 'builder_source_snapshot.py').write_bytes(Path(__file__).read_bytes())
    (out / 'path_module_snapshot.py').write_bytes((ROOT / 'src/directed_road_chains.py').read_bytes())
    (out / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
