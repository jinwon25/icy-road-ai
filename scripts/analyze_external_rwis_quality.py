"""검증한 첫 겨울 관측 스냅샷의 지점 편중·결측·상태/온도를 시각화한다."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_external_augmentation import json_write
from src.data_source import sha256_file
from src.external_quality import quality_tables
from src.external_temperature import join_training_temperatures
from src.frozen_assessment import verify_freeze


def plot_quality(external, competition, station_table, daily, plan, manifest, path, acquisition_complete=False):
    plt.rcParams['font.family'] = 'Malgun Gothic'
    plt.rcParams['axes.unicode_minus'] = False
    stations = [station for ids in plan['station_groups'].values() for station in ids]
    dates = pd.date_range(plan['development_start_kst'], plan['development_end_kst'], freq='D')
    index = pd.MultiIndex.from_product([stations, dates], names=['station', 'date_kst'])
    all_days = daily.set_index(['station', 'date_kst']).reindex(index)
    requested = pd.DataFrame([{'station': r['station'], 'date_kst': pd.Timestamp(r['start_kst']).normalize()}
                              for r in manifest['records'].values()]).value_counts().reindex(index, fill_value=0)
    coverage = (all_days.valid_state_rows.fillna(0)/144).to_numpy().reshape(len(stations), len(dates)).astype(float)
    coverage[requested.to_numpy().reshape(coverage.shape) == 0] = np.nan
    ice = all_days.ice_rows.fillna(0).to_numpy().reshape(coverage.shape).astype(float)
    ice[requested.to_numpy().reshape(coverage.shape) == 0] = np.nan
    fig, axes = plt.subplots(3, 1, figsize=(13, 11), gridspec_kw={'height_ratios': [1, 1, 1.1]}, constrained_layout=True)
    for ax, values, title, cmap_name, vmax in [
        (axes[0], coverage, '지점별 일일 유효 상태 커버리지 · 회색은 아직 요청하지 않은 날짜', 'Blues', 1),
        (axes[1], ice, '일일 관측 Ice 슬롯 수 · 04만 양성, 온도 조건으로 정답을 삭제하지 않음', 'Oranges', 144)]:
        cmap = plt.get_cmap(cmap_name).copy(); cmap.set_bad('#d9dde2')
        im = ax.imshow(values, aspect='auto', vmin=0, vmax=vmax, cmap=cmap, interpolation='nearest')
        ax.set_yticks(range(len(stations)), stations)
        ticks = [i for i, date in enumerate(dates) if date.day in (1, 15)]
        ax.set_xticks(ticks, [dates[i].strftime('%m/%d') for i in ticks])
        ax.set_title(title, loc='left', fontsize=12)
        fig.colorbar(im, ax=ax, fraction=.02, pad=.02)
    bins = np.arange(-12, 10.5, .5)
    matched = competition.loc[competition.time.isin(external.time.unique())]
    for frame, label, color in [(competition, '대회 개발14지점 · 첫 겨울 전체', '#3576a8'),
                               (matched, '대회 개발14지점 · 추가자료와 동일 시각집합', '#4c9273'),
                               (external, '추가9지점 · 수집된 첫 겨울', '#da7a27')]:
        values = frame.loc[frame.ice.eq(1), 'road_temp'].dropna()
        if len(values):
            weights = np.full(len(values), 1./len(values))
            axes[2].hist(values, bins=bins, weights=weights, histtype='step', linewidth=2, label=f'{label} (온도 유효 Ice {len(values):,}건)', color=color)
    axes[2].axvline(0, color='#5b6470', linestyle='--', linewidth=1)
    axes[2].set(xlabel='Ice 관측 시 노면온도 (°C)', ylabel='전체 온도 유효 Ice 중 구간 비율',
                title='센서·지역·관측기간 차이에 따른 상태/온도 분포 · 실제 결빙 확률이나 센서 오류 확정이 아님')
    axes[2].legend(loc='upper right'); axes[2].grid(alpha=.15)
    partition = '전체 첫 겨울 수집 감사 완료' if acquisition_complete else '부분 수집 감사 스냅샷'
    fig.suptitle(f'첫 겨울 개발 관측 품질 · 추가 {len(external):,}행 / Ice {int(external.ice.eq(1).sum()):,}행\n{partition} · 다음 겨울·보호 지점 정답은 사용하지 않음', fontsize=14)
    fig.savefig(path, dpi=170); plt.close(fig)


def main():
    private = ROOT / 'outputs/private'; source = private / 'external/kma_rwis_development_v1'
    audit_path = source / 'summary.json'; audit = json.loads(audit_path.read_text(encoding='utf-8'))
    observation_path = source / 'observations_available.parquet'
    assert sha256_file(observation_path) == audit['observations_sha256']
    plan_path = ROOT / 'config/kma_external_validation_plan.json'
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    assert sha256_file(plan_path) == audit['plan_sha256'] and not audit['reserved_validation_opened']
    manifest_path = source / audit['download_manifest_snapshot']
    assert sha256_file(manifest_path) == audit['download_manifest_snapshot_sha256']
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    external = pd.read_parquet(observation_path)
    comp_path = private / 'physical_features/features.parquet'; thermal_path = private / 'point_sources/rwis.parquet'
    comp = pd.read_parquet(comp_path, columns=['station', 'time', 'ice', 'state_raw'])
    comp = comp.loc[comp.time.ge(plan['development_start_kst']) & comp.time.lt(pd.Timestamp(plan['development_end_kst']) + pd.Timedelta(days=1))]
    thermal = pd.read_parquet(thermal_path, columns=['station', 'time', 'road_temp'])
    assert len(set(comp.station)) == 14 and not set(comp.station) & set(external.station)
    comp = join_training_temperatures(comp, thermal, set(comp.station))
    matched = comp.loc[comp.time.isin(external.time.unique())]
    external_station, daily, runs = quality_tables(external, plan)
    comp_station, _, _ = quality_tables(comp, plan)
    signature = {'observations': sha256_file(observation_path), 'competition_features': sha256_file(comp_path),
                 'thermal': sha256_file(thermal_path), 'runner': sha256_file(Path(__file__)),
                 'diagnostics': sha256_file(ROOT / 'src/external_quality.py'), 'plan': sha256_file(plan_path)}
    digest = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()[:16]
    out = private / 'external_quality' / f'snapshot_{digest}'
    if out.exists():
        raise FileExistsError('Quality evidence exists; preserve snapshot')
    out.mkdir(parents=True)
    shutil.copy2(observation_path, out / 'input_external_observations.parquet')
    shutil.copy2(audit_path, out / 'input_audit.json'); shutil.copy2(plan_path, out / 'input_plan.json')
    shutil.copy2(manifest_path, out / 'input_download_manifest.json')
    shutil.copy2(Path(__file__), out / 'source_runner.py')
    shutil.copy2(ROOT / 'src/external_quality.py', out / 'source_diagnostics.py')
    comp.to_parquet(out / 'input_competition_first_winter.parquet', index=False, compression='zstd')
    matched.to_parquet(out / 'input_competition_matching_external_times.parquet', index=False, compression='zstd')
    external_station.to_csv(out / 'external_station_quality.csv', index=False, encoding='utf-8-sig')
    comp_station.to_csv(out / 'competition_station_quality.csv', index=False, encoding='utf-8-sig')
    daily.to_csv(out / 'external_daily_quality.csv', index=False, encoding='utf-8-sig')
    runs.to_csv(out / 'external_ice_runs.csv', index=False, encoding='utf-8-sig')
    acquisition_complete = audit['status'] == 'development_download_complete'
    plot_quality(external, comp, external_station, daily, plan, manifest, out / 'quality_overview.png', acquisition_complete)
    total_ice = int(external.ice.eq(1).sum()); most_ice = int(external_station.ice_rows.max())
    summary = {'status': 'first_winter_quality_diagnostics_not_model_evaluation', 'audited_windows': audit['downloaded_windows_audited'],
               'external_rows': len(external), 'external_ice_rows': total_ice,
               'external_ice_stations': int(external_station.ice_rows.gt(0).sum()),
               'largest_station_ice_share': most_ice/total_ice if total_ice else None,
               'external_ice_temperature_above_2c_rows': int(external_station.ice_temperature_above_2c_rows.sum()),
               'competition_first_winter_rows': len(comp), 'competition_first_winter_ice_rows': int(comp.ice.eq(1).sum()),
               'competition_ice_temperature_above_2c_rows': int(comp_station.ice_temperature_above_2c_rows.sum()),
               'competition_matching_external_times': {'rows': len(matched), 'ice_rows': int(matched.ice.eq(1).sum()),
                   'ice_temperature_above_2c_rows': int((matched.ice.eq(1) & matched.road_temp.gt(2)).sum()),
                   'scope': 'Same available clock timestamps, different station populations. Sensor or location effects are not isolated.'},
               'state_labels_modified_or_filtered_by_temperature': False, 'reserved_outcomes_used': False,
               'model_training_started_by_this_diagnostic': False,
               'collection_partition': 'complete_first_winter' if acquisition_complete else 'partial_audited_first_winter',
               'expected_windows_full_winter': audit['expected_windows_full_winter'],
               'signature': signature, 'frozen_files_unchanged': len(verify_freeze(ROOT)['files']),
               'scope': 'Sample concentration and sensor/state/temperature diagnostics only. Runs are consecutive observed slots, not continuous icing duration. Periods and station populations differ.'}
    summary['files'] = {p.name: sha256_file(p) for p in out.iterdir() if p.is_file()}
    json_write(out / 'summary.json', summary)
    json_write(out.parent / 'latest.json', {'snapshot': out.relative_to(ROOT).as_posix(),
                                         'summary_sha256': sha256_file(out / 'summary.json'), **summary})
    print(json.dumps({k: summary[k] for k in ['status', 'external_rows', 'external_ice_rows', 'largest_station_ice_share',
                                             'external_ice_temperature_above_2c_rows', 'state_labels_modified_or_filtered_by_temperature']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
