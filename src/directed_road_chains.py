"""방향별 공식 링크의 연속성 감사와 원형을 보존한 거리 분할."""
from collections import defaultdict
from math import acos, ceil, degrees, hypot

from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import substring


def connection_angle(a, b, look_m=30.):
    if look_m <= 0:
        raise ValueError('Positive tangent distance required')
    x = a.coords[-1]
    y = a.interpolate(max(0., a.length - look_m)).coords[0]
    z = b.coords[0]
    w = b.interpolate(min(look_m, b.length)).coords[0]
    u, v = (x[0] - y[0], x[1] - y[1]), (w[0] - z[0], w[1] - z[1])
    norm = hypot(*u) * hypot(*v)
    if norm <= 0:
        raise ValueError('Degenerate tangent')
    return degrees(acos(max(-1., min(1., (u[0] * v[0] + u[1] * v[1]) / norm))))


def audit_paths(records, max_angle=45., max_gap=1., look_m=30., review_pairs=(), gap_exceptions=None):
    """합법적 통행 경로의 인증이 아닌 도형·노드 연속성 후보를 만든다."""
    if not 0 < max_angle < 90 or max_gap < 0 or look_m <= 0:
        raise ValueError('Invalid continuity QA choices')
    edges = {}
    starts = defaultdict(list)
    for row in records:
        key = str(row['LINK_ID'])
        g = row['geometry']
        if key in edges or not isinstance(g, LineString) or not g.is_valid or g.length <= 0 or g.is_ring:
            raise ValueError('Duplicate, closed or invalid directed edge')
        edges[key] = row
        starts[str(row['F_NODE'])].append(key)
    outgoing, incoming, candidates = defaultdict(list), defaultdict(list), []
    flagged = set(review_pairs)
    exceptions = gap_exceptions or {}
    for key in sorted(edges):
        row = edges[key]
        for other in sorted(starts[str(row['T_NODE'])]):
            b = edges[other]
            angle = connection_angle(row['geometry'], b['geometry'], look_m)
            gap = Point(row['geometry'].coords[-1]).distance(Point(b['geometry'].coords[0]))
            reason = 'accepted_geometry_continuity'
            if angle > max_angle:
                reason = 'turn_angle_exceeds_qa'
            elif gap > max_gap:
                reason = ('accepted_with_reviewed_source_gap'
                          if (key, other) in exceptions and gap <= exceptions[(key, other)]
                          else 'endpoint_gap_exceeds_qa')
            elif (key, other) in flagged:
                reason = 'official_turn_record_requires_review'
            candidates.append({'from_link': key, 'to_link': other, 'angle_deg': angle,
                               'endpoint_gap_m': gap, 'status': reason})
            if (key, other) in flagged and reason.startswith('accepted'):
                reason = 'official_turn_record_requires_review'
                candidates[-1]['status'] = reason
            if reason.startswith('accepted'):
                outgoing[key].append(other)
                incoming[other].append(key)
    # A fork remains a fork: never silently take the lowest-angle candidate.
    following = {k: v[0] for k, v in outgoing.items() if len(v) == 1 and len(incoming[v[0]]) == 1}
    preceding = {v: k for k, v in following.items()}
    seen, paths = set(), []
    for key in sorted(edges):
        if key in preceding:
            continue
        path = []
        while key not in seen:
            seen.add(key)
            path.append(key)
            if key not in following:
                break
            key = following[key]
        paths.append(path)
    if seen != set(edges):
        raise ValueError('Directed cycle requires separate review')
    assert sum(map(len, paths)) == len(edges)
    return paths, candidates


def split_path(records, max_length=1000.):
    """연결 틈을 더하지 않고 원래 선형 부분만 분할한다. 거리 원점은 로컬이다."""
    if not records or max_length <= 0:
        raise ValueError('Positive segment size and nonempty path required')
    for a, b in zip(records, records[1:]):
        if str(a['T_NODE']) != str(b['F_NODE']):
            raise ValueError('Path node sequence is disconnected')
    offsets, total = [], 0.
    for row in records:
        g = row['geometry']
        if not isinstance(g, LineString) or not g.is_valid or g.length <= 0:
            raise ValueError('Invalid source geometry')
        offsets.append((total, total + g.length, row))
        total += g.length
    result = []
    for index in range(ceil(total / max_length)):
        m0, m1 = index * max_length, min((index + 1) * max_length, total)
        pieces, lineage = [], []
        for begin, end, row in offsets:
            left, right = max(begin, m0), min(end, m1)
            if right <= left:
                continue
            piece = substring(row['geometry'], left - begin, right - begin)
            if not isinstance(piece, LineString) or piece.length <= 0:
                raise ValueError('Degenerate split output')
            pieces.append(piece)
            lineage.append({'LINK_ID': str(row['LINK_ID']), 'link_m0': left - begin,
                            'link_m1': right - begin, 'length_m': piece.length})
        geometry = pieces[0] if len(pieces) == 1 else MultiLineString(pieces)
        if abs(geometry.length - (m1 - m0)) > 1e-6:
            raise AssertionError('Split length not conserved')
        result.append({'m0': m0, 'm1': m1, 'geometry': geometry, 'lineage': lineage,
                       'piece_count': len(pieces), 'tail': m1 - m0 < max_length - 1e-6})
    if abs(sum(r['geometry'].length for r in result) - total) > 1e-6:
        raise AssertionError('Path length not conserved')
    return result
