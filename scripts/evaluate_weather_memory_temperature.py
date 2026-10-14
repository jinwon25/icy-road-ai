"""고정 기상 이력2모델·2균등 결합과 경험적 오차 범위를 공간 제외로 비교한다."""
from datetime import datetime, timezone
import hashlib
from itertools import combinations
from pathlib import Path
import shutil
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.method_blending import domain, temperature_gate, ice_guard
from src.temperature_transfer import regression_report
from src.temperature_uncertainty import interval_report
from src.thermal_ice import fixed_thermal_rule, diagnostic_report
from src.weather_memory_temperature import FEATURES, BASELINE, MODELS, CANDIDATES, weather_history, model_features, calibrate_ranges, apply_ranges, condition_bins, range_gate
from scripts.evaluate_method_blending import read, write, preservation, PRIVATE, training

SOURCE = PRIVATE / 'temperature_pair_blending_20261010_v1'
INPUTS = PRIVATE / 'weather_distance_20261010_v1'
OUT = PRIVATE / 'weather_memory_temperature_20261013_v1'
CONFIG = ROOT / 'config/weather_memory_temperature_experiment.json'


def origin_frame(group, kind, context_predictions, groups):
    path = SOURCE / group / (kind+'.parquet')
    frame = pd.read_parquet(path, columns=['station', 'time', 'group', 'road_temp', 'weather_mse300', BASELINE])
    parts = []
    for other in sorted(set(groups)-{group}) if kind == 'inner_oof' else [group]:
        excluded = tuple(sorted([group, other])) if kind == 'inner_oof' else (group,)
        prediction = context_predictions[excluded]
        parts.append(prediction.loc[prediction.station.isin(groups[other]), ['station', 'time', *MODELS]])
    join = pd.concat(parts, ignore_index=True)
    result = frame.merge(join, on=['station', 'time'], how='left', validate='one_to_one')
    pd.testing.assert_frame_equal(result[frame.columns], frame)
    if not all(np.array_equal(np.isfinite(result[c]), np.isfinite(result[BASELINE])) for c in MODELS):
        raise ValueError('Shared finite prediction denominator required')
    result['equal_memory_pair'] = (result[MODELS[0]]+result[MODELS[1]])/2
    result['equal_trio_memory'] = (result[BASELINE]+result.equal_memory_pair)/2
    return result


