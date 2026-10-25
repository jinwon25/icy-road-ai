"""검증된 후보 CSV·공간 도형으로 통신 없는 구간 탐색 HTML을 별도 폴더에 만든다."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha


def records(frame):
    return frame.astype(object).where(frame.notna(), None).to_dict('records')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args(); candidate = a.candidate.resolve(); out = a.output.resolve()
    if out.exists(): raise FileExistsError('Preserve existing dashboard')
    manifest = json.loads((candidate / 'manifest.json').read_text('utf-8'))['files']
    sources = ['exports/segment_estimates.csv', 'exports/prediction_group_daily.csv']
    sources += [f'figures/candidate_conditions_{s}m_2024.gpkg' for s in [500, 1000]]
    for name in sources: assert sha(candidate / name) == manifest[name]['sha256'], name
    segments = pd.read_csv(candidate / sources[0], dtype={'seg_id': str, 'prediction_group': str}, float_precision='round_trip')
    daily = pd.read_csv(candidate / sources[1], dtype={'prediction_group': str}, float_precision='round_trip')
    assert len(segments) == 2532 and len(daily) == 16560
    assert not segments.duplicated(['scale_m', 'winter', 'seg_id']).any()
    assert not daily.duplicated(['prediction_group', 'winter', 'date_kst']).any()
    geoms = []
    for scale in [500, 1000]:
        f = gpd.read_file(candidate / f'figures/candidate_conditions_{scale}m_2024.gpkg').to_crs(5179)
        assert set(f.seg_id) == set(segments.loc[segments.scale_m.eq(scale), 'seg_id'])
        f['scale_m'] = scale; geoms.append(f)
    geo = pd.concat(geoms, ignore_index=True)
    xmin, ymin, xmax, ymax = gpd.GeoSeries(geo.geometry, crs=5179).total_bounds
    factor = min(520 / (xmax - xmin), 455 / (ymax - ymin))
    xpad, ypad = (640 - (xmax - xmin) * factor) / 2, 56
    def xy(x, y): return round(xpad + (x - xmin) * factor, 2), round(ypad + (ymax - y) * factor, 2)
    paths = {}
    for row in geo.itertuples():
        lines = [row.geometry] if row.geometry.geom_type == 'LineString' else list(row.geometry.geoms)
        paths[f'{row.scale_m}|{row.seg_id}'] = ' '.join('M' + ' L'.join(','.join(map(str, xy(x, y))) for x, y, *_ in line.coords) for line in lines)
    labels = []
    for route, part in geo.loc[geo.scale_m.eq(500)].groupby('route_nm'):
        mid = part.geometry.union_all().centroid
        x, y = xy(mid.x, mid.y)
        labels.append(dict(name=route, x=min(x + 15, 490), y=y - 16))
    daily_columns = [c for c in daily if c not in ['prediction_group', 'winter']]
    groups = {f'{group}|{winter}': records(part.sort_values('date_kst')[daily_columns])
              for (group, winter), part in daily.groupby(['prediction_group', 'winter'])}
    for r in segments.itertuples():
        ds = daily.loc[daily.prediction_group.eq(r.prediction_group) & daily.winter.eq(r.winter)]
        assert len(ds) == 120 and int(ds.ice_valid_slots.sum()) == r.ice_valid_slots
        assert int(ds.cold_wet_slots.sum()) == r.cold_wet_slots
        weighted = float((ds.estimated_temp_mean_c * ds.temperature_valid_slots).sum() / ds.temperature_valid_slots.sum())
        assert abs(weighted - r.estimated_temp_mean_c) < 1e-10
    payload = dict(segments=records(segments), daily=groups, paths=paths, labels=labels,
        scale20km=20000 * factor,
        ranges={c: [float(segments[c].min()), float(segments[c].max())] for c in ['cold_wet_fraction', 'estimated_temp_mean_c']})
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('<', '\\u003c')
    decoded = json.loads(encoded)
    pd.testing.assert_frame_equal(pd.DataFrame(decoded['segments'])[segments.columns], segments, check_dtype=False, check_exact=True)
    restored = pd.concat([pd.DataFrame(rows).assign(prediction_group=k.split('|')[0], winter=int(k.split('|')[1])) for k, rows in decoded['daily'].items()], ignore_index=True)
    keys = ['prediction_group', 'winter', 'date_kst']
    pd.testing.assert_frame_equal(restored[daily.columns].sort_values(keys).reset_index(drop=True), daily.sort_values(keys).reset_index(drop=True), check_dtype=False, check_exact=True)
    template = ROOT / 'src/review_dashboard_template.html'
    out.mkdir(parents=True)
    (out / 'index.html').write_text(template.read_text('utf-8').replace('__PAYLOAD__', encoded), 'utf-8')
    for name in sources[:2]: shutil.copy2(candidate / name, out / Path(name).name)
    receipt = dict(status='dashboard_source_and_embedded_numbers_verified',segments=len(segments),geometries=len(paths),
        daily_rows=len(daily),embedded_csv_exact=True,segment_daily_aggregates_verified=True,
        candidate_manifest_sha256=sha(candidate / 'manifest.json'),sources={name:sha(candidate / name) for name in sources},
        template_sha256=sha(template),generator_sha256=sha(Path(__file__)),html_sha256=sha(out / 'index.html'),
        geometry_for_display_only=True,external_requests_required=False,visual_review_pending=True)
    (out / 'source_snapshot.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps(receipt, ensure_ascii=False), flush=True)


if __name__ == '__main__': main()
