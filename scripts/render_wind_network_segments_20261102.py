"""기존·현재 풍속과 추정값 변화의 두 겨울 지도를 같은 척도로 그린다."""
from pathlib import Path
import sys

import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize, TwoSlopeNorm
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_objective_icing import read, write, now
from scripts.project_wind_network_segments_20261102 import OUTPUT, PREVIOUS
from src.data_source import sha256_file as sha


def main():
    source = ROOT/OUTPUT; previous = ROOT/PREVIOUS
    out = ROOT/'outputs/private/wind_network_projection_review_20261102_v2'
    if out.exists(): raise FileExistsError('Preserve completed projection rendering')
    summary = read(source/'summary.json'); audit = read(source/'independent_verification.json')
    assert audit['status'] == 'passed' and audit['summary_sha256'] == sha(source/'summary.json')
    out.mkdir()
    layers = {year: gpd.read_file(source/'weather_segments.gpkg', layer=f'winter_{year}') for year in [2024, 2025]}
    old = {year: gpd.read_file(previous/'weather_segments.gpkg', layer=f'winter_{year}').set_index('seg_id') for year in [2024, 2025]}
    boundary = gpd.read_file(ROOT/'outputs/private/segment_exposure_20261009_v1/boundary.gpkg')
    for year, layer in layers.items():
        layer['previous_wind_mean'] = layer.seg_id.map(old[year].wind_speed_mean)
        layer['wind_estimate_change'] = layer.wind_speed_mean-layer.previous_wind_mean
    wind = np.concatenate([g[['wind_speed_mean', 'previous_wind_mean']].to_numpy().ravel() for g in layers.values()])
    norm = Normalize(vmin=float(np.nanmin(wind)), vmax=float(np.nanmax(wind)))
    maximum = max(float(g.wind_estimate_change.abs().max()) for g in layers.values())
    difference = TwoSlopeNorm(vmin=-maximum, vcenter=0., vmax=maximum)
    plt.rcParams.update({'font.family': 'Malgun Gothic', 'axes.unicode_minus': False, 'font.size': 10})
    fig, axes = plt.subplots(2, 3, figsize=(12, 9.4))
    fig.subplots_adjust(left=.055, right=.985, bottom=.13, top=.87, hspace=.08, wspace=.02)
    extent = layers[2024].total_bounds; pad = 4000
    columns = [('previous_wind_mean', '이전 풍속 추정', 'viridis', norm),
               ('wind_speed_mean', '현재 관측망 풍속 추정', 'viridis', norm),
               ('wind_estimate_change', '추정값 변화 (현재 - 이전)', 'RdBu_r', difference)]
    for row, (year, layer) in enumerate(layers.items()):
        for col, (field, title, cmap, scale) in enumerate(columns):
            ax = axes[row, col]
            boundary.plot(ax=ax, color='#f1f3f4', edgecolor='#c5cdd2', linewidth=.4)
            layer.plot(ax=ax, column=field, cmap=cmap, norm=scale, linewidth=2.6, missing_kwds={'color': '#999999'})
            unknown = layer.loc[layer.new_asos_source_domain]
            points = unknown.geometry.interpolate(.5, normalized=True)
            ax.scatter(points.x, points.y, c='#1d2833', s=2.5, alpha=.85, zorder=4)
            ax.set(xlim=(extent[0]-pad, extent[2]+pad), ylim=(extent[1]-pad, extent[3]+pad)); ax.set_axis_off()
            if row == 0: ax.set_title(title, fontsize=13, pad=10)
            if col == 0: ax.text(-.015, .5, f'{year}.11–{year+1}.02', rotation=90,
                transform=ax.transAxes, va='center', ha='right', fontsize=11)
            ax.annotate('N', xy=(.94, .94), xytext=(.94, .82), xycoords='axes fraction', ha='center',
                arrowprops={'arrowstyle': '-|>', 'color': '#334b5a'}, fontsize=8, color='#334b5a')
            x = extent[2]-17000; y = extent[1]-1800
            ax.plot([x, x+10000], [y, y], color='#334b5a', lw=1.3)
            ax.text(x+5000, y+1800, '10 km', ha='center', fontsize=7, color='#334b5a')
        for col, (_, _, cmap, scale) in enumerate(columns):
            if row == 1:
                bar = fig.colorbar(ScalarMappable(norm=scale, cmap=cmap), ax=axes[:, col],
                    orientation='horizontal', fraction=.025, pad=.025, shrink=.84)
                bar.ax.tick_params(labelsize=9); bar.set_label('m/s', fontsize=9)
    fig.suptitle('채택된 관측망 풍속 모형의 843구간 적용', fontsize=18, y=.98)
    fig.text(.055, .925, '같은 기온·습도·노면온도·결빙을 보존하고 풍속만 갱신 · 두 겨울 공통 색 척도', fontsize=11, color='#4d6779')
    fig.text(.055, .060, '변화 지도는 예측값의 차이이며 실측 오차 개선 지도가 아닙니다. 검은 점: 학습에 없던 ASOS 172 출처 구간.', fontsize=10, color='#4d6779')
    fig.text(.055, .032, '방향별 500m는 결과 보고 단위입니다. 구간별 독립 정확도·결빙확률·위험등급을 입증한 결과가 아닙니다.', fontsize=10, color='#4d6779')
    image = ROOT/'docs/images/wind_network_projection_20261102.png'
    if image.exists(): raise FileExistsError('Preserve existing map')
    fig.savefig(image, dpi=180); plt.close(fig)
    rows = []
    for year, layer in layers.items():
        for route, part in layer.groupby('route_nm'):
            weight = part.len_m.to_numpy(float)
            average = lambda column: float(np.average(part[column], weights=weight))
            rows.append(dict(winter=year, route=route, segments=len(part), directional_length_m=float(weight.sum()),
                previous_wind_mean=average('previous_wind_mean'), wind_speed_mean=average('wind_speed_mean'),
                wind_estimate_change=average('wind_estimate_change'),
                wind_network_outside_fraction=average('wind_network_outside_fraction'),
                wind_network_mean_station_count=average('wind_network_mean_station_count'),
                new_asos_source_segments=int(part.new_asos_source_domain.sum())))
    pd.DataFrame(rows).to_csv(out/'route_wind_comparison.csv', index=False, encoding='utf-8-sig')
    write(out/'receipt.json', dict(status='rendered_pending_visual_review', at_utc=now(),
        summary_sha256=sha(source/'summary.json'), audit_sha256=sha(source/'independent_verification.json'),
        figure_sha256=sha(image), route_rows=len(rows), source_sha256=sha(Path(__file__)),
        new_independent_assessment=False, files={p.name: sha(p) for p in out.iterdir() if p.is_file()}))
    print('WIND MAP RENDERED', len(rows), 'route rows', flush=True)


if __name__ == '__main__':
    main()
