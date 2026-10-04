"""Geometry-only subdivision; never bridges gaps or infers travel direction."""
from collections import Counter, defaultdict
from math import ceil

from shapely import line_merge, normalize
from shapely.geometry import LineString, MultiLineString
from shapely.ops import substring


def prepare_chains(lines):
    """Merge exact shared endpoints only; do not node interior crossings."""
    parts = []
    for geometry in lines:
        if geometry is None or geometry.is_empty or not geometry.is_valid:
            raise ValueError('Empty or invalid road geometry')
        if isinstance(geometry, LineString):
            parts.append(geometry)
        elif isinstance(geometry, MultiLineString):
            parts.extend(geometry.geoms)
        else:
            raise ValueError('Road must be linear')
    # Supplying MultiLineString avoids converting grade-separated crossings into junctions.
    merged = line_merge(MultiLineString(parts))
    chains = list(merged.geoms) if isinstance(merged, MultiLineString) else [merged]
    return sorted((normalize(chain) for chain in chains), key=lambda g: (g.bounds, g.wkb_hex))


def split_chain(chain, max_length=1000.):
    if max_length <= 0 or chain.length <= 0:
        raise ValueError('Positive length required')
    result = []
    for index in range(ceil(chain.length / max_length)):
        start, end = index * max_length, min((index + 1) * max_length, chain.length)
        piece = substring(chain, start, end)
        if not isinstance(piece, LineString) or piece.length <= 0:
            raise ValueError('Degenerate output segment')
        result.append((start, end, piece))
    if abs(sum(p[2].length for p in result) - chain.length) > 1e-6:
        raise AssertionError('Segment length not conserved')
    return result


def endpoint_topology(chains):
    adjacency = defaultdict(set)
    degree = Counter()
    for chain in chains:
        a, b = tuple(chain.coords[0]), tuple(chain.coords[-1])
        adjacency[a].add(b)
        adjacency[b].add(a)
        degree[a] += 1
        degree[b] += 1
    seen, components = set(), 0
    for node in adjacency:
        if node in seen:
            continue
        components += 1
        stack = [node]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(adjacency[current] - seen)
    return {'endpoint_components': components, 'endpoint_nodes': len(adjacency),
            'dangling_endpoints': sum(value == 1 for value in degree.values()),
            'branch_endpoints': sum(value > 2 for value in degree.values()),
            'closed_chains': sum(chain.is_ring for chain in chains)}
