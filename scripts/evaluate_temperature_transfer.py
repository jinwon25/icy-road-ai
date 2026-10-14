"""기온 대비 편차·열환경 입력 후보를 기존 HGB와 중첩 공간 비교한다."""
import argparse
from datetime import datetime, timezone
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
from src.data_source import sha256_file
from src.external_reserved import verify_reserved_freeze
from src.frozen_assessment import verify_freeze
from src.temperature_transfer import (CANDIDATES, LOSS_CANDIDATES, MODEL_OVERRIDES, candidate_spec, THERMAL_FEATURES, WEATHER_FEATURES,
    validate_development, training_arrays, predict_temperature, regression_report, select_temperature)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['thermal', 'loss'], default='thermal')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    out = (args.output or ROOT / ('outputs/private/temperature_transfer_20261009_v1' if args.profile == 'thermal'
                                 else 'outputs/private/temperature_loss_20261009_v1')).resolve()
    if not out.is_relative_to((ROOT / 'outputs/private').resolve()):
        raise ValueError('Write experiment artifacts only under outputs/private')
    if out.exists():
        raise FileExistsError('Preserve existing run; choose a new output version')
    release = ROOT / 'outputs/private/releases/20261007'
    private = release / 'outputs/private'
    previous = ROOT / 'outputs/private/weather_fallback_20261009_v1'
    group_run = ROOT / 'outputs/private/ice_group_balanced_20261009_v1'
    config_path = ROOT / ('config/temperature_transfer_experiment.json' if args.profile == 'thermal'
                         else 'config/temperature_loss_experiment.json')
    config = read(config_path)
    candidates = CANDIDATES if args.profile == 'thermal' else LOSS_CANDIDATES
    if config['candidates'] != list(candidates) or config['thermal_additions'] != (THERMAL_FEATURES[14:] if args.profile == 'thermal' else []):
        raise ValueError('Experiment feature contract differs from config')
    if args.profile == 'loss' and config['model_overrides'] != MODEL_OVERRIDES:
        raise ValueError('Loss experiment model contract differs from config')
    for entry in read(previous / 'input_signature.json').values():
        if sha256_file(Path(entry['path'])) != entry['sha256']:
            raise ValueError('Previous source signature changed')
    frozen_external = verify_reserved_freeze(release, private / 'external_reserved_predictions_v1')
    frozen_original = verify_freeze(release)
    sources = {
        'training_index': previous / 'training_index.parquet',
        'physical_matrix': group_run / 'feature_matrix.parquet',
        'development_index': group_run / 'development_index.parquet',
        'previous_predictions': previous / 'outer_predictions.parquet',
        'previous_fits': previous / 'fit_receipts.json',
        'groups': release / 'config/kma_external_validation_plan.json',
        'config': config_path, 'runner': Path(__file__),
        'implementation': ROOT / 'src/temperature_transfer.py',
    }
    signature = {k: {'path': str(p), 'sha256': sha256_file(p)} for k, p in sources.items()}
    frame = pd.read_parquet(sources['training_index'])
    index = pd.read_parquet(sources['development_index'])
    if not frame[['station', 'time']].equals(index[['station', 'time']]):
        raise ValueError('Prior thermal index and predictor rows differ')
    matrix = pd.read_parquet(sources['physical_matrix'], columns=THERMAL_FEATURES)
    if len(matrix) != len(frame):
        raise ValueError('Predictor rows differ')
    frame = pd.concat([frame.reset_index(drop=True), matrix.reset_index(drop=True)], axis=1)
    validate_development(frame)
    plan = read(sources['groups'])
    groups = {k: set(v) for k, v in plan['station_groups'].items()}
    external = set().union(*groups.values())
    donors = set(frame.loc[frame.group.eq('competition'), 'station'])
    if len(donors) != 14 or len(external) != 9 or set(frame.station) != donors | external:
        raise ValueError('Only pinned 23 development stations permitted')
    old_fits = [r for r in read(sources['previous_fits']) if r['candidate'] == 'augmented_hgb']
    baselines = {}
    for receipt in old_fits:
        key = tuple(receipt['forbidden_stations'])
        path = previous / receipt['model_path']
        if sha256_file(path) != receipt['model_sha256'] or receipt['features'] != WEATHER_FEATURES:
            raise ValueError('Baseline model changed')
        expected = frame.loc[frame.road_temp.notna() & frame.asos_air_temp.notna() & ~frame.station.isin(key)]
        if len(expected) != receipt['training_rows'] or sorted(expected.station.unique()) != receipt['training_stations']:
            raise ValueError('Baseline fit population differs')
        baselines.setdefault(key, (path, receipt))
    out.mkdir()
    write(out / 'experiment_plan.json', config)
    write(out / 'input_signature.json', signature)
    shutil.copy2(__file__, out / 'analysis_source.py')
    shutil.copy2(sources['implementation'], out / 'temperature_transfer.py')
    frame.to_parquet(out / 'development_inputs.parquet', index=False, compression='zstd')
    write(out / 'groups.json', {g: sorted(v) for g, v in groups.items()})
    cache, fit_receipts, decisions, results, references = {}, [], {}, [], []

    def baseline(forbidden, query):
        key = tuple(sorted(forbidden))
        path, receipt = baselines[key]
        model = joblib.load(path)
        pred = np.where(query.asos_air_temp.notna(), model.predict(query[WEATHER_FEATURES]), np.nan)
        references.append({'path': str(path), 'sha256': receipt['model_sha256'], 'forbidden_stations': list(key)})
        return pred

    def fit(candidate, forbidden):
        key = (candidate, tuple(sorted(forbidden)))
        if key in cache:
            return cache[key]
        train = frame.loc[np.isfinite(frame.road_temp) & np.isfinite(frame.asos_air_temp)
                          & ~frame.station.isin(forbidden)].copy()
        x, y = training_arrays(train, candidate, forbidden)
        folder = out / 'models' / (candidate + '__' + '_'.join(sorted(forbidden)))
        folder.mkdir(parents=True)
        started = time.monotonic()
        parameters = config['hgb_parameters'] | MODEL_OVERRIDES.get(candidate, {})
        model = HistGradientBoostingRegressor(**parameters)
        model.fit(x, y)
        joblib.dump(model, folder / 'model.joblib')
        receipt = {'candidate': candidate, 'forbidden_stations': sorted(forbidden),
                   'training_stations': sorted(train.station.unique()), 'training_rows': len(train),
                   'features': list(x), 'residual_anchor': 'asos_air_temp' if candidate_spec(candidate)[1] else None,
                   'model_parameters': parameters,
                   'model_path': (folder / 'model.joblib').relative_to(out).as_posix(),
                   'model_sha256': sha256_file(folder / 'model.joblib'),
                   'fit_seconds': time.monotonic() - started,
                   'training_values_sha256': __import__('hashlib').sha256(
                       pd.util.hash_pandas_object(train, index=True).to_numpy().tobytes()).hexdigest()}
        write(folder / 'fit_manifest.json', receipt)
        fit_receipts.append(receipt)
        cache[key] = model
        print(candidate, ','.join(sorted(forbidden)), 'fit complete', round(receipt['fit_seconds'], 2), flush=True)
        return model

    with threadpool_limits(limits=config['max_compute_threads']):
        for outer, held in groups.items():
            query = frame.loc[frame.station.isin(external - held)].copy()
            scores = {name: pd.Series(np.nan, index=query.index) for name in ['direct_weather14', *candidates]}
            for inner, checked in groups.items():
                if inner == outer:
                    continue
                check = query.loc[query.station.isin(checked)]
                scores['direct_weather14'].loc[check.index] = baseline(held | checked, check)
                for candidate in candidates:
                    model = fit(candidate, held | checked)
                    scores[candidate].loc[check.index] = predict_temperature(model, check, candidate)
            domain = np.isfinite(query.asos_air_temp)
            if any(not np.array_equal(np.isfinite(p), domain) for p in scores.values()):
                raise ValueError('Inner prediction domains differ')
            reports = {name: regression_report(query, p.to_numpy()) for name, p in scores.items()}
            chosen = select_temperature(reports, maximum_station_harm=config['maximum_station_harm'], candidate_names=list(candidates))
            decision = {'outer_group': outer, 'selection_groups': sorted(set(groups) - {outer}),
                        'excluded_stations': sorted(held), 'selected_candidate': chosen,
                        'inner_reports': reports, 'outer_labels_used_for_selection': False}
            folder = out / outer; folder.mkdir()
            write(folder / 'decision.json', decision)
            inner_output = query[['station', 'time', 'road_temp']].copy()
            for name, p in scores.items(): inner_output[name] = p.to_numpy()
            inner_output.to_parquet(folder / 'inner_oof.parquet', index=False, compression='zstd')
            # 내부 선택을 저장한 뒤 외부 그룹을 예측하며 외부 결과로 선택을 바꾸지 않는다.
            check = frame.loc[frame.station.isin(held)]
            part = check[['station', 'time', 'group', 'road_temp']].copy()
            part['direct_weather14'] = baseline(held, check)
            for candidate in candidates:
                model = fit(candidate, held)
                part[candidate] = predict_temperature(model, check, candidate)
            part['selected_candidate'] = chosen
            part['selected_temperature'] = part[chosen]
            part.to_parquet(folder / 'outer_predictions.parquet', index=False, compression='zstd')
            results.append(part); decisions[outer] = decision
            print(outer, 'selected', chosen, flush=True)
    combined = pd.concat(results, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    previous_predictions = pd.read_parquet(sources['previous_predictions']).set_index(['station', 'time'])
    old = previous_predictions.loc[pd.MultiIndex.from_frame(combined[['station', 'time']])]
    np.testing.assert_allclose(combined.direct_weather14, old.augmented_hgb, rtol=0, atol=1e-12, equal_nan=True)
    variants = ['direct_weather14', *candidates, 'selected_temperature']
    domain = np.isfinite(combined.direct_weather14)
    if any(not np.array_equal(np.isfinite(combined[v]), domain) for v in variants):
        raise ValueError('Outer prediction domains differ')
    metrics = {name: regression_report(combined, combined[name]) for name in variants}
    rows = [{'variant': name, 'station': st, **m} for name, r in metrics.items() for st, m in r['stations'].items()]
    pd.DataFrame(rows).to_csv(out / 'station_metrics.csv', index=False, encoding='utf-8-sig')
    regimes = []
    for name in variants:
        for label, mask in [('all', np.ones(len(combined), bool)),
                            ('day_06to18', combined.time.dt.hour.between(6, 17)),
                            ('night', ~combined.time.dt.hour.between(6, 17)),
                            *[(g, combined.group.eq(g)) for g in groups],
                            *[(m, combined.time.dt.strftime('%Y-%m').eq(m)) for m in ['2024-11', '2024-12', '2025-01', '2025-02']]]:
            regimes.append({'variant': name, 'regime': label,
                            **regression_report(combined.loc[mask], combined.loc[mask, name])['pooled']})
    pd.DataFrame(regimes).to_csv(out / 'regime_metrics.csv', index=False, encoding='utf-8-sig')
    combined.to_parquet(out / 'outer_predictions.parquet', index=False, compression='zstd')
    write(out / 'decisions.json', decisions)
    write(out / 'fit_receipts.json', fit_receipts)
    write(out / 'baseline_reuse.json', references)
    if verify_reserved_freeze(release, private / 'external_reserved_predictions_v1') != frozen_external or verify_freeze(release) != frozen_original:
        raise ValueError('Frozen assessment evidence changed')
    summary = {'status': 'nested_development_comparison_complete', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
               'scope': config['scope'], 'input_rows': len(frame), 'outer_rows': len(combined),
               'metrics': metrics, 'choices': {g: d['selected_candidate'] for g, d in decisions.items()},
               'unique_new_fits': len(fit_receipts), 'protected_or_reserved_outcomes_used': False,
               'frozen_external_files': len(frozen_external['files']), 'frozen_original_files': len(frozen_original['files']),
               'final_model_promoted': False,
               'files': {p.relative_to(out).as_posix(): sha256_file(p) for p in out.rglob('*') if p.is_file()}}
    write(out / 'summary.json', summary)
    print(json.dumps({'choices': summary['choices'], 'fits': summary['unique_new_fits'],
                      'metrics': {k: {'pooled': v['pooled'], 'macro': v['station_macro'], 'near_freezing': v['near_freezing']}
                                  for k, v in metrics.items()}}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
