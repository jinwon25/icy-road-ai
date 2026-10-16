"""행별 ASOS 탐색과 별도 모델 재추론으로 관측 공백 연구를 검산한다."""
from datetime import datetime, timezone
from pathlib import Path
import math
import sys
import joblib
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_method_blending import read, write, preservation
from src.data_source import sha256_file as sha
from src.method_blending import domain
from src.submission_runtime import FEATURES, WATER, infer
from src.submission_io import read_weather

PRIVATE = ROOT / 'outputs/private'
OUT = PRIVATE / 'asos_gap_fallback_20261016_v1'
SOURCE = PRIVATE / 'releases/20261007/outputs/private'
MODELS = PRIVATE / 'weather_memory_controls_20261013_v1'
CANDIDATE = PRIVATE / 'submission_candidate_20261016_v1'
INPUTS = ['station', 'time', *FEATURES, *[c for c in WATER if c not in FEATURES]]


def distance(lat, lon, other_lat, other_lon):
    a, b = math.radians(lat), math.radians(other_lat)
    dlat, dlon = b-a, math.radians(other_lon-lon)
    x = math.sin(dlat/2)**2 + math.cos(a)*math.cos(b)*math.sin(dlon/2)**2
    return 6371.0088*2*math.asin(min(1.0, math.sqrt(x)))


