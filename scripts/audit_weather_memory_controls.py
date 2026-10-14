"""이력 대조군의 같은 학습조건·20모델·예측·지표·사건 손실을 별도 검산한다."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sys
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.event_retention import compare_event_retention
from scripts.audit_method_blending import report, gate
from scripts.audit_temperature_blind_validation import compare, reference_ice
from scripts.review_weather_memory_events import reconstruct
from scripts.evaluate_method_blending import read, write, preservation

PRIVATE = ROOT / 'outputs/private'
OUT = PRIVATE / 'weather_memory_controls_20261013_v1'
SOURCE = PRIVATE / 'weather_memory_temperature_20261013_v2'
BASELINE = 'equal_distance_mse_mae300'
MODELS = ['nohistory12_mse300', 'nohistory12_mae300']
BLENDS = ['equal_nohistory_pair', 'equal_trio_nohistory']
MEMORY = ['memory12_mse300', 'memory12_mae300', 'equal_memory_pair', 'equal_trio_memory']
FEATURES = ['asos_air_temp', 'aws_air_temp', 'aws_humidity', 'aws_wind_speed', 'aws_rain_15m', 'aws_dewpoint', 'aws_age_minutes', 'asos_age_minutes', 'hour_sin', 'hour_cos', 'season_sin', 'season_cos']


def main():
    target = OUT / 'independent_verification.json'
    if target.exists(): raise FileExistsError('Preserve control audit')
    summary = read(OUT / 'summary.json'); groups = read(OUT / 'groups.json'); plan = read(OUT / 'experiment_plan.json')
    for rel, digest in read(OUT / 'input_signatures.json').items(): assert sha(ROOT / rel) == digest, rel
    for rel, digest in summary['files'].items(): assert sha(OUT / rel) == digest, rel
    source_summary = read(SOURCE / 'summary.json'); source_audit = read(SOURCE / 'independent_verification.json')
    assert source_audit['summary_sha256'] == sha(SOURCE / 'summary.json')
    data = pd.read_parquet(PRIVATE / 'weather_distance_20261010_v1/development_inputs.parquet')
    original = read(SOURCE / 'fit_receipts.json'); receipts = read(OUT / 'fit_receipts.json'); checked, refits = 0, 0
    assert len(receipts) == 20 and len({(tuple(r['excluded_groups']), r['candidate']) for r in receipts}) == 20
    with threadpool_limits(limits=2):
        for r in receipts:
            paired = next(v for v in original if v['excluded_groups'] == r['excluded_groups'] and v['candidate'] == r['paired_memory_candidate'])
            forbidden = set().union(*(set(groups[g]) for g in r['excluded_groups']))
            train = data.loc[np.isfinite(data.road_temp) & np.isfinite(data.asos_air_temp) & ~data.station.isin(forbidden)]
            query = data.loc[data.station.isin(forbidden)]
            assert r['parameters'] == paired['parameters'] and r['training_rows'] == paired['training_rows'] == len(train)
            assert r['training_stations'] == paired['training_stations'] == sorted(train.station.unique())
            assert r['features'] == FEATURES == paired['features'][:12] and len(paired['features']) == 42
            assert sorted(forbidden) == r['forbidden_stations'] == paired['forbidden_stations']
            digest = hashlib.sha256(pd.util.hash_pandas_object(train[['station', 'time', 'road_temp', *FEATURES]], index=True).to_numpy().tobytes()).hexdigest()
            assert digest == r['training_values_sha256']
            path = OUT / r['model_path']; assert sha(path) == r['model_sha256']; model = joblib.load(path)
            assert all(model.get_params()[k] == v for k, v in r['parameters'].items())
            q = pd.read_parquet(path.parent / 'predictions.parquet')
            pd.testing.assert_frame_equal(q[['station', 'time']], query[['station', 'time']].reset_index(drop=True))
            expected = np.where(np.isfinite(query.asos_air_temp), model.predict(query[FEATURES]), np.nan)
            np.testing.assert_allclose(q[r['candidate']], expected, atol=1e-10, rtol=0, equal_nan=True); checked += len(q)
            if r['excluded_groups'] == ['honam_baekyang', 'seohaean_seocheon']:
                refit = HistGradientBoostingRegressor(**r['parameters']).fit(train[FEATURES], train.road_temp)
                np.testing.assert_allclose(refit.predict(query[FEATURES]), model.predict(query[FEATURES]), atol=1e-10, rtol=0); refits += 1
            print('대조군 검산:', '__'.join(r['excluded_groups']), r['candidate'], flush=True)
    decisions = read(OUT / 'decisions.json'); parts = []; blend_values = 0
    for g in groups:
        inner = pd.read_parquet(OUT / g / 'inner_oof.parquet'); outer = pd.read_parquet(OUT / g / 'outer_predictions.parquet')
        for kind, f in [('inner_oof', inner), ('outer_predictions', outer)]:
            orig = pd.read_parquet(SOURCE / g / (kind+'.parquet'), columns=['station', 'time', 'group', 'road_temp', BASELINE, *MEMORY])
            pd.testing.assert_frame_equal(f[orig.columns], orig)
            for h in sorted(set(groups)-{g}) if kind == 'inner_oof' else [g]:
                context = '__'.join(sorted([g, h])) if kind == 'inner_oof' else g
                pred = pd.read_parquet(OUT / 'contexts' / context / 'predictions.parquet').set_index(['station', 'time'])
                subset = f.loc[f.station.isin(groups[h])]
                np.testing.assert_allclose(subset[MODELS], pred.loc[pd.MultiIndex.from_frame(subset[['station', 'time']]), MODELS], atol=0, rtol=0, equal_nan=True)
            np.testing.assert_allclose(f[BLENDS[0]], (f[MODELS[0]]+f[MODELS[1]])/2, atol=0, rtol=0, equal_nan=True)
            np.testing.assert_allclose(f[BLENDS[1]], (f[BASELINE]+f[BLENDS[0]])/2, atol=0, rtol=0, equal_nan=True); blend_values += len(f)*2
        reports = {c: report(inner, c) for c in [BASELINE, *MODELS, *BLENDS]}; compare(reports, decisions[g]['inner_reports'])
        eligible = [c for c in [*MODELS, *BLENDS] if gate(reports[c], reports[BASELINE])]
        chosen = min(eligible, key=lambda c: (reports[c]['station_macro']['mae'], reports[c]['station_macro']['rmse'], c)) if eligible else BASELINE
        assert chosen == decisions[g]['selected_candidate'] and not decisions[g]['outer_labels_used']
        np.testing.assert_allclose(outer.selected_control, outer[chosen], atol=0, rtol=0, equal_nan=True); parts.append(outer)
    combined = pd.read_parquet(OUT / 'outer_predictions.parquet'); classified = pd.read_parquet(OUT / 'ice_predictions.parquet')
    pd.testing.assert_frame_equal(combined, pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True))
    compare({c: report(combined, c) for c in summary['metrics']}, summary['metrics'])
    for c in [BASELINE, *MEMORY]: compare(summary['metrics'][c], source_summary['metrics'][c])
    assert summary['gate_vs_original_trio'] == {c: gate(summary['metrics'][c], summary['metrics'][BASELINE]) for c in [*MODELS, *BLENDS, 'selected_control']}
    assert summary['memory_gate_vs_matched_control'] == {m: gate(summary['metrics'][m], summary['metrics'][c]) for m, c in zip(MEMORY, MODELS+BLENDS)}
    pd.testing.assert_frame_equal(classified[combined.columns], combined)
    source_ice = pd.read_parquet(SOURCE / 'ice_predictions.parquet')
    pd.testing.assert_frame_equal(classified[['station', 'time', 'ice', 'baseline_prediction']], source_ice[['station', 'time', 'ice', 'baseline_prediction']])
    water = data.set_index(['station', 'time']).loc[pd.MultiIndex.from_frame(classified[['station', 'time']]), ['aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']].to_numpy()
    base_events = reconstruct(source_ice, 'ice_'+BASELINE); retention = {}
    for name, r in summary['ice_diagnostic'].items():
        t = classified[name].to_numpy(); fallback = ~np.isfinite(t) | np.isnan(water).all(axis=1)
        p = ((t <= 0) & ((water[:, 0] >= t) | (water[:, 1] > 0) | (water[:, 2] > 0))).astype(int); p[fallback] = classified.baseline_prediction.to_numpy()[fallback]
        np.testing.assert_array_equal(p, classified['ice_'+name]); compare(reference_ice(classified, 'ice_'+name) | {'fallback_rows': int(fallback.sum())}, r)
        expected_events = reconstruct(classified, 'ice_'+name)
        pd.testing.assert_frame_equal(expected_events, pd.read_csv(OUT / f'ice_events_{name}.csv', dtype={'station': str}))
        retention[name] = compare_event_retention(base_events, expected_events)
    freezes = preservation()
    write(target, dict(status='independent_same_parameter_memory_controls_audit_passed', audited_at_utc=datetime.now(timezone.utc).isoformat(),
         summary_sha256=sha(OUT / 'summary.json'), audit_source_sha256=sha(Path(__file__)), model_prediction_values_verified=checked,
         receipts_verified=20, representative_refits=refits, blend_values_verified=blend_values, decisions_verified=4, temperature_reports_verified=10,
         physics_reports_verified=5, event_identity_checks=retention, assessment_outcomes_used=False, model_promoted=False,
         old_frozen_files=freezes[0], reserved_frozen_files=freezes[1]))
    print('검산 완료', {n: r['lost_events'] for n, r in retention.items()})


if __name__ == '__main__': main()
