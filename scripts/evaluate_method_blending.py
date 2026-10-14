"""9종 온도 모델의 세 단계 공간 블렌딩과 고정 물리 판정을 비교한다."""
import argparse
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
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
from src.method_blending import COMPONENTS, BLENDS, domain, matrix, fit_weights, convex_predict, choose_temperature, temperature_gate, validate_meta_origin
from src.temperature_transfer import WEATHER_FEATURES, THERMAL_FEATURES, MODEL_OVERRIDES, regression_report
from src.weather_distance_ablation import DISTANCE_FREE_FEATURES
from src.external_temperature import fit_weather_temperature
from src.thermal_ice import fixed_thermal_rule, diagnostic_report
from scripts.fresh_station_validation import old_freezes, verify_seal

PRIVATE = ROOT / 'outputs/private'
CONFIG = ROOT / 'config/method_blending_experiment.json'
DEFAULT = PRIVATE / 'method_blending_20261010_v1'
SOURCES = {'temperature_transfer_20261009_v1': ['residual_weather14', 'direct_thermal24', 'residual_thermal24'],
           'temperature_loss_20261010_v1': ['weather_mae100', 'weather_mse300', 'weather_mae300'],
           'weather_distance_20261010_v1': ['weather12_no_distance'],
           'weather_fallback_20261009_v1': ['direct_weather14', 'augmented_ridge']}


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def write(p, v):
    with Path(p).open('x', encoding='utf-8') as f:
        json.dump(v, f, ensure_ascii=False, indent=2, allow_nan=False); f.write('\n')


def preservation():
    result = old_freezes()
    for name in ['fresh_station_validation_20261009_v2', 'temperature_blind_20261010_v1', 'temperature_mean_blind_20261010_v1']:
        verify_seal(PRIVATE / name)
    return result


def spec(candidate):
    names = DISTANCE_FREE_FEATURES if candidate == 'weather12_no_distance' else THERMAL_FEATURES if 'thermal24' in candidate else WEATHER_FEATURES
    return list(names), candidate.startswith('residual_')


def predict(model, frame, candidate):
    names, residual = spec(candidate)
    p = model.predict(frame[names])
    if residual:
        p = p + frame.asos_air_temp.to_numpy()
    return np.where(np.isfinite(frame.asos_air_temp), p, np.nan)


def training(data, forbidden):
    return data.loc[np.isfinite(data.road_temp) & np.isfinite(data.asos_air_temp) & ~data.station.isin(forbidden)].copy()


def old_model_registry(data, signatures):
    registry = {}
    for name, components in SOURCES.items():
        folder = PRIVATE / name
        summary = read(folder / 'summary.json'); audit = read(folder / 'independent_verification.json')
        if audit['status'] not in ['passed', 'independent_temperature_audit_passed', 'independent_distance_ablation_audit_passed']:
            raise ValueError('Audited source required')
        if audit.get('summary_sha256') and audit['summary_sha256'] != sha(folder / 'summary.json'):
            raise ValueError('Source audit signature differs')
        for rel in ['summary.json', 'independent_verification.json', 'fit_receipts.json']:
            signatures[str((folder / rel).relative_to(ROOT))] = sha(folder / rel)
        for r in read(folder / 'fit_receipts.json'):
            c = 'direct_weather14' if r['candidate'] == 'augmented_hgb' else r['candidate']
            if c not in components:
                continue
            path = folder / r['model_path']; excluded = tuple(sorted(r['forbidden_stations']))
            if sha(path) != r['model_sha256'] or r['features'] != spec(c)[0]:
                raise ValueError('Source model signature/features differ')
            train = training(data, excluded)
            if len(train) != r['training_rows'] or sorted(train.station.unique()) != r['training_stations']:
                raise ValueError('Source training population differs')
            key = (c, excluded)
            if key in registry and registry[key]['model_sha256'] != r['model_sha256']:
                raise ValueError('Duplicated source model changed')
            registry.setdefault(key, {'candidate': c, 'forbidden_stations': list(excluded), 'training_stations': r['training_stations'],
                                     'training_rows': r['training_rows'], 'model_path': str(path.relative_to(ROOT)), 'model_sha256': sha(path)})
            signatures[str(path.relative_to(ROOT))] = sha(path)
    if len(registry) != 90:
        raise ValueError('Exactly nine components times ten unique spatial contexts required')
    return registry