def main():
    target = OUT / 'independent_verification.json'
    if target.exists():
        raise FileExistsError('Preserve completed weather fallback audit')
    frozen = preservation()
    summary = read(OUT / 'summary.json')
    plan = read(OUT / 'experiment_plan.json')
    for rel, digest in read(OUT / 'input_signatures.json').items():
        assert sha(ROOT / rel) == digest, rel
    for rel, digest in summary['files'].items():
        assert sha(OUT / rel) == digest, rel
    original_plan = {k: v for k, v in plan.items() if k != 'started_at_utc'}
    assert original_plan == read(ROOT / 'config/asos_gap_fallback_experiment.json')
    obs = pd.read_parquet(SOURCE / 'point_sources/asos.parquet', columns=['station', 'source_time', 'air_temp', 'snow_cm'])
    obs.station = obs.station.astype(str)
    for c in ['air_temp', 'snow_cm']:
        obs[c] = obs[c].replace([-999., -99.9, -99.2, -99.7], np.nan)
    available = {s: p.loc[p.air_temp.notna()].sort_values('source_time') for s, p in obs.groupby('station')}
    coords = pd.read_csv(SOURCE / 'point_sources/weather_coordinates.csv', dtype={'station_id': str})
    coords = coords.loc[coords.kind.eq('ASOS') & coords.station_id.isin(available)]
    catalogue = pd.read_csv(SOURCE / 'external/kma_rwis_reference/station_catalog.csv', dtype={'station': str}).set_index('station')
    index = pd.read_csv(CANDIDATE / 'data/point_prediction_index.csv', dtype={'id': str})
    selections = [('masked', pd.read_parquet(OUT / 'masked_weather_selections.parquet')),
                  ('protected', pd.read_parquet(OUT / 'protected_weather_selections.parquet'))]
    checked = 0
    # Deliberately filter a timestamp interval per row, rather than searchsorted.
    for scope, frame in selections:
        for station, part in frame.groupby('station'):
            if scope == 'masked':
                lat, lon = catalogue.loc[station, ['lat', 'lon']]
            else:
                point = index.loc[index.kind.eq('protected') & index.id.eq(station)].iloc[0]
                lat, lon = point.point_lat, point.point_lon
            ranked = sorted((distance(lat, lon, r.latitudes, r.longitudes), r.station_id) for r in coords.itertuples())
            for row in part.itertuples():
                assert row.primary_asos_station == ranked[0][1]
                expected = None
                for km, source_station in ranked:
                    if scope == 'masked' and source_station == ranked[0][1]:
                        continue
                    if km > plan['maximum_distance_km'] or km > ranked[0][0] + plan['maximum_extra_distance_km']:
                        continue
                    source = available[source_station]
                    old = source.loc[source.source_time.lt(row.time) & source.source_time.ge(row.time-pd.Timedelta(minutes=60))]
                    if not old.empty:
                        expected = (source_station, old.iloc[-1], km)
                        break
                if expected is None:
                    assert pd.isna(row.selected_asos_station)
                    assert all(pd.isna(getattr(row, c)) for c in ['source_time', 'air_temp', 'snow_cm', 'age_minutes', 'distance_km'])
                else:
                    source_station, observed, km = expected
                    assert row.selected_asos_station == source_station and row.source_time == observed.source_time
                    np.testing.assert_allclose([row.air_temp, row.snow_cm, row.age_minutes, row.distance_km],
                        [observed.air_temp, observed.snow_cm, (row.time-observed.source_time).total_seconds()/60, km],
                        atol=1e-8, rtol=0, equal_nan=True)
                checked += 1
    groups = read(MODELS / 'groups.json')
    population = set().union(*map(set, groups.values()))
    weather = domain(pd.read_parquet(PRIVATE / 'weather_distance_20261010_v1/development_inputs.parquet',
                                    columns=[*INPUTS, 'road_temp']))
    weather = weather.loc[weather.station.isin(population)]
    samples = weather.loc[weather.time.dt.day.isin(plan['synthetic_mask_days']) &
                          weather.time.dt.strftime('%H:%M').isin(plan['synthetic_mask_target_slots'])].sort_values(['station', 'time']).reset_index(drop=True)
    assert len(samples) == 648
    saved = pd.read_parquet(OUT / 'masked_validation_predictions.parquet')
    selected = selections[0][1]
    assert_frame_equal(samples[['station', 'time', 'road_temp']], saved[['station', 'time', 'road_temp']])
    assert_frame_equal(samples[['station', 'time']], selected[['station', 'time']])
    altered = samples[INPUTS].copy()
    altered[['asos_air_temp', 'asos_age_minutes', 'asos_snow_cm']] = selected[['air_temp', 'age_minutes', 'snow_cm']].to_numpy()
    registry = {(r['candidate'], tuple(r['excluded_groups'])): r for r in read(MODELS / 'fit_receipts.json')}
    table = pd.read_csv(OUT / 'masked_station_metrics.csv', dtype={'station': str}, float_precision='round_trip').set_index('station')
    gate = plan['quality_gate']
    values_checked = 0
    for station, part in samples.groupby('station'):
        group = next(g for g, ids in groups.items() if station in ids)
        models = []
        for name in ['nohistory12_mse300', 'nohistory12_mae300']:
            receipt = registry[(name, (group,))]
            path = MODELS / receipt['model_path']
            assert sha(path) == receipt['model_sha256']
            assert not set(groups[group]) & set(receipt['training_stations'])
            models.append(joblib.load(path))
        original = infer(part[INPUTS], models).estimated_road_temp_c
        proposal = infer(altered.loc[part.index], models).estimated_road_temp_c
        actual = saved.loc[part.index]
        np.testing.assert_allclose(original, actual.original_temperature, atol=0, rtol=0, equal_nan=True)
        np.testing.assert_allclose(proposal, actual.fallback_temperature, atol=0, rtol=0, equal_nan=True)
        present = np.isfinite(part.road_temp) & np.isfinite(original) & np.isfinite(proposal)
        n = int(present.sum())
        coverage = selected.loc[part.index].selected_asos_station.notna().mean()
        baseline = (original[present]-part.road_temp[present]).abs().mean()
        replacement = (proposal[present]-part.road_temp[present]).abs().mean()
        shift = (proposal[present]-original[present]).abs().mean()
        row = table.loc[station]
        np.testing.assert_allclose([n, coverage, baseline, replacement, shift],
            [row.paired_temperature_rows, row.available_fraction, row.original_mae, row.fallback_mae, row.mean_absolute_temperature_change],
            atol=1e-12, rtol=0, equal_nan=True)
        qualified = (n >= gate['minimum_paired_temperature_rows_each_station'] and coverage >= gate['minimum_available_fraction_each_station']
                     and replacement <= baseline*(1+gate['maximum_station_mae_relative_harm'])+1e-12
                     and shift <= gate['maximum_station_mean_temperature_change_celsius'])
        assert qualified == row.quality_passed
        values_checked += 2*len(part)
    protected = pd.read_parquet(OUT / 'protected_gap_reference_inputs.parquet')
    selection = selections[1][1]
    assert_frame_equal(protected[['station', 'time']], selection[['station', 'time']])
    original_parts = []
    for (station, winter), part in protected.assign(winter=np.where(protected.time.dt.month.ge(11), protected.time.dt.year, protected.time.dt.year-1)).groupby(['station', 'winter'], sort=False):
        point = index.loc[index.kind.eq('protected') & index.id.eq(station) & index.winter.eq(winter)].iloc[0]
        original = pd.read_parquet(CANDIDATE / 'data/weather_groups' / (point.prediction_group+'.parquet'), columns=INPUTS)
        original = original.loc[original.time.isin(part.time)].copy()
        original.station = station
        original_parts.append(original)
    original = pd.concat(original_parts, ignore_index=True).set_index(['station', 'time']).loc[pd.MultiIndex.from_frame(protected[['station', 'time']])].reset_index()
    other = [c for c in INPUTS if c not in ['asos_air_temp', 'asos_snow_cm', 'asos_age_minutes']]
    assert_frame_equal(original[other], protected[other])
    have = selection.selected_asos_station.notna()
    assert not (original.asos_air_temp.notna() & original.asos_age_minutes.between(1, 60)).any()
    for dest, source in [('asos_air_temp', 'air_temp'), ('asos_snow_cm', 'snow_cm'), ('asos_age_minutes', 'age_minutes')]:
        expected = original[dest].copy()
        expected.loc[have] = selection.loc[have, source].to_numpy()
        np.testing.assert_allclose(expected, protected[dest], equal_nan=True, rtol=0, atol=0)
    models = [joblib.load(CANDIDATE / 'model' / (n+'.joblib')) for n in ['weather12_mse300', 'weather12_mae300']]
    replay = infer(protected[INPUTS], models)
    persisted = read_weather(OUT / 'protected_gap_reference_predictions.csv')
    # The CSV loader is lossless; these are predictions, not inference weather.
    for c in ['estimated_road_temp_c', 'temperature_component_spread_c', 'predicted_ice']:
        np.testing.assert_allclose(pd.to_numeric(persisted[c], errors='coerce').to_numpy(float),
                                  replay[c].to_numpy(float, na_value=np.nan), atol=0, rtol=0, equal_nan=True)
    assert replay.estimated_road_temp_c.notna().sum() == replay.predicted_ice.notna().sum() == 12
    assert replay.predicted_ice.isna().sum() == 6 and int(table.quality_passed.sum()) == 2
    assert not summary['all_station_quality_gates_passed'] and not summary['execution_candidate_changed']
    assert sha(CANDIDATE.with_suffix('.zip')) == summary['execution_candidate_archive_sha256']
    assert preservation() == frozen
    receipt = dict(status='independent_asos_gap_fallback_audit_passed', audited_at_utc=datetime.now(timezone.utc).isoformat(),
                   summary_sha256=sha(OUT / 'summary.json'), weather_selections_verified=checked,
                   validation_temperature_values_replayed=values_checked, protected_prediction_rows_replayed=len(replay),
                   station_quality_gates_verified=len(table), qualified_stations=2, reference_available_rows=12,
                   reference_still_missing_rows=6, execution_candidate_unchanged=True, assessment_outcomes_read=False,
                   old_frozen_files=frozen[0], reserved_frozen_files=frozen[1])
    write(target, receipt)
    print(receipt, flush=True)


if __name__ == '__main__':
    main()