def main():
    if OUT.exists(): raise FileExistsError('Preserve completed or interrupted research')
    plan = read(CONFIG)
    if plan['models'] != list(MODELS) or plan['candidates'] != list(CANDIDATES) or plan['primary_baseline'] != BASELINE:
        raise ValueError('Pinned experiment differs')
    freezes = preservation()
    audit = read(SOURCE / 'independent_verification.json')
    if audit['status'] != 'independent_fixed_pairs_audit_passed' or audit['summary_sha256'] != sha(SOURCE / 'summary.json'):
        raise ValueError('Audited baseline required')
    OUT.mkdir(); write(OUT / 'experiment_plan.json', plan | {'started_at_utc': datetime.now(timezone.utc).isoformat(), 'new_independent_assessment': False})
    pinned = [CONFIG, Path(__file__), ROOT / 'src/weather_memory_temperature.py', ROOT / 'src/temperature_uncertainty.py', ROOT / 'src/method_blending.py',
              ROOT / 'src/temperature_transfer.py', ROOT / 'src/thermal_ice.py', ROOT / 'scripts/evaluate_method_blending.py',
              INPUTS / 'development_inputs.parquet', SOURCE / 'groups.json', SOURCE / 'summary.json', SOURCE / 'independent_verification.json']
    for group in read(SOURCE / 'groups.json'):
        pinned.extend(SOURCE / group / (kind+'.parquet') for kind in ['inner_oof', 'outer_predictions'])
    pinned.append(SOURCE / 'ice_predictions.parquet')
    signatures = {str(p.relative_to(ROOT)): sha(p) for p in pinned}
    write(OUT / 'input_signatures.json', signatures)
    shutil.copy2(Path(__file__), OUT / 'analysis_source.py'); shutil.copy2(ROOT / 'src/weather_memory_temperature.py', OUT / 'memory_source.py')
    groups = read(SOURCE / 'groups.json'); write(OUT / 'groups.json', groups)
    data = domain(pd.read_parquet(INPUTS / 'development_inputs.parquet'))
    if set(data.station) != set(plan['allowed_stations']): raise ValueError('Only fixed23 stations permitted')
    history = weather_history(data)
    history.to_parquet(OUT / 'history_inputs.parquet', index=True, compression='zstd')
    data = pd.concat([data, history], axis=1)
    contexts = [(g,) for g in sorted(groups)] + list(combinations(sorted(groups), 2))
    receipts, predictions = [], {}
    with threadpool_limits(limits=2):
        for excluded in contexts:
            forbidden = set().union(*(set(groups[g]) for g in excluded))
            fit = training(data, forbidden); query = data.loc[data.station.isin(forbidden)].copy()
            x = model_features(fit); qx = model_features(query)
            target = fit.road_temp.to_numpy(float)
            result = query[['station', 'time']].copy()
            folder = OUT / 'contexts' / '__'.join(excluded); folder.mkdir(parents=True)
            for name, loss in zip(MODELS, ['squared_error', 'absolute_error']):
                params = plan['hgb_parameters'] | {'loss': loss}; started = time.monotonic()
                model = HistGradientBoostingRegressor(**params).fit(x, target)
                path = folder / (name+'.joblib'); joblib.dump(model, path, compress=3)
                result[name] = np.where(np.isfinite(query.asos_air_temp), model.predict(qx), np.nan)
                receipt = dict(candidate=name, excluded_groups=list(excluded), forbidden_stations=sorted(forbidden),
                               training_stations=sorted(fit.station.unique()), training_rows=len(fit), features=FEATURES, parameters=params,
                               training_values_sha256=hashlib.sha256(pd.util.hash_pandas_object(fit[['station', 'time', 'road_temp', *FEATURES]], index=True).to_numpy().tobytes()).hexdigest(),
                               model_path=path.relative_to(OUT).as_posix(), model_sha256=sha(path), fit_seconds=time.monotonic()-started)
                receipts.append(receipt)
                print('학습:', '__'.join(excluded), name, len(fit), round(receipt['fit_seconds'], 2), flush=True)
            result.to_parquet(folder / 'predictions.parquet', index=False, compression='zstd'); predictions[excluded] = result
    write(OUT / 'fit_receipts.json', receipts)
    parts, decisions, calibrations = [], {}, {}
    for group in groups:
        inner = origin_frame(group, 'inner_oof', predictions, groups); query = origin_frame(group, 'outer_predictions', predictions, groups)
        reports = {c: regression_report(inner, inner[c]) for c in [BASELINE, *CANDIDATES]}
        eligible = [c for c in CANDIDATES if temperature_gate(reports[c], reports[BASELINE])]
        chosen = min(eligible, key=lambda c: (reports[c]['station_macro']['mae'], reports[c]['station_macro']['rmse'], c)) if eligible else BASELINE
        decisions[group] = dict(selected_candidate=chosen, selection_groups=sorted(set(groups)-{group}), inner_reports=reports, outer_labels_used=False)
        query['selected_temperature'] = query[chosen]; query['selected_candidate'] = chosen
        calibrations[group] = {}
        for name in [BASELINE, *CANDIDATES]:
            for conditional in (False, True):
                key = name+('_conditional' if conditional else '_global')
                cal = calibrate_ranges(inner, inner[name], conditional)
                cal.update(calibration_groups=sorted(set(groups)-{group}), outer_labels_used=False)
                calibrations[group][key] = cal
                lo, hi = apply_ranges(query, query[name], cal)
                query[key+'_lower'], query[key+'_upper'] = lo, hi
        folder = OUT / group; folder.mkdir()
        inner.to_parquet(folder / 'inner_oof.parquet', index=False, compression='zstd')
        query.to_parquet(folder / 'outer_predictions.parquet', index=False, compression='zstd'); parts.append(query)
    write(OUT / 'decisions.json', decisions); write(OUT / 'calibrations.json', calibrations)
    combined = pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    metrics = {c: regression_report(combined, combined[c]) for c in ['weather_mse300', BASELINE, *CANDIDATES, 'selected_temperature']}
    ranges, conditions = {}, []
    for name in [BASELINE, *CANDIDATES]:
        for conditional in (False, True):
            key = name+('_conditional' if conditional else '_global')
            ranges[key] = interval_report(combined, combined[name], combined[key+'_lower'], combined[key+'_upper'])
            bins = condition_bins(combined, combined[name])
            valid = np.isfinite(combined.road_temp) & np.isfinite(combined[name])
            for cell in sorted(bins.loc[valid].unique()):
                take = valid & bins.eq(cell)
                inside = combined.road_temp.between(combined[key+'_lower'], combined[key+'_upper'])
                conditions.append(dict(method=key, condition=cell, n=int(take.sum()), coverage=float(inside[take].mean()),
                                       width=float((combined[key+'_upper']-combined[key+'_lower'])[take].mean())))
    pd.DataFrame(conditions).to_csv(OUT / 'range_conditions.csv', index=False)
    labels = pd.read_parquet(SOURCE / 'ice_predictions.parquet', columns=['station', 'time', 'ice', 'baseline_prediction'])
    classified = combined.merge(labels, on=['station', 'time'], validate='one_to_one')
    if len(classified) != len(combined): raise ValueError('Ice denominator differs')
    water = combined[['station', 'time']].merge(data[['station', 'time', 'aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']], on=['station', 'time'], validate='one_to_one')
    ice, stations = {}, {}
    for name in [BASELINE, *CANDIDATES, 'selected_temperature']:
        p, fallback, _ = fixed_thermal_rule(classified[name], water, classified.baseline_prediction, True)
        classified['ice_'+name] = p
        r, st, days, events = diagnostic_report(classified, p)
        ice[name] = r | {'fallback_rows': int(fallback.sum())}; stations[name] = st
        for label, table in [('stations', st), ('days', days), ('events', events)]: table.to_csv(OUT / f'ice_{label}_{name}.csv', index=False)
    ice_checks = {name: ice_guard(ice[name], ice[BASELINE], stations[name], stations[BASELINE]) for name in [*CANDIDATES, 'selected_temperature']}
    combined.to_parquet(OUT / 'outer_predictions.parquet', index=False, compression='zstd')
    classified.to_parquet(OUT / 'ice_predictions.parquet', index=False, compression='zstd')
    assert all(sha(ROOT / rel) == digest for rel, digest in signatures.items())
    assert preservation() == freezes
    assert all(r['pooled']['n'] == 155236 for r in metrics.values())
    summary = dict(status='weather_memory_temperature_development_complete', completed_at_utc=datetime.now(timezone.utc).isoformat(),
                   metrics=metrics, ranges=ranges, choices={g: d['selected_candidate'] for g, d in decisions.items()},
                   temperature_gate_vs_trio={c: temperature_gate(metrics[c], metrics[BASELINE]) for c in [*CANDIDATES, 'selected_temperature']},
                   conditional_range_gate={c: range_gate(ranges[c+'_conditional'], ranges[c+'_global']) for c in [BASELINE, *CANDIDATES]},
                   ice_diagnostic=ice, ice_guard_vs_trio={c: {'eligible': x[0], 'checks': x[1]} for c, x in ice_checks.items()},
                   new_model_fits=len(receipts), learned_weights=0, new_independent_assessment=False, assessment_outcomes_used=False,
                   guaranteed_coverage=False, model_promoted=False, old_frozen_files=freezes[0], reserved_frozen_files=freezes[1],
                   files={p.relative_to(OUT).as_posix(): sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()})
    write(OUT / 'summary.json', summary)
    print('완료:', summary['choices'], summary['temperature_gate_vs_trio'], summary['conditional_range_gate'], flush=True)


if __name__ == '__main__': main()
