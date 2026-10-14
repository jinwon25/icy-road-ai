"""결빙점 가중 MSE/MAE와 고정 결합을 이중 공간 제외로 비교한다."""
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
import hashlib
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
from scripts.evaluate_method_blending import read, write, preservation, training
from scripts.evaluate_thermal_consensus import report, eligible
from src.data_source import sha256_file as sha
from src.method_blending import domain, ALLOWED, temperature_gate
from src.temperature_transfer import regression_report
from src.thermal_ice import fixed_thermal_rule
from src.event_retention import compare_event_retention
from src.qa633_metrics import daily_table, aggregate
from src.weather_distance_ablation import DISTANCE_FREE_FEATURES as FEATURES
from src.freezing_weight import freezing_weights, fixed_blends

PRIVATE = ROOT / 'outputs/private'
SOURCE = PRIVATE / 'weather_memory_controls_20261013_v1'
INPUT = PRIVATE / 'weather_distance_20261010_v1/development_inputs.parquet'
LABEL = PRIVATE / 'qa633_development_20261013_v1/fixed_predictions.parquet'
OUT = PRIVATE / 'freezing_weight_20261014_v1'
CONFIG = ROOT / 'config/freezing_weight_experiment.json'


def fingerprint(frame):
    return hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).to_numpy().tobytes()).hexdigest()


def score(frame, names):
    result, stations, events = {}, {}, {}
    for name in names:
        p, fallback, _ = fixed_thermal_rule(frame[name], frame, frame.original, True)
        frame['ice_' + name] = p
        ice, stations[name], events[name] = report(frame, p)
        result[name] = dict(temperature=regression_report(frame, frame[name]), ice=ice,
                            fallback_rows=int(fallback.sum()))
    return result, stations, events


def assess(result, stations, events, names, baseline):
    for name in names:
        retention = compare_event_retention(events[baseline], events[name])
        temp = temperature_gate(result[name]['temperature'], result[baseline]['temperature'])
        ice = eligible(result[name]['ice'], result[baseline]['ice'], stations[name], stations[baseline], retention)
        result[name].update(temperature_gate=temp, ice_gate=ice, retention=retention, eligible=bool(temp and ice))