def load_library(group, kind, signatures):
    keys = ['station', 'time']; reference = None
    for name, columns in SOURCES.items():
        path = PRIVATE / name / group / (kind + '.parquet')
        signatures[str(path.relative_to(ROOT))] = sha(path)
        summary = read(PRIVATE / name / 'summary.json')
        rel = path.relative_to(PRIVATE / name).as_posix()
        if sha(path) != summary['files'][rel]:
            raise ValueError('Stored component prediction changed')
        frame = pd.read_parquet(path)
        if name == 'weather_fallback_20261009_v1':
            if kind == 'inner_oof':
                ridge = frame.loc[frame.candidate.eq('augmented_ridge'), keys+['road_temp', 'prediction']].rename(columns={'prediction': 'augmented_ridge'})
                hgb = frame.loc[frame.candidate.eq('augmented_hgb'), keys+['prediction']].rename(columns={'prediction': 'direct_weather14'})
                frame = ridge.merge(hgb, on=keys, validate='one_to_one')
            else:
                frame = frame.rename(columns={'augmented_hgb': 'direct_weather14'})
        frame = domain(frame).sort_values(keys).reset_index(drop=True)
        if reference is None:
            reference = frame[keys+['road_temp']].copy()
        else:
            pd.testing.assert_frame_equal(reference[keys+['road_temp']], frame[keys+['road_temp']])
        for c in columns:
            reference[c] = frame[c].to_numpy()
    matrix(reference)
    return reference


