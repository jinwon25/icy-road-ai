"""거리 제거의 제외 그룹·학습 행·재추론·선택·온도 및 결빙 결과를 별도로 검산한다."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.audit_temperature_blind_validation import reference_temperature, reference_ice, compare
from scripts.fresh_station_validation import old_freezes, verify_seal

DEFAULT = ROOT / 'outputs/private/weather_distance_20261010_v1'
CANDIDATE = 'weather12_no_distance'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def verify_query_scope(saved, forbidden, external):
    # 추론 지점은 학습 제외 그룹에 있어야 한다. 학습 지점과의 관계를 뒤집지 않는다.
    if not set(saved.station) <= set(forbidden) & set(external):
        raise ValueError('Query station was not excluded from fitting')


def temperatures(frame, column):
    report = reference_temperature(frame, column)
    near = reference_temperature(frame.loc[frame.road_temp.between(-2, 2)], column)
    return {k: report[k] for k in ['pooled', 'stations', 'station_macro']} | {'near_freezing': near['pooled']}


def gate(reports, maximum_harm):
    baseline = reports['direct_weather14']; candidate = reports[CANDIDATE]
    if candidate['near_freezing']['n'] != baseline['near_freezing']['n']:
        raise ValueError('Selection denominator differs')
    for station in baseline['stations']:
        if candidate['stations'][station]['n'] != baseline['stations'][station]['n']:
            raise ValueError('Station selection denominator differs')
    passed = (candidate['station_macro']['mae'] < baseline['station_macro']['mae'] - 1e-12
              and candidate['station_macro']['rmse'] < baseline['station_macro']['rmse'] - 1e-12
              and all(candidate['stations'][s]['mae'] <= m['mae'] * (1 + maximum_harm) + 1e-12
                      for s, m in baseline['stations'].items())
              and candidate['near_freezing']['mae'] <= baseline['near_freezing']['mae'] + 1e-12)
    return CANDIDATE if passed else 'direct_weather14'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, default=DEFAULT)
    out = parser.parse_args().experiment.resolve()
    target = out / 'independent_verification.json'
    if not out.is_relative_to((ROOT / 'outputs/private').resolve()) or target.exists():
        raise ValueError('New private audit required')
    summary = read(out / 'summary.json'); config = read(out / 'experiment_plan.json')
    for rel, digest in summary['files'].items():
        if sha(out / rel) != digest:
            raise ValueError('Experiment evidence changed')
    for rel, digest in read(out / 'input_signatures.json').items():
        if sha(ROOT / rel) != digest:
            raise ValueError('Source signature differs')
    freezes = old_freezes()
    verify_seal(ROOT / 'outputs/private/temperature_blind_20261010_v1')
    verify_seal(ROOT / 'outputs/private/fresh_station_validation_20261009_v2')
    frame = pd.read_parquet(out / 'development_inputs.parquet')
    groups = {g: set(s) for g, s in read(out / 'groups.json').items()}
    external = set().union(*groups.values())
    if len(external) != 9 or len(set(frame.station) - external) != 14 or frame.duplicated(['station', 'time']).any():
        raise ValueError('Development population differs')
    if not (frame.time.ge('2024-11-01') & frame.time.lt('2025-03-01')).all():
        raise ValueError('Unexpected winter outcomes')
    rejected = {'12410', '33411', '23402', '12104', '12206', '12212', '12407', '23206', '23406', '33209', '33415',
                '12406', '23405', '33407', '33416'}
    if set(frame.station) & rejected:
        raise ValueError('Protected or opened assessment outcomes in development')
    receipts = read(out / 'fit_receipts.json')
    baseline_receipts = [r for r in read(ROOT / 'outputs/private/weather_fallback_20261009_v1/fit_receipts.json')
                         if r['candidate'] == 'augmented_hgb']
    baseline_map = {tuple(r['forbidden_stations']): r for r in baseline_receipts}
    candidates = {}; baselines = {}; features = None
    for receipt in receipts:
        key = tuple(receipt['forbidden_stations'])
        if key in candidates or receipt['parameters'] != config['hgb_parameters']:
            raise ValueError('Duplicate fit or changed parameters')
        train = frame.loc[~frame.station.isin(key) & np.isfinite(frame.road_temp) & np.isfinite(frame.asos_air_temp)]
        digest = hashlib.sha256(pd.util.hash_pandas_object(train, index=True).to_numpy().tobytes()).hexdigest()
        if len(train) != receipt['training_rows'] or sorted(train.station.unique()) != receipt['training_stations'] or digest != receipt['training_values_sha256']:
            raise ValueError('Fit population/hash differs')
        path = out / receipt['model_path']
        if sha(path) != receipt['model_sha256']:
            raise ValueError('Candidate model changed')
        model = joblib.load(path)
        base_receipt = baseline_map[key]
        base_path = ROOT / 'outputs/private/weather_fallback_20261009_v1' / base_receipt['model_path']
        if sha(base_path) != base_receipt['model_sha256']:
            raise ValueError('Baseline model changed')
        base = joblib.load(base_path)
        required = [c for c in base_receipt['features'] if c not in ['aws_distance_km', 'asos_distance_km']]
        if len(required) != 12 or required != receipt['features'] or list(model.feature_names_in_) != required:
            raise ValueError('Not a two-feature ablation')
        if any(model.get_params()[k] != v or base.get_params()[k] != v for k, v in config['hgb_parameters'].items()):
            raise ValueError('Model parameters differ')
        candidates[key] = model; baselines[key] = (base, base_receipt['features']); features = required
    decisions = read(out / 'decisions.json'); values_verified = 0

    def replay(forbidden, population, saved):
        nonlocal values_verified
        key = tuple(sorted(forbidden))
        indexed = population.set_index(['station', 'time'])
        aligned = indexed.loc[pd.MultiIndex.from_frame(saved[['station', 'time']])]
        if len(aligned) != len(saved):
            raise ValueError('Replay population differs')
        verify_query_scope(saved, forbidden, external)
        for name, model, columns in [(CANDIDATE, candidates[key], features),
                                     ('direct_weather14', *baselines[key])]:
            pred = model.predict(aligned[columns])
            pred = np.where(aligned.asos_air_temp.notna(), pred, np.nan)
            np.testing.assert_allclose(pred, saved[name], rtol=0, atol=1e-12, equal_nan=True)
            values_verified += len(pred)

    with threadpool_limits(limits=2):
        for group, held in groups.items():
            inner = pd.read_parquet(out / group / 'inner_oof.parquet')
            if set(inner.station) != external - held or inner.duplicated(['station', 'time']).any():
                raise ValueError('Inner OOF held-out population differs')
            for other, checked in groups.items():
                if other != group:
                    replay(held | checked, frame, inner.loc[inner.station.isin(checked)])
            reports = {name: temperatures(inner, name) for name in ['direct_weather14', CANDIDATE]}
            compare(reports, decisions[group]['inner_reports'])
            chosen = gate(reports, config['maximum_station_harm'])
            if chosen != decisions[group]['selected_candidate'] or decisions[group]['outer_labels_used_for_selection'] is not False:
                raise ValueError('Candidate selection differs')
            if set(decisions[group]['excluded_stations']) != held or set(decisions[group]['selection_groups']) != set(groups) - {group}:
                raise ValueError('Selection groups differ')
            outer = pd.read_parquet(out / group / 'outer_predictions.parquet')
            if set(outer.station) != held:
                raise ValueError('Outer population differs')
            replay(held, frame, outer)
            np.testing.assert_allclose(outer.selected_temperature, outer[chosen], rtol=0, atol=1e-12, equal_nan=True)
    combined = pd.read_parquet(out / 'outer_predictions.parquet')
    expected = pd.concat([pd.read_parquet(out / g / 'outer_predictions.parquet') for g in groups], ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(combined, expected)
    compare({name: temperatures(combined, name) for name in summary['metrics']}, summary['metrics'])
    classified = pd.read_parquet(out / 'ice_diagnostic_predictions.parquet')
    labels = pd.read_parquet(ROOT / 'outputs/private/daily_primary_transfer_20261009_v1/predictions.parquet').set_index(['station', 'time'])
    keys = pd.MultiIndex.from_frame(classified[['station', 'time']])
    np.testing.assert_allclose(classified.ice, labels.loc[keys, 'ice'], rtol=0, atol=0, equal_nan=True)
    moisture = frame.set_index(['station', 'time']).loc[keys]
    for name in summary['ice_diagnostic']:
        t = classified[name].to_numpy(); baseline = classified.baseline_prediction.to_numpy()
        water = moisture[['aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']].to_numpy()
        fallback = ~np.isfinite(t) | np.isnan(water).all(axis=1)
        p = ((t <= 0) & ((water[:, 0] >= t) | (water[:, 1] > 0) | (water[:, 2] > 0))).astype(int)
        p[fallback] = baseline[fallback]
        np.testing.assert_array_equal(classified['ice_' + name], p)
        report = reference_ice(classified, 'ice_' + name) | {'fallback_rows': int(fallback.sum())}
        compare(report, summary['ice_diagnostic'][name])
    primary_gate = gate(summary['metrics'], config['maximum_station_harm']) == CANDIDATE
    result = dict(status='independent_distance_ablation_audit_passed', audited_at_utc=datetime.now(timezone.utc).isoformat(),
                  summary_sha256=sha(out / 'summary.json'), audit_source_sha256=sha(Path(__file__)),
                  unique_fits_verified=len(receipts), prediction_values_verified=values_verified,
                  decisions_verified=len(decisions), temperature_variants_verified=3, ice_policies_verified=3,
                  development_overall_gate_passed=primary_gate, candidate_promoted=False,
                  old_frozen_files=freezes[0], reserved_frozen_files=freezes[1])
    with target.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