def main():
    if OUT.exists():
        raise FileExistsError('Preserve completed or interrupted experiment')
    plan = read(CONFIG)
    frozen = preservation()
    audit = read(SOURCE / 'independent_verification.json')
    assert audit['summary_sha256'] == sha(SOURCE / 'summary.json')
    for rel, digest in read(SOURCE / 'input_signatures.json').items():
        assert sha(ROOT / rel) == digest
    groups = read(SOURCE / 'groups.json')
    baseline, secondary = plan['baseline'], plan['secondary_baseline']
    models, candidates = plan['models'], plan['candidates']
    pinned = [CONFIG, Path(__file__), ROOT / 'src/freezing_weight.py',
              ROOT / 'src/qa633_metrics.py', ROOT / 'src/thermal_ice.py', ROOT / 'src/method_blending.py',
              ROOT / 'src/temperature_transfer.py', ROOT / 'src/event_retention.py',
              ROOT / 'scripts/evaluate_thermal_consensus.py', ROOT / 'scripts/evaluate_method_blending.py',
              INPUT, LABEL, SOURCE / 'summary.json', SOURCE / 'independent_verification.json', SOURCE / 'groups.json']
    pinned += [SOURCE / g / (kind + '.parquet') for g in groups for kind in ('inner_oof', 'outer_predictions')]
    signatures = {str(p.relative_to(ROOT)): sha(p) for p in pinned}
    OUT.mkdir()
    write(OUT / 'experiment_plan.json', plan | {'started_at_utc': datetime.now(timezone.utc).isoformat()})
    write(OUT / 'input_signatures.json', signatures)
    write(OUT / 'groups.json', groups)
    shutil.copy2(Path(__file__), OUT / 'analysis_source.py')
    data = domain(pd.read_parquet(INPUT))
    assert set(data.station) == ALLOWED
    labels = domain(pd.read_parquet(LABEL, columns=['station', 'time', 'ice', 'original']))
    water = data[['station', 'time', 'aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']]
    receipts, predictions = [], {}
    controls = read(SOURCE / 'fit_receipts.json')
    with threadpool_limits(limits=2):
        for excluded in [(g,) for g in sorted(groups)] + list(combinations(sorted(groups), 2)):
            forbidden = set().union(*(set(groups[g]) for g in excluded))
            train = training(data, forbidden)
            query = data.loc[data.station.isin(forbidden)].copy()
            weights = freezing_weights(train.road_temp, plan['weight']['amplitude'], plan['weight']['sigma_celsius'])
            folder = OUT / 'contexts' / '__'.join(excluded)
            folder.mkdir(parents=True)
            pred = query[['station', 'time']].copy()
            for name, old, loss in zip(models, ['nohistory12_mse300', 'nohistory12_mae300'], ['squared_error', 'absolute_error']):
                params = plan['hgb_parameters'] | {'loss': loss}
                matched = next(r for r in controls if r['candidate'] == old and r['excluded_groups'] == list(excluded))
                assert matched['parameters'] == params and matched['training_rows'] == len(train)
                assert matched['training_stations'] == sorted(train.station.unique()) and matched['features'] == list(FEATURES)
                started = time.monotonic()
                model = HistGradientBoostingRegressor(**params).fit(train[list(FEATURES)], train.road_temp, sample_weight=weights)
                path = folder / (name + '.joblib')
                joblib.dump(model, path, compress=3)
                pred[name] = np.where(np.isfinite(query.asos_air_temp), model.predict(query[list(FEATURES)]), np.nan)
                receipts.append(dict(candidate=name, excluded_groups=list(excluded), forbidden_stations=sorted(forbidden),
                    training_stations=sorted(train.station.unique()), training_rows=len(train), features=list(FEATURES), parameters=params,
                    training_values_sha256=fingerprint(train[['station', 'time', 'road_temp', *FEATURES]]),
                    weights_sha256=hashlib.sha256(weights.tobytes()).hexdigest(), weight_min=float(weights.min()),
                    weight_max=float(weights.max()), weight_mean=float(weights.mean()),
                    model_path=path.relative_to(OUT).as_posix(), model_sha256=sha(path), fit_seconds=time.monotonic()-started))
                print('학습', '__'.join(excluded), name, round(receipts[-1]['fit_seconds'], 1), flush=True)
            pred.to_parquet(folder / 'predictions.parquet', index=False, compression='zstd')
            predictions[excluded] = pred
    write(OUT / 'fit_receipts.json', receipts)
    parts, decisions = [], {}
    names = [baseline, secondary, *candidates]
    for g in sorted(groups):
        frames = {}
        for kind in ('inner_oof', 'outer_predictions'):
            reference = domain(pd.read_parquet(SOURCE / g / (kind + '.parquet'),
                columns=['station', 'time', 'group', 'road_temp', baseline, secondary]))
            pp = []
            for h in sorted(set(groups)-{g}) if kind == 'inner_oof' else [g]:
                key = tuple(sorted([g, h])) if kind == 'inner_oof' else (g,)
                pp.append(predictions[key].loc[predictions[key].station.isin(groups[h])])
            frame = reference.merge(pd.concat(pp), on=['station', 'time'], how='left', validate='one_to_one')
            pd.testing.assert_frame_equal(frame[reference.columns], reference)
            frame = frame.merge(labels, on=['station', 'time'], validate='one_to_one').merge(water, on=['station', 'time'], validate='one_to_one')
            assert len(frame) == len(reference)
            for key, value in fixed_blends(frame[baseline], frame[models[0]], frame[models[1]]).items():
                frame[key] = value
            frames[kind] = frame
        inner, outer = frames['inner_oof'], frames['outer_predictions']
        scores, stations, events = score(inner, names)
        assess(scores, stations, events, candidates, baseline)
        accepted = [c for c in candidates if scores[c]['eligible']]
        chosen = min(accepted, key=lambda c: (scores[c]['temperature']['station_macro']['mae'],
                     scores[c]['temperature']['station_macro']['rmse'], c)) if accepted else baseline
        decisions[g] = dict(selected=chosen, eligible=accepted, scores=scores, outer_labels_used=False,
                            selection_groups=sorted(set(groups)-{g}))
        outer['nested_selected'] = outer[chosen]
        outer['selected_candidate'] = chosen
        folder = OUT / g
        folder.mkdir()
        inner.to_parquet(folder / 'inner_oof.parquet', index=False, compression='zstd')
        outer.to_parquet(folder / 'outer_predictions.parquet', index=False, compression='zstd')
        parts.append(outer)
        print('내부 선택', g, chosen, '적격', accepted, flush=True)
    write(OUT / 'decisions.json', decisions)
    combined = pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    all_names = names + ['nested_selected']
    scores, stations, events = score(combined, all_names)
    assess(scores, stations, events, candidates + ['nested_selected'], baseline)
    combined.to_parquet(OUT / 'outer_predictions.parquet', index=False, compression='zstd')
    day_tables, station_tables = [], []
    for name in all_names:
        stations[name].to_csv(OUT / (name + '_station_diagnostics.csv'), index=False)
        events[name].to_csv(OUT / (name + '_events.csv'), index=False)
        for n in (144, 130, 72, 1):
            days = daily_table(combined, combined['ice_' + name], sorted(combined.station.unique()), n)
            _, ss = aggregate(days, sorted(combined.station.unique()))
            for table, dest in ((days, day_tables), (ss, station_tables)):
                table['method'] = name
                table['minimum_valid_slots'] = n
                dest.append(table)
        r = scores[name]
        print(name, 'MAE', r['temperature']['station_macro']['mae'], 'near', r['temperature']['near_freezing']['mae'],
              'F1', r['ice']['daily']['144']['f1_available_station_mean'], 'FP/FN', r['ice']['fp'], r['ice']['fn'], flush=True)
    pd.concat(day_tables).to_csv(OUT / 'daily_metrics.csv', index=False)
    pd.concat(station_tables).to_csv(OUT / 'station_metrics.csv', index=False)
    assert all(sha(ROOT / p) == h for p, h in signatures.items()) and preservation() == frozen
    assert all(r['temperature']['pooled']['n'] == 155236 for r in scores.values())
    write(OUT / 'summary.json', dict(status='freezing_weight_development_complete',
        completed_at_utc=datetime.now(timezone.utc).isoformat(), scores=scores,
        choices={g:d['selected'] for g,d in decisions.items()}, rows=len(combined), new_model_fits=len(receipts),
        repeated_development=True, new_independent_assessment=False, assessment_outcomes_used=False, model_promoted=False,
        old_frozen_files=frozen[0], reserved_frozen_files=frozen[1],
        files={p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file()}))


if __name__ == '__main__':
    main()