def fixed_weights(candidate):
    w = np.ones(len(COMPONENTS))/len(COMPONENTS)
    if candidate == 'equal_weather_trio':
        w[:] = 0
        for c in ['direct_weather14', 'weather12_no_distance', 'weather_mse300']:
            w[COMPONENTS.index(c)] = 1/3
    return w


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, default=DEFAULT)
    out = parser.parse_args().output.resolve()
    if out.exists() or not out.is_relative_to(PRIVATE.resolve()):
        raise ValueError('New private experiment directory required')
    plan = read(CONFIG)
    if plan['temperature_components'] != list(COMPONENTS) or plan['temperature_blends'] != list(BLENDS) or plan['shrink_penalty'] != .1:
        raise ValueError('Pinned experiment differs')
    freezes = preservation(); out.mkdir()
    write(out / 'experiment_plan.json', plan | {'started_at_utc': datetime.now(timezone.utc).isoformat(), 'new_independent_assessment': False})
    for path in [Path(__file__), ROOT / 'src/method_blending.py']:
        shutil.copy2(path, out / path.name)
    source = PRIVATE / 'weather_distance_20261010_v1'
    data = domain(pd.read_parquet(source / 'development_inputs.parquet'))
    groups = {g: set(v) for g, v in read(source / 'groups.json').items()}
    if set(data.station) != set(plan['allowed_stations']) or len(groups) != 4:
        raise ValueError('Only fixed 23 stations and four groups permitted')
    signatures = {str(p.relative_to(ROOT)): sha(p) for p in [CONFIG, Path(__file__), ROOT / 'src/method_blending.py',
                  ROOT / 'src/temperature_transfer.py', ROOT / 'src/external_temperature.py', ROOT / 'src/thermal_ice.py',
                  source / 'development_inputs.parquet', source / 'groups.json']}
    registry = old_model_registry(data, signatures)
    write(out / 'reused_model_receipts.json', list(registry.values())); write(out / 'groups.json', {g: sorted(v) for g, v in groups.items()})
    inner_libraries, outer_libraries = {}, {}
    for g in groups:
        inner_libraries[g] = load_library(g, 'inner_oof', signatures)
        outer_libraries[g] = load_library(g, 'outer_predictions', signatures)
    # 이후 새 결과를 얻기 전에 원본과 설정을 고정한다.
    label_path = PRIVATE / 'daily_primary_transfer_20261009_v1/predictions.parquet'
    signatures[str(label_path.relative_to(ROOT))] = sha(label_path)
    write(out / 'input_signatures.json', signatures)
    receipts, triples, meta_receipts, decisions, parts = [], {}, [], {}, []
    with threadpool_limits(limits=plan['max_compute_threads']):
        for excluded_groups in combinations(sorted(groups), 3):
            forbidden = set().union(*(groups[g] for g in excluded_groups))
            train = training(data, forbidden); target = data.loc[data.station.isin(forbidden)]
            predictions = target[['station', 'time', 'road_temp']].copy(); predictions['group'] = target.station.map({s: g for g in groups for s in groups[g]})
            folder = out / 'triple_contexts' / '__'.join(excluded_groups); folder.mkdir(parents=True)
            for candidate in COMPONENTS:
                names, residual = spec(candidate); params = plan['hgb_parameters'] | MODEL_OVERRIDES.get(candidate, {})
                started = time.monotonic()
                if candidate == 'augmented_ridge':
                    model, fitted = fit_weather_temperature(train, names, 100.)
                    assert len(fitted) == len(train)
                else:
                    y = train.road_temp.to_numpy() - (train.asos_air_temp.to_numpy() if residual else 0)
                    model = HistGradientBoostingRegressor(**params).fit(train[names], y)
                path = folder / (candidate + '.joblib'); joblib.dump(model, path, compress=3)
                record = dict(candidate=candidate, excluded_groups=list(excluded_groups), forbidden_stations=sorted(forbidden),
                              training_stations=sorted(train.station.unique()), training_rows=len(train), features=names,
                              training_values_sha256=hashlib.sha256(pd.util.hash_pandas_object(train, index=True).to_numpy().tobytes()).hexdigest(),
                              parameters=params if candidate != 'augmented_ridge' else {'alpha': 100., 'preprocessing': 'median indicators + StandardScaler'},
                              residual_anchor='asos_air_temp' if residual else None, model_path=path.relative_to(out).as_posix(),
                              model_sha256=sha(path), fit_seconds=time.monotonic()-started)
                receipts.append(record); predictions[candidate] = predict(model, target, candidate)
                print('3그룹 제외 학습:', '__'.join(excluded_groups), candidate, round(record['fit_seconds'], 2), flush=True)
            matrix(predictions); predictions.to_parquet(folder / 'predictions.parquet', index=False, compression='zstd')
            triples[tuple(excluded_groups)] = predictions
        for outer, held in groups.items():
            folder = out / outer; folder.mkdir()
            inner = inner_libraries[outer].copy(); inner['group'] = inner.station.map({s: g for g in groups for s in groups[g]})
            for c in BLENDS:
                inner[c] = convex_predict(matrix(inner), fixed_weights(c)) if c.startswith('equal_') else np.nan
            for check in sorted(set(groups)-{outer}):
                meta_parts = []
                for target in sorted(set(groups)-{outer, check}):
                    excluded = tuple(sorted([outer, check, target]))
                    validate_meta_origin([target], excluded, outer, check)
                    meta_parts.append(triples[excluded].loc[triples[excluded].group.eq(target)])
                meta = pd.concat(meta_parts, ignore_index=True)
                for c, penalty in [('simplex_mse', 0.), ('simplex_shrink', plan['shrink_penalty'])]:
                    w, detail = fit_weights(meta, penalty)
                    rows = inner.group.eq(check); inner.loc[rows, c] = convex_predict(matrix(inner.loc[rows]), w)
                    meta_receipts.append(dict(stage='inner', outer_group=outer, validation_group=check, candidate=c,
                                              meta_groups=sorted(set(groups)-{outer, check}), meta_training_rows=len(meta), **detail))
            reports = {c: regression_report(inner, inner[c]) for c in ['direct_weather14', 'weather_mse300', *BLENDS]}
            selected = choose_temperature(reports, plan['maximum_station_harm'])
            decision = dict(outer_group=outer, selection_groups=sorted(set(groups)-{outer}), selected_candidate=selected,
                            excluded_stations=sorted(held), inner_reports=reports, outer_labels_used_for_selection=False)
            write(folder / 'decision.json', decision); decisions[outer] = decision
            inner.to_parquet(folder / 'inner_oof.parquet', index=False, compression='zstd')
            result = outer_libraries[outer].copy(); result['group'] = outer
            for c in BLENDS:
                if c.startswith('equal_'):
                    w = fixed_weights(c)
                else:
                    for target in set(groups)-{outer}:
                        validate_meta_origin([target], [outer, target], outer)
                    w, detail = fit_weights(inner, 0. if c == 'simplex_mse' else plan['shrink_penalty'])
                    meta_receipts.append(dict(stage='outer', outer_group=outer, validation_group=None, candidate=c,
                                              meta_groups=sorted(set(groups)-{outer}), meta_training_rows=len(inner), **detail))
                result[c] = convex_predict(matrix(result), w)
            result['selected_candidate'] = selected; result['selected_temperature'] = result[selected]
            result.to_parquet(folder / 'outer_predictions.parquet', index=False, compression='zstd'); parts.append(result)
            print('외부 그룹 선택:', outer, selected, flush=True)
    combined = pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    metrics = {c: regression_report(combined, combined[c]) for c in [*COMPONENTS, *BLENDS, 'selected_temperature']}
    if {r['pooled']['n'] for r in metrics.values()} != {155236}:
        raise ValueError('Shared development temperature denominator changed')
    combined.to_parquet(out / 'outer_predictions.parquet', index=False, compression='zstd')
    valid = np.isfinite(combined.road_temp) & np.isfinite(combined.direct_weather14)
    errors = matrix(combined.loc[valid])-combined.loc[valid, 'road_temp'].to_numpy()[:, None]
    pd.DataFrame(np.corrcoef(errors, rowvar=False), index=COMPONENTS, columns=COMPONENTS).to_csv(out / 'error_correlations.csv')
    labels = domain(pd.read_parquet(label_path))
    classified = combined.merge(labels[['station', 'time', 'ice', 'baseline_prediction']], on=['station', 'time'], validate='one_to_one')
    if len(classified) != len(combined) or not classified[['station', 'time']].equals(combined[['station', 'time']]):
        raise ValueError('Classification row alignment changed')
    water = combined[['station', 'time']].merge(data[['station', 'time', 'aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']], on=['station', 'time'], validate='one_to_one')
    ice = {}
    for c in ['direct_weather14', 'weather_mse300', *BLENDS, 'selected_temperature']:
        p, fallback, _ = fixed_thermal_rule(classified[c].to_numpy(), water, classified.baseline_prediction.to_numpy(), True)
        classified['ice_'+c] = p
        report, stations, days, events = diagnostic_report(classified, p)
        ice[c] = report | {'fallback_rows': int(fallback.sum())}
        stations.to_csv(out / ('ice_stations_'+c+'.csv'), index=False)
        days.to_csv(out / ('ice_days_'+c+'.csv'), index=False)
        events.to_csv(out / ('ice_events_'+c+'.csv'), index=False)
    classified.to_parquet(out / 'ice_predictions.parquet', index=False, compression='zstd')
    pd.DataFrame([{'variant': c, 'station': s, **r} for c, m in metrics.items() for s, r in m['stations'].items()]).to_csv(out / 'temperature_stations.csv', index=False)
    write(out / 'fit_receipts.json', receipts); write(out / 'meta_fit_receipts.json', meta_receipts); write(out / 'decisions.json', decisions)
    for rel, digest in signatures.items():
        if sha(ROOT / rel) != digest:
            raise ValueError('Original evidence changed')
    if len(receipts) != 36 or len(meta_receipts) != 32 or preservation() != freezes:
        raise ValueError('Fit counts or previous assessment seals changed')
    summary = dict(status='three_level_temperature_blending_development_complete', completed_at_utc=datetime.now(timezone.utc).isoformat(),
                   input_rows=len(data), outer_rows=len(combined), unique_new_base_fits=36, reused_unique_base_models=90, meta_fits=32,
                   metrics=metrics, ice_diagnostic=ice, choices={g: d['selected_candidate'] for g, d in decisions.items()},
                   development_gate_vs_weather14={c: temperature_gate(metrics[c], metrics['direct_weather14']) for c in [*BLENDS, 'selected_temperature']},
                   incremental_gate_vs_mse300={c: temperature_gate(metrics[c], metrics['weather_mse300']) for c in [*BLENDS, 'selected_temperature']},
                   old_frozen_files=freezes[0], reserved_frozen_files=freezes[1], assessment_outcomes_used=False,
                   new_independent_assessment=False, model_promoted=False,
                   files={p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob('*')) if p.is_file()})
    write(out / 'summary.json', summary)
    print(json.dumps({k: summary[k] for k in ['status', 'choices', 'development_gate_vs_weather14', 'incremental_gate_vs_mse300']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
